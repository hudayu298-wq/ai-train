"""LiftLab API with account authentication and owner-scoped storage."""
import json
import asyncio
import logging
import time
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError, ConfigDict
from typing import Literal
try:
    from . import training_program, plan_generation
except ImportError:
    import training_program, plan_generation
try:
    from . import ai_planner, library, movement_analysis, coach, reminders, workouts, database, auth, progression, health_data, agent, research
    from .services import research_store, knowledge_store,privacy
    from . import periodization
    from . import nutrition_guidance, mobility, strength_profile
    from . import knowledge
    from .services import nutrition as nutrition_service
except ImportError:
    import ai_planner
    import library
    import movement_analysis
    import coach
    import reminders
    import workouts
    import database
    import auth
    import progression
    import health_data
    import agent
    import research
    from services import research_store, knowledge_store,privacy
    import periodization
    import nutrition_guidance, mobility
    import strength_profile
    import knowledge
    from services import nutrition as nutrition_service

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / '.env', override=False)
DATA = Path(os.environ.get('FIT_DATA_DIR', ROOT / 'data'))
DATA.mkdir(parents=True, exist_ok=True)
DB = DATA / 'fitness-v2.db'

def connection():
    return database.connection(DB)

# Production schemas are upgraded explicitly with Alembic before starting the service.
if os.environ.get('APP_ENV') != 'production':
    database.metadata.create_all(database.get_engine(DB))
auth.secret()

def save(kind, payload, key=None,*,privacy_revision=None):
    key = key or str(uuid4())
    with connection() as db:
        if privacy_revision is not None:
            db.lock_user()
            privacy.require(db,privacy_revision)
        db.write(kind, key, payload)
    return {'id': key, **payload}

def records(kind):
    with connection() as db:
        return db.records(kind)

app = FastAPI(title='练伴 API', version='0.5.1',
    docs_url=None if os.environ.get('APP_ENV') == 'production' else '/docs',
    redoc_url=None if os.environ.get('APP_ENV') == 'production' else '/redoc',
    openapi_url=None if os.environ.get('APP_ENV') == 'production' else '/openapi.json')
auth.install_middleware(app, DB)

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Default Pydantic errors include raw input, which can contain credentials.
    return JSONResponse(status_code=422, content={'detail': '输入不符合要求，请检查字段和数值范围',
        'fields': [list(e['loc']) for e in exc.errors()]})

@app.exception_handler(IntegrityError)
async def conflict_error(request, exc):
    return JSONResponse(status_code=409, content={'detail': '记录冲突，请刷新后重试'})
app.add_middleware(CORSMiddleware, allow_origin_regex=r'https?://(localhost|127\.0\.0\.1)(:\d+)?',
                   allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'], allow_headers=['Content-Type', 'Authorization'])

app.include_router(auth.router(DB, DATA))

library.initialize(connection)
app.include_router(library.router(connection))
app.include_router(strength_profile.router(connection))

def exercise_entries():
    return library.all_entries(connection, 'exercises')

def food_entries():
    return library.all_entries(connection, 'foods')

def require_weighted(exercise_id):
    entry = library.find_entry(connection, 'exercises', exercise_id)
    if not entry or entry['type'] != 'weighted':
        raise HTTPException(422, '请选择动作库中有效的负重动作；自重模块当前仅支持资料浏览')
    return entry

def validate_plan_exercises(plan):
    for day in plan['days']:
        for exercise in day['exercises']:
            require_weighted(exercise['exercise_id'])

class Profile(BaseModel):
    age: int = Field(ge=18, le=90)
    height_cm: float = Field(ge=120, le=230)
    weight_kg: float = Field(ge=35, le=250)
    sex: Literal['male', 'female']
    goal: Literal['fat_loss', 'muscle_gain']
    experience: Literal['beginner', 'intermediate'] = 'beginner'
    days: int = Field(ge=1, le=7)
    restrictions: str = Field(default='', max_length=1000)

class Meal(BaseModel):
    food_id: str
    grams: float = Field(gt=0, le=3000)
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack'] = 'breakfast'
    day: date | None = None
    portion_source: Literal['unknown', 'weighed', 'estimated', 'label', 'ai_confirmed'] = 'unknown'
    portion_confirmed: bool = True
    notes: str = Field(default='', max_length=500)
    request_id: str | None = Field(default=None, min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


class NutritionDiary(BaseModel):
    status: Literal['unknown', 'partial', 'complete']
    notes: str = Field(default='', max_length=500)

def nutrition_today():
    return datetime.now(timezone(timedelta(hours=8))).date()

NUTRIENTS = ['kcal', 'protein', 'fat', 'carbs']
MEAL_LABELS = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '加餐', 'unassigned': '未分类'}

def nutrient_totals(items):
    return {k: float(sum((Decimal(str(item['nutrients'][k])) for item in items), Decimal(0)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) for k in NUTRIENTS}

class Training(BaseModel):
    exercise_id: str
    weight_kg: float = Field(ge=0, le=500)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    rpe: float = Field(ge=1, le=10)
    pain: bool = False
    day: date = Field(default_factory=date.today)

class RMRecord(BaseModel):
    exercise_id: str = Field(min_length=1, max_length=80)
    weight_kg: float = Field(gt=0, le=500)
    reps: int = Field(ge=1, le=10)
    measured_on: date
    confirmed_maximum: bool

class PlanExercise(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    exercise_id: str = Field(min_length=1, max_length=80)
    weight_kg: float | None = Field(gt=0, le=500)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    rest_seconds: int = Field(ge=0, le=1800)
    target_rir: int | None = Field(default=None, ge=0, le=10, strict=True)

class PlanDay(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r'.*\S.*')
    exercises: list[PlanExercise] = Field(min_length=1, max_length=20)
    weekday: int | None = Field(default=None, ge=1, le=7)
    start_time: str | None = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    duration_minutes: int | None = Field(default=None, ge=15, le=180)
    focus: training_program.Focus | None = None
    session_goal: str | None = Field(default=None, min_length=1, max_length=240, pattern=r'.*\S.*')
    training_method: Literal['straight_sets', 'five_by_five', 'strength_hypertrophy'] | None = None
    primary_exercise_id: str | None = Field(default=None, min_length=1, max_length=80)

class CycleWeek(BaseModel):
    model_config = ConfigDict(extra='forbid')
    week: int = Field(ge=1, le=periodization.POLICY['max_cycle_weeks'], strict=True)
    phase: Literal['foundation', 'build', 'consolidate', 'deload']
    purpose: str = Field(min_length=1, max_length=700)
    days: list[PlanDay] = Field(min_length=1, max_length=7)

class CycleBlueprintWeek(BaseModel):
    model_config = ConfigDict(extra='forbid')
    week: int = Field(ge=1, le=periodization.POLICY['max_cycle_weeks'], strict=True)
    phase: Literal['foundation', 'build', 'consolidate', 'deload']
    purpose: str = Field(min_length=1, max_length=160)
    template: Literal['base', 'recovery'] = 'base'

class UserPlan(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')
    days: list[PlanDay] = Field(min_length=1, max_length=7)
    generation_id: str | None = None
    base_plan_id: str | None = None
    cycle_weeks: int | None = Field(default=None, ge=periodization.POLICY['min_cycle_weeks'], le=periodization.POLICY['max_cycle_weeks'])
    cycle_schedule: list[CycleWeek] | None = Field(default=None, min_length=periodization.POLICY['min_cycle_weeks'], max_length=periodization.POLICY['max_cycle_weeks'])

class AIPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    split_type: Literal['full_body', 'upper_lower', 'push_pull_legs', 'bodypart_four', 'bodypart_five']
    days: list[PlanDay] = Field(min_length=1, max_length=7)
    rationale: str = Field(min_length=1, max_length=1500)
    warmup: str = Field(min_length=1, max_length=1000)
    recovery: str = Field(min_length=1, max_length=1000)
    progression: str = Field(min_length=1, max_length=1000)
    cycle_weeks: int = Field(default=periodization.POLICY['default_cycle_weeks'], ge=periodization.POLICY['min_cycle_weeks'], le=periodization.POLICY['max_cycle_weeks'])
    weeks: list[str] = Field(default_factory=list, max_length=periodization.POLICY['max_cycle_weeks'])
    cycle_schedule: list[CycleWeek] = Field(default_factory=list, max_length=periodization.POLICY['max_cycle_weeks'])
    cycle_blueprint: list[CycleBlueprintWeek] = Field(default_factory=list, max_length=periodization.POLICY['max_cycle_weeks'])
    risk_warnings: list[str] = Field(default_factory=list, max_length=10)

# NSCA Training Load Chart: generic max-repetition references, not individual limits.
RM_FRACTIONS = {1: 1.0, 2: .95, 3: .93, 4: .90, 5: .87, 6: .85, 7: .83, 8: .80, 9: .77, 10: .75}

@app.post('/api/rm')
def add_rm(rm: RMRecord):
    require_weighted(rm.exercise_id)
    if rm.measured_on > nutrition_today():
        raise HTTPException(422, 'RM日期不能晚于今天')
    estimate = rm.weight_kg / RM_FRACTIONS[rm.reps] if rm.confirmed_maximum else None
    return save('rm', {**rm.model_dump(mode='json'), 'reference_1rm_kg': round(estimate, 2) if estimate else None,
        'method': 'self_reported_1rm' if rm.reps == 1 else 'nsca_rm_table_estimate', 'rule_version': 'rm-0.1'})

@app.get('/api/rm')
def get_rm():
    latest = {}
    for record in records('rm'):
        key = record['exercise_id']
        if key not in latest or record['measured_on'] > latest[key]['measured_on']:
            latest[key] = record
    return list(latest.values())

def assess_plan(plan):
    baselines = {r['exercise_id']: r for r in get_rm()}
    profile = get_profile()
    result = []
    for day in plan['days']:
        for exercise in day['exercises']:
            item = {'day': day['name'], 'exercise_id': exercise['exercise_id'],
                'volume_kg': round(exercise['weight_kg'] * exercise['sets'] * exercise['reps'], 1) if exercise['weight_kg'] is not None else None,
                'load_percent': None, 'rm_id': None, 'reference_1rm_kg': None}
            rm = baselines.get(exercise['exercise_id'])
            if profile and profile['restrictions'].strip():
                item['risk_warning'] = '已记录伤病或限制；以下为负荷参考，请结合可训练范围，不适时暂停相关动作。'
            if exercise['weight_kg'] is None:
                item.update(status='missing_load', message='重量待确认：补充该动作的可靠RM或根据实际训练填写重量。')
            elif not rm and exercise.get('load_reference', {}).get('kind') in ('reported_performance', 'regional_estimate'):
                item.update(status='estimated_load', message=exercise['load_reference']['label'] + '：这是起始建议，需首训核对，不是实测RM。')
            elif not rm or not rm['confirmed_maximum']:
                item.update(status='missing_rm', message='缺少确认的RM数据，暂不评估负荷。')
            elif (nutrition_today() - date.fromisoformat(rm['measured_on'])).days > 90:
                item.update(status='stale_rm', message='RM数据超过90天，请更新后再评估。')
            else:
                raw_percent = exercise['weight_kg'] / rm['reference_1rm_kg'] * 100
                item.update(rm_id=rm['id'], reference_1rm_kg=rm['reference_1rm_kg'],
                    load_percent=round(raw_percent, 1), rm_method=rm['method'], measured_on=rm['measured_on'])
                reference = RM_FRACTIONS.get(exercise['reps'])
                if raw_percent > 100:
                    item.update(status='above_reference', message='计划重量超过当前1RM参考值，请复核重量和RM数据。')
                elif reference is None:
                    item.update(status='reference_only', message='已展示相对负荷；超过10次的组不做次数匹配推断。')
                elif raw_percent > reference * 100:
                    item.update(status='high_relative_load', message='重量高于该次数的通用RM参考，完成难度可能较高；结合余力与疲劳复核。')
                else:
                    item.update(status='reference_only', message='已展示相对负荷；RM不能单独判定计划合理性或动作安全。')
            result.append(item)
    return {'rule_version': 'rm-0.1', 'items': result,
        'note': '按用户提供的RM与通用次数表评估，不调整计划；多次RM换算为估算1RM。'}

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'multi_user', 'vision_enabled': False}


@app.get('/api/cache/status')
def cache_status():
    try:from .services import cache, research_store
    except ImportError:from services import cache, research_store
    with connection() as db:research_store.require_admin(db)
    return cache.status()

@app.get('/api/catalog')
def catalog(extended: bool = False):
    # Older installed clients assume every returned exercise has a live detector.
    exercises = exercise_entries()
    # Keep names/options needed to edit existing owner records, while new users
    # receive only the everyday selection. The backing catalog is never deleted.
    referenced = set()
    if extended:
        with connection() as db:
            for kind in ('plan', 'plan_draft', 'workout', 'training', 'rm'):
                referenced.update(library.exercise_selection.referenced_ids(db.records(kind)))
        exercises = [e for e in exercises if library.exercise_selection.visible(e) or e['id'] in referenced]
    if not extended:
        exercises = [e for e in exercises if e.get('realtime_supported')]
    if extended:
        # The app needs identities and filter facets here; full teaching text is
        # loaded from the paginated library rather than duplicating megabytes at login.
        exercises=[{k:v for k,v in e.items() if k not in ('technique','upstream_refs','demo')}
            if e.get('source_kind')=='external_catalog' else e for e in exercises]
    return {'exercises': exercises, 'foods': food_entries(), 'food_source': '每100克可食部分；来源与生熟状态详见每个条目'}

@app.get('/api/profile')
def get_profile():
    items = records('profile')
    return items[0] if items else None

@app.put('/api/profile')
def put_profile(profile: Profile):
    return save('profile', profile.model_dump(), 'local-profile')

@app.post('/api/plans')
def save_user_plan(plan: UserPlan):
    payload = plan.model_dump()
    requested_cycle_weeks = payload.pop('cycle_weeks')
    requested_schedule = payload.pop('cycle_schedule')
    generation_id = payload.pop('generation_id')
    base_plan_id = payload.pop('base_plan_id')
    if generation_id and base_plan_id:
        raise HTTPException(422, '生成草稿确认与当前计划编辑不能同时提交')
    validate_plan_exercises(payload)
    if len({d['name'] for d in payload['days']}) != len(payload['days']):
        raise HTTPException(422, '训练日名称不能重复')
    with connection() as db:
        db.lock_user()
        current = progression.active_plan(db)
        draft = db.read('plan_draft', generation_id) if generation_id else None
        if draft and draft.get('privacy_invalidated'):
            raise HTTPException(409,'来源数据或授权已变化，旧AI草稿已清除，请重新生成')
        if generation_id and not draft:
            raise HTTPException(422, 'AI草稿不存在，请重新生成')
        optional_source = draft or (current if base_plan_id else {}) or {}
        for index, day in enumerate(payload['days']):
            original = next((d for d in optional_source.get('days', []) if d['name'] == day['name']), {})
            training_program.preserve_day(day, original, plan.days[index].model_fields_set)
            for ei, exercise in enumerate(day['exercises']):
                previous = next((e for e in original.get('exercises', []) if e['exercise_id'] == exercise['exercise_id']), {})
                if 'target_rir' not in plan.days[index].exercises[ei].model_fields_set:
                    exercise['target_rir'] = previous.get('target_rir')
                strength_profile.preserve_reference(exercise, previous)
        if generation_id:
            existing = next((p for p in db.records('plan') if p.get('generation_id') == generation_id), None)
            if existing:
                if existing['name'] != payload['name'] or progression.day_inputs(existing['days']) != progression.day_inputs(payload['days']):
                    raise HTTPException(409, '该草稿已确认，修改当前计划请使用编辑入口')
                if ((requested_cycle_weeks is not None and requested_cycle_weeks != existing.get('cycle_weeks', 4)) or
                        requested_schedule is not None and periodization.schedule_signature(requested_schedule) != periodization.schedule_signature(periodization.normalized(existing)['cycle_schedule'])):
                    raise HTTPException(409, '该草稿已确认，周期修改请通过当前计划编辑入口')
                return {**existing, 'assessment': assess_plan(existing)}
            if draft['profile_snapshot'] != get_profile() or draft['rm_snapshot'] != get_rm():
                raise HTTPException(409, '画像或RM已变化，请重新生成AI计划')
            if draft.get('training_program_version') != training_program.VERSION:
                raise HTTPException(409, '计划结构已更新，请重新生成包含每日目标与训练法的草稿')
            current_strength = strength_profile.state(db)
            if not current_strength['ready'] or draft.get('strength_revision') != current_strength['revision']:
                raise HTTPException(409, '胸、背、腿力量资料已变化或未补齐，请重新生成AI计划')
            if any(e['weight_kg'] is None for d in payload['days'] for e in d['exercises']):
                raise HTTPException(422, 'AI计划每个负重动作都需填写具体重量，不能确认空重量计划')
            if draft.get('coach_profile_snapshot') != coach.state(db)['facts']:
                raise HTTPException(409, '画像偏好已变化，请重新生成AI计划')
            if draft.get('training_revision') != workouts.revision(db):
                raise HTTPException(409, '训练档案已变化，请重新生成AI计划')
            if draft.get('health_revision') and draft['health_revision'] != health_data.revision(db):
                raise HTTPException(409, '健康数据或授权已变化，请重新生成AI计划')
            if draft.get('mobility_revision') and draft['mobility_revision'] != mobility.revision(db):
                raise HTTPException(409, '活动度数据或授权已变化，请重新生成AI计划')
            if draft.get('foundation_revision') and draft['foundation_revision'] != knowledge_store.revision(db):
                raise HTTPException(409, '基础知识版本或来源已变化，请重新生成AI计划')
            if draft.get('effective_until') and draft['effective_until'] < nutrition_today().isoformat():
                raise HTTPException(409, '临时周计划已过期，请重新生成')
            if draft.get('base_plan_id') != (current or {}).get('id'):
                raise HTTPException(409, '当前计划已更新，请重新生成')
        if base_plan_id and (not current or current['id'] != base_plan_id):
            raise HTTPException(409, '当前计划已更新，请刷新后修改')
        if requested_schedule is not None:
            for wi, week in enumerate(requested_schedule):
                previous_week = next((w for w in optional_source.get('cycle_schedule', []) if w['week'] == week['week']), {})
                for di, day in enumerate(week['days']):
                    original = next((d for d in previous_week.get('days', []) if d['name'] == day['name']), {})
                    training_program.preserve_day(day, original, plan.cycle_schedule[wi].days[di].model_fields_set)
        if draft and ((requested_cycle_weeks is not None and requested_cycle_weeks != draft['cycle_weeks']) or
                requested_schedule is not None and periodization.schedule_signature(requested_schedule[1:]) != periodization.schedule_signature(draft['cycle_schedule'][1:])):
            raise HTTPException(422, '确认草稿不能改写服务端已校验的未来周；请保存后通过计划编辑入口修改')
        metadata_source = draft or (current if base_plan_id else {}) or {}
        metadata = {k: metadata_source[k] for k in ('rationale', 'warmup', 'recovery', 'progression', 'model',
            'profile_snapshot', 'rm_snapshot', 'coach_profile_snapshot', 'cycle_weeks', 'weeks', 'risk_warnings',
            'requested_schedule', 'effective_profile', 'knowledge_release_id', 'foundation_revision', 'health_revision', 'effective_until', 'strength_revision', 'load_reference_version', 'split_type', 'training_program_version') if k in metadata_source}
        metadata.update({k: metadata_source[k] for k in ('cycle_schedule', 'cycle_schedule_origin', 'cycle_policy_version',
            'cycle_started_on', 'week_started_on', 'week_attempt', 'cycle_reviewed_on', 'cycle_complete', 'cycle_baseline_days', 'cycle_blueprint', 'next_cycle', 'previous_cycle_id') if k in metadata_source})
        if not draft:
            metadata['coach_profile_snapshot'] = coach.state(db)['facts']
        names = {e['id']: e['name'] for e in exercise_entries()}
        for day in payload['days']:
            if len({e['exercise_id'] for e in day['exercises']}) != len(day['exercises']):
                raise HTTPException(422, '同一训练日不能重复添加同一动作')
            for exercise in day['exercises']:
                exercise['name'] = names[exercise['exercise_id']]
        if draft and len(payload['days']) != draft.get('effective_profile', draft['profile_snapshot'])['days']:
            raise HTTPException(422, '确认计划的训练日数量需与画像一致')
        key = str(uuid4())
        saved = {**payload, **metadata, 'generation_id': generation_id,
            'base_plan_id': (current or {}).get('id'), 'version': (current or {}).get('version', 0) + 1,
            'cycle_id': current.get('cycle_id', current['id']) if base_plan_id else key,
            'cycle_week': current.get('cycle_week', 1) if base_plan_id else 1,
            'created_on': nutrition_today().isoformat(), 'source': 'ai' if draft else 'user',
            'note': 'AI生成、用户确认的训练计划。' if draft else '用户确认修改的训练计划。'}
        saved['cycle_weeks'] = requested_cycle_weeks or saved.get('cycle_weeks', 4)
        if not base_plan_id:
            saved.update(cycle_started_on=nutrition_today().isoformat(), week_started_on=nutrition_today().isoformat(),
                week_attempt=1, cycle_complete=False)
        if requested_schedule is not None:
            saved['cycle_schedule'] = requested_schedule
        elif saved.get('cycle_schedule'):
            # Old clients submit only days. Preserve the server draft's full cycle.
            identities = lambda days: [(d['name'], [e['exercise_id'] for e in d['exercises']]) for d in days]
            if any(identities(w['days']) != identities(saved['days']) for w in saved['cycle_schedule']):
                if any(periodization.day_signature(w['days']) != periodization.day_signature(metadata_source['days']) for w in saved['cycle_schedule']):
                    raise HTTPException(422, '现有周期包含不同周目标，修改训练日或动作需重新生成周期或明确提交完整周目标供复核')
                saved['cycle_schedule'] = [{**w, 'days': json.loads(json.dumps(saved['days']))} for w in saved['cycle_schedule']]
                saved.pop('cycle_baseline_days', None)
                saved['cycle_schedule_origin'] = 'user_rebased_template'
        try:
            saved = periodization.sync_current_week(saved)
            saved = periodization.validate_schedule(saved)
        except (ValueError, IndexError):
            raise HTTPException(422, '周期安排与周数、训练日或当前目标不一致') from None
        valid_rms = {r['exercise_id']: r for r in get_rm() if r['confirmed_maximum'] and r.get('reference_1rm_kg')
            and 0 <= (nutrition_today() - date.fromisoformat(r['measured_on'])).days <= periodization.POLICY['rm_max_age_days']}
        catalog_map = {e['id']: e for e in exercise_entries()}
        current_facts = coach.state(db)['facts']
        current_targets = {(d['name'], e['exercise_id']): e for d in saved['days'] for e in d['exercises']}
        for week in saved['cycle_schedule']:
            validate_plan_exercises(week)
            # Full-cycle API submissions lose client provenance at schema parsing.
            # Restore only the matching server target's reference, just as for days.
            previous_week = next((w for w in metadata_source.get('cycle_schedule', []) if w['week'] == week['week']), {})
            for day in week['days']:
                previous_day = next((d for d in previous_week.get('days', []) if d['name'] == day['name']), {})
                limits = [n for n in (day.get('duration_minutes'), current_facts.get('session_minutes')) if n]
                if limits and periodization.estimate_seconds(day) > min(limits) * 60:
                    raise HTTPException(422, '周期中有训练日预计超出可用时间，请调整组次或动作')
                for exercise in day['exercises']:
                    previous = next((e for e in previous_day.get('exercises', []) if e['exercise_id'] == exercise['exercise_id']), {})
                    # sync_current_week already preserved the current day's source.
                    if week['week'] != saved['cycle_week']:
                        strength_profile.preserve_reference(exercise, previous)
                    exercise['name'] = names[exercise['exercise_id']]
                    if not periodization.equipment_allowed(catalog_map[exercise['exercise_id']], current_facts):
                        raise HTTPException(422, '周期动作需要画像未提供的器械，请调整计划')
                    rm = valid_rms.get(exercise['exercise_id'])
                    current_target = current_targets[(day['name'], exercise['exercise_id'])]
                    if (week['week'] > saved['cycle_week'] and not rm and exercise['weight_kg'] is not None and
                            (current_target['weight_kg'] is None or exercise['weight_kg'] > current_target['weight_kg'])):
                        raise HTTPException(422, '未来周加重需要对应动作的有效RM，请先补充或保持重量')
                    if week['week'] > saved['cycle_week'] and rm and exercise['weight_kg'] is not None and (
                            exercise['reps'] not in RM_FRACTIONS or exercise['weight_kg'] > rm['reference_1rm_kg'] * RM_FRACTIONS[exercise['reps']]):
                        raise HTTPException(422, '未来周目标超过有效RM参考，请调整后确认')
        if draft and current:
            saved['previous_cycle_id'] = current.get('cycle_id', current['id'])
        saved['next_cycle']['status'] = 'ready_for_review' if saved['cycle_complete'] else 'review_when_complete'
        if saved.get('training_program_version'):
            try:
                for week in saved['cycle_schedule']:
                    training_program.validate({**saved, 'days': week['days']}, {}, recovery=week['phase'] == 'deload')
            except ValueError as e:
                raise HTTPException(422, '训练日目标或训练法需复核：' + str(e)) from None
        db.write('plan', key, saved)
    return {'id': key, **saved, 'assessment': assess_plan(saved)}


@app.post('/api/plans/assess')
def assess_draft(plan: UserPlan):
    validate_plan_exercises(plan.model_dump())
    return assess_plan(plan.model_dump())

@app.get('/api/ai/status')
def ai_status():
    return ai_planner.status()

@app.post('/api/plans/generate')
async def generate_plan():
    return await generate_plan_for()


def validate_generated_plan(raw, effective_profile, baselines, available, strength_snapshot, training_snapshot):
    stage = 'schema'
    try:
        generated = AIPlan.model_validate(raw).model_dump()
        stage = 'program'
        training_program.validate(generated, effective_profile)
        stage = 'days_and_loads'
        planned_days = effective_profile['days']
        if len(generated['days']) != planned_days or len({d['name'] for d in generated['days']}) != planned_days:
            raise ValueError('训练日数量或名称与画像不匹配')
        allowed_ids = {e['id'] for e in available}
        for di, day in enumerate(generated['days']):
            if len(day['exercises']) > periodization.POLICY['max_daily_ai_exercises'] or len({e['exercise_id'] for e in day['exercises']}) != len(day['exercises']):
                raise ValueError(f'第{di + 1}个训练日有重复动作或动作过多')
            for ei, exercise in enumerate(day['exercises']):
                if exercise['exercise_id'] not in allowed_ids:
                    raise ValueError(f'第{di + 1}天第{ei + 1}个动作不在可用动作库中')
                try:
                    strength_profile.validate_load(exercise, strength_snapshot, baselines)
                except ValueError as error:
                    raise ValueError(f'第{di + 1}天第{ei + 1}个动作：{error}') from None
        stage = 'cycle'
        if not generated['weeks']:
            generated['weeks'] = [f'第{i + 1}周：' + ('校准动作、实际负重与余力' if i == 0 else '依据完成记录评估渐进负荷、恢复和是否需要减量') for i in range(generated['cycle_weeks'])]
        if len(generated['weeks']) != generated['cycle_weeks']:
            raise ValueError('每周说明数量与周期周数不匹配')
        generated = periodization.prepare_generated(generated, effective_profile, baselines,
            {e['id']: e for e in available}, training_snapshot, regional_strength=strength_snapshot)
        for week in generated['cycle_schedule']:
            training_program.validate({**generated, 'days': week['days']}, effective_profile, recovery=week['phase'] == 'deload')
        strength_profile.add_references(generated, strength_snapshot, baselines)
        return generated
    except (ValidationError, ValueError, KeyError, IndexError, TypeError) as error:
        raise plan_generation.InvalidPlan(stage, error) from None


async def generate_plan_for(overrides=None):
    deadline = time.monotonic() + 100
    profile = get_profile()
    if not profile:
        raise HTTPException(422, '请先保存用户画像，再生成AI计划')
    rm_snapshot = get_rm()
    with connection() as db:
        strength_snapshot = strength_profile.require_ready(db)
        private_revision=privacy.revision(db)
        coach_snapshot = coach.state(db)['facts']
        training_snapshot = workouts.model_memory(db)
        training_revision = workouts.revision(db)
        base_plan_id = (progression.active_plan(db) or {}).get('id')
        health_snapshot = health_data.summarize(db, for_ai=True)
        mobility_snapshot = mobility.summarize_for_ai(db)
        health_revision = health_data.revision(db)
        mobility_revision = mobility.revision(db)
        knowledge = research_store.active(db)
        evidence = research_store.retrieve(db, 'resistance training strength hypertrophy 力量训练 渐进负荷', release=knowledge)
        foundation = knowledge_store.context(db, '计划个体化 持续训练 渐进调整 伤病风险', limit=4)
        foundation_revision = knowledge_store.revision(db)
    effective_profile = {**profile, **coach_snapshot}
    overrides = overrides or {}
    if overrides.get('training_weekdays') is not None:
        effective_profile.update(training_weekdays=overrides['training_weekdays'], days=len(overrides['training_weekdays']))
    if overrides.get('session_minutes') is not None:
        effective_profile['session_minutes'] = overrides['session_minutes']
    if overrides.get('scope') == 'current_profile' and any(k in overrides for k in ('training_weekdays', 'session_minutes')):
        raise HTTPException(422, '临时训练日或时长请使用 this_week；长期调整请先更新画像')
    planned_days = effective_profile['days']
    training_program.check_schedule(effective_profile)
    baselines = {r['exercise_id']: r for r in rm_snapshot if r['confirmed_maximum']
        and r['reference_1rm_kg'] and 0 <= (nutrition_today() - date.fromisoformat(r['measured_on'])).days <= periodization.POLICY['rm_max_age_days']}
    painful = {e['exercise_id'] for e in training_snapshot.get('recent_discomfort', [])}
    available = [e for e in exercise_entries() if e['type'] == 'weighted' and e.get('source_kind')!='external_catalog'
        and e['id'] in strength_profile.PLAN_REGIONS and e['id'] not in painful and periodization.equipment_allowed(e, effective_profile)]
    if not available:
        raise HTTPException(422, '动作库没有可用的负重动作')
    program_contract = training_program.contract(effective_profile, [e['id'] for e in available])
    if not program_contract['splits']:
        raise HTTPException(422, '当前动作与可训练范围无法覆盖所选分化，请调整画像器械或分化偏好')
    schema = AIPlan.model_json_schema()
    # Emit one executable base week plus compact template references, rather than
    # asking the model to repeat up to 504 exercise prescriptions in one response.
    schema['properties'].pop('cycle_schedule')
    schema['$defs'].pop('CycleWeek', None)
    schema['required'].append('cycle_blueprint')
    schema['properties']['days'].update(minItems=planned_days, maxItems=planned_days)
    schema['$defs']['PlanDay']['properties']['exercises']['maxItems'] = periodization.POLICY['max_daily_ai_exercises']
    schema['$defs']['PlanDay']['required'] += list(training_program.DAY_FIELDS)
    schema['properties']['split_type']['enum'] = list(program_contract['splits'])
    schema['$defs']['PlanDay']['properties']['focus'] = {'type': 'string', 'enum': list(program_contract['focus_exercise_ids'])}
    preferred_method = effective_profile.get('training_method') or 'auto'
    schema['$defs']['PlanDay']['properties']['training_method'] = {'type': 'string', 'enum':
        list(training_program.METHODS) if preferred_method == 'auto' else [preferred_method]}
    schema['$defs']['PlanDay']['properties']['primary_exercise_id'] = {'type': 'string', 'enum': [e['id'] for e in available]}
    schema['$defs']['PlanExercise']['properties']['exercise_id']['enum'] = [e['id'] for e in available]
    schema['$defs']['PlanExercise']['properties']['weight_kg'] = {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 500,
        'description': '具体起始建议重量，不能为null；依据同动作RM、实际表现或胸背腿力量画像估计'}
    schema['x-exercise-catalog'] = [{k: e.get(k) for k in ('id', 'name', 'category', 'equipment', 'weight_basis',
        'body_regions', 'joint_actions', 'primary_muscles')} for e in available]
    def assert_snapshot_current():
        if get_profile() != profile or get_rm() != rm_snapshot:
            raise HTTPException(409, '生成过程中画像或RM已变化，请重新生成')
        with connection() as db:
            privacy.require(db,private_revision)
            current_strength = strength_profile.state(db)
            if not current_strength['ready'] or current_strength['revision'] != strength_snapshot['revision']:
                raise HTTPException(409, '生成过程中力量资料已变化，请重新生成')
            if coach.state(db)['facts'] != coach_snapshot:
                raise HTTPException(409, '生成过程中画像偏好已变化，请重新生成')
            if workouts.revision(db) != training_revision:
                raise HTTPException(409, '生成过程中训练档案已变化，请重新生成')
            if health_data.revision(db) != health_revision:
                raise HTTPException(409, '生成过程中健康数据或授权已变化，请重新生成')
            if mobility.revision(db) != mobility_revision:
                raise HTTPException(409, '生成过程中活动度数据或授权已变化，请重新生成')
            if knowledge_store.revision(db) != foundation_revision:
                raise HTTPException(409, '生成过程中基础知识或来源已变化，请重新生成')
    model_profile = {**effective_profile,
        'training_memory': training_snapshot, 'health_context': health_snapshot, 'mobility_context': mobility_snapshot,
        'published_evidence': evidence, 'knowledge_release_id': knowledge['id'], 'foundation_knowledge': foundation,
        'cycle_product_policy': periodization.POLICY, 'regional_strength': strength_snapshot,
        'training_program_contract': program_contract,
        'load_reference_policy': {'version': strength_profile.VERSION, 'kind': 'initial_proposal_only',
            'note': '跨动作仅为待校准的起始建议，不是RM或训练事实；同动作首次建议不超过已报告重量，不能在同重量增加次数。'}}
    request_id = uuid4().hex[:12]
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HTTPException(504, '生成计划超时，画像已保留，请稍后重试')
        try:
            raw, model = await asyncio.wait_for(ai_planner.generate(model_profile, baselines, schema), timeout=remaining)
        except asyncio.TimeoutError:
            raise HTTPException(504, '生成或校正计划超时，画像已保留，请稍后重试') from None
        try:
            generated = validate_generated_plan(raw, effective_profile, baselines, available, strength_snapshot, training_snapshot)
            break
        except plan_generation.InvalidPlan as error:
            logging.getLogger('lianban.plan_generation').warning(
                'plan_validation request=%s attempt=%s stage=%s rule=%s', request_id, attempt + 1, error.stage, error.rule)
            if attempt == 1 or deadline - time.monotonic() < 10:
                raise HTTPException(502, f'AI计划校验未通过：{error.reason}。请重新生成（诊断编号{request_id}）') from None
            assert_snapshot_current()
            model_profile = {**model_profile, 'generation_feedback': plan_generation.repair_feedback(raw, error)}
    if profile['restrictions'].strip():
        generated['risk_warnings'].append('已记录伤病或训练限制：' + profile['restrictions'] + '。仅作风险提示，不代表已获医疗许可；避开引起不适的动作。')
    assert_snapshot_current()
    draft = save('plan_draft', {**generated, 'training_program_version': training_program.VERSION, 'model': model, 'profile_snapshot': profile,
        'coach_profile_snapshot': coach_snapshot, 'training_revision': training_revision, 'base_plan_id': base_plan_id,
        'rm_snapshot': rm_snapshot, 'strength_revision': strength_snapshot['revision'], 'load_reference_version': strength_profile.VERSION,
        'health_revision': health_revision, 'mobility_revision':mobility_revision, 'effective_profile': effective_profile,
        'requested_schedule': overrides, 'knowledge_release_id': knowledge['id'], 'foundation_revision': foundation_revision,
        'effective_until': (nutrition_today() + timedelta(days=6-nutrition_today().weekday())).isoformat() if overrides.get('scope') == 'this_week' else None,
        'created_on': nutrition_today().isoformat()},privacy_revision=private_revision)
    return {**draft, 'generation_id': draft['id'], 'assessment': assess_plan(draft)}

def nutrition_target(profile):
    return nutrition_service.target(profile)

@app.get('/api/plans')
def get_plans():
    with connection() as db:
        history = workouts.history(db)
        facts = coach.state(db)['facts']
    return [{**periodization.normalized(p), 'cycle_status': periodization.status(p, history, facts=facts), 'assessment': assess_plan(p)}
        for p in records('plan') if p.get('source') in ('user', 'ai', 'progression')
        and (not p.get('effective_until') or p['effective_until'] >= nutrition_today().isoformat())]

@app.post('/api/meals')
def add_meal(meal: Meal):
    today = nutrition_today()
    if meal.day is not None and meal.day != today:
        raise HTTPException(422, '饮食仅支持记录当天，请刷新页面后重试')
    food = library.find_entry(connection, 'foods', meal.food_id)
    if not food:
        raise HTTPException(422, '食物不存在')
    with connection() as db:
        return nutrition_service.record_meal(db, meal.model_dump(mode='json'), food, today.isoformat())

@app.get('/api/meals')
def get_meals():
    today = nutrition_today().isoformat()
    return [item for item in records('meal') if item['day'] == today]

@app.get('/api/nutrition/today')
def nutrition_summary():
    with connection() as db:
        return nutrition_service.summary(db, nutrition_today().isoformat(), get_profile())

@app.put('/api/nutrition/diary')
def save_nutrition_diary(body: NutritionDiary):
    with connection() as db:
        db.write('nutrition_diary', nutrition_today().isoformat(), body.model_dump())
    return body

@app.delete('/api/meals/{record_id}')
def delete_meal(record_id: str):
    with connection() as db:
        existing = db.read('meal', record_id)
        if not existing:
            raise HTTPException(404, '记录不存在')
        if existing['day'] != nutrition_today().isoformat():
            raise HTTPException(422, '该记录不属于当天，请刷新当天饮食')
        nutrition_service.invalidate_diary(db, nutrition_today().isoformat())
        if not db.remove('meal', record_id):
            raise HTTPException(404, '记录不存在')
        try:from .services import privacy
        except ImportError:from services import privacy
        privacy.invalidate(db,reason='meal_source_deleted',domains={'nutrition'})
        privacy.remember_deleted(db,'meal',record_id)
    return {'deleted': True}

@app.post('/api/training')
def add_training(training: Training):
    selected = require_weighted(training.exercise_id)
    return save('training', {**training.model_dump(mode='json'), 'name': selected['name'], 'weight_basis': selected['weight_basis'],
        'feedback': '记录到不适，请停止自动加重并寻求专业评估。' if training.pain else '已记录；当前版本不会自动增加重量。'})

@app.delete('/api/training/{record_id}')
def delete_legacy_training(record_id:str):
    with connection() as db:
        db.lock_user()
        row=db.read('training',record_id)
        if not row:raise HTTPException(404,'训练记录不存在')
        if row.get('workout_id'):raise HTTPException(409,'逐组记录属于整次训练，请在训练记录中删除整次训练')
        db.remove('training',record_id)
        workouts.refresh_summaries(db)
        privacy.invalidate(db,reason='legacy_training_source_deleted',domains={'training'})
    return {'deleted':True}

@app.get('/api/training')
def get_training():
    return records('training')

def coach_context(message, *, include_foundation=True, include_evidence=True, sections=None):
    def wanted(key):return sections is None or key in sections
    exercises = exercise_entries() if wanted('exercise_catalog') or wanted('related_exercise_details') else []
    related = [e for e in exercises if any(term and term in message for term in
               [e['name'], *e.get('aliases', [])])]
    with connection() as db:
        reminder_settings = reminders.preferences(db)
        knowledge = research_store.active(db)
        data = {
        'coach_persona': {'id': reminder_settings['coach_id'], 'coach_name': reminder_settings['coach_name'], 'virtual_character': True},
        'today': nutrition_today().isoformat(),
        'knowledge_release_id': knowledge['id'],
        'video_evidence_available': False,
        }
        if wanted('reminder_settings'):data['reminder_settings']=reminder_settings
        if wanted('training_memory'):data['training_memory']=workouts.memory(db)
        if wanted('known_profile'):data['known_profile']=coach.facts(db)
        if wanted('strength_profile'):data['strength_profile']=strength_profile.state(db)
        if wanted('health_context'):data['health_context']=health_data.summarize(db,for_ai=True)
        if wanted('mobility_context'):data['mobility_context']=mobility.summarize_for_ai(db)
        if include_evidence:data['published_evidence']=research_store.retrieve(db,message,release=knowledge)
        if include_foundation:data['foundation_knowledge']=knowledge_store.context(db,message,limit=3)
    if wanted('nutrition'):data['nutrition']=nutrition_summary()
    if wanted('rm'):data['rm']=get_rm()
    if wanted('current_plan'):data['current_plan']=get_plans()[:1]
    if wanted('recent_training'):data['recent_training']=get_training()[:5]
    if wanted('exercise_catalog'):
        data['exercise_catalog']=[{k:e.get(k) for k in
            ('id','name','type','movement_pattern','body_regions','weight_basis','realtime_supported')}
            for e in exercises if e.get('source_kind')!='external_catalog']
    if wanted('related_exercise_details'):
        data['related_exercise_details']=[{k:e.get(k) for k in
            ('id','name','joint_actions','primary_muscles','secondary_muscles','technique','content_version')}
            for e in related[:3]]
    return data

app.include_router(health_data.router(connection))
app.include_router(nutrition_guidance.router(connection))
app.include_router(mobility.router(connection))
app.include_router(coach.router(connection, Profile, coach_context))
app.include_router(reminders.router(connection, Profile))
app.include_router(workouts.router(connection, require_weighted, coach_context))
app.include_router(progression.router(connection, get_profile, get_rm, assess_plan))
app.include_router(periodization.router(connection, get_profile, get_rm, assess_plan))
review_workout = workouts.review_service(connection, require_weighted, coach_context)
progress_workout = progression.progress_service(connection, get_profile, get_rm, assess_plan)

def agent_save_workout(body):
    with connection() as db:
        db.lock_user()
        return workouts.save_workout(db, body, require_weighted)

agent_service = agent.AgentService(connection, lambda message,sections=None: coach_context(message,
    include_foundation=False,include_evidence=False,sections=sections), {
    'meal_model': Meal, 'plan_model': UserPlan, 'generate_plan': generate_plan_for,
    'save_meal': add_meal, 'save_plan': save_user_plan, 'save_workout': agent_save_workout}, Profile)
app.include_router(agent.router(agent_service))
app.include_router(research.router(connection))
app.include_router(knowledge.router(connection))

@app.post('/api/media')
async def upload_media(kind: Literal['meal', 'video'] = Form(...), exercise_id: str = Form(''), file: UploadFile = File(...)):
    if kind == 'video':
        require_weighted(exercise_id)
    allowed = {'meal': {'image/jpeg': '.jpg', 'image/png': '.png'},
               'video': {'video/mp4': '.mp4', 'video/quicktime': '.mov'}}
    suffix = allowed[kind].get(file.content_type)
    if not suffix:
        raise HTTPException(415, '支持 JPG/PNG 图片或 MP4/MOV 视频')
    limit = (10 if kind == 'meal' else 100) * 1024 * 1024
    media_dir = DATA / 'uploads'
    media_dir.mkdir(exist_ok=True)
    key = str(uuid4())
    target = media_dir / (key + suffix)
    size = 0
    try:
        with target.open('wb') as stream:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, '文件超过大小限制')
                stream.write(chunk)
        if not size:
            raise HTTPException(422, '文件为空')
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    try:
        return save('media', {'kind': kind, 'exercise_id': exercise_id, 'bytes': size,
            'status': 'awaiting_integration', 'message': '文件已保存。识别模型尚未接入，未生成分析结果。',
            'stored_name': target.name}, key)
    except Exception:
        target.unlink(missing_ok=True)
        raise

@app.get('/api/media')
def get_media():
    return records('media')

@app.get('/api/media/{media_id}/file')
def download_media(media_id: str):
    with connection() as db:
        media = db.read('media', media_id)
    if not media:
        raise HTTPException(404, '文件不存在')
    root = (DATA / 'uploads').resolve()
    target = (root / media['stored_name']).resolve()
    if target.parent != root or not target.is_file():
        raise HTTPException(404, '文件不存在')
    return FileResponse(target)

@app.get('/api/movement/status')
def movement_status():
    return movement_analysis.status()

@app.post('/api/movement/analyze')
async def analyze_movement(request: movement_analysis.AnalysisRequest):
    entry = library.find_entry(connection, 'exercises', request.exercise_id)
    if not entry:
        raise HTTPException(422, '动作不存在或已停用')
    with connection() as db:
        foundation = knowledge_store.context(db, entry['name']+' 视频可见性 活动度', limit=3)
    result = await movement_analysis.analyze(entry, request, foundation=foundation)
    result['foundation_version'] = foundation['version']
    # Only the text/evidence references are saved; raw images are not kept by this endpoint.
    return save('movement_analysis', {**result, 'exercise_id':entry['id'], 'exercise_name':entry['name'],
        'created_on':nutrition_today().isoformat()})

@app.get('/api/media/{media_id}/analysis-context')
def media_analysis_context(media_id: str):
    media = next((m for m in records('media') if m['id']==media_id and m['kind']=='video'), None)
    if not media:
        raise HTTPException(404, '训练录像不存在')
    entry = library.find_entry(connection, 'exercises', media['exercise_id'])
    if not entry:
        raise HTTPException(422, '录像对应动作已停用')
    return library.exercise_content.analysis_context(entry)

try:
    from . import progression_settings, training_trends, catalog_content, external_foods
except ImportError:
    import progression_settings, training_trends, catalog_content, external_foods
app.include_router(progression_settings.router(connection))
app.include_router(training_trends.router(connection))
app.include_router(catalog_content.router(connection))
app.include_router(external_foods.router(connection))

app.mount('/assets', StaticFiles(directory=ROOT/'backend/assets'), name='assets')

flutter_web = ROOT / 'mobile' / 'build' / 'web'
if flutter_web.exists():
    app.mount('/app', StaticFiles(directory=flutter_web, html=True), name='flutter')
@app.get('/', include_in_schema=False)
def index():
    if flutter_web.exists():
        return RedirectResponse('/app/')
    return HTMLResponse('<!doctype html><meta charset="utf-8"><title>练伴</title>'
        '<h1>练伴</h1><p>后端已运行，请使用安卓 App 登录。浏览器端需先构建 Flutter Web。</p>')
