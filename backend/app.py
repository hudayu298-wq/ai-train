"""LiftLab API with account authentication and owner-scoped storage."""
import json
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
    from . import ai_planner, library, movement_analysis, coach, reminders, workouts, database, auth, progression
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

def save(kind, payload, key=None):
    key = key or str(uuid4())
    with connection() as db:
        db.write(kind, key, payload)
    return {'id': key, **payload}

def records(kind):
    with connection() as db:
        return db.records(kind)

app = FastAPI(title='练伴 API', version='0.2.0',
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
    exercise_id: str = Field(min_length=1, max_length=80)
    weight_kg: float | None = Field(gt=0, le=500)
    sets: int = Field(ge=1, le=20)
    reps: int = Field(ge=1, le=100)
    rest_seconds: int = Field(ge=0, le=1800)

class PlanDay(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r'.*\S.*')
    exercises: list[PlanExercise] = Field(min_length=1, max_length=20)
    weekday: int | None = Field(default=None, ge=1, le=7)
    start_time: str | None = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    duration_minutes: int | None = Field(default=None, ge=15, le=180)

class UserPlan(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r'.*\S.*')
    days: list[PlanDay] = Field(min_length=1, max_length=7)
    generation_id: str | None = None
    base_plan_id: str | None = None

class AIPlan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=80)
    days: list[PlanDay] = Field(min_length=1, max_length=7)
    rationale: str = Field(min_length=1, max_length=1500)
    warmup: str = Field(min_length=1, max_length=1000)
    recovery: str = Field(min_length=1, max_length=1000)
    progression: str = Field(min_length=1, max_length=1000)
    cycle_weeks: int = Field(default=4, ge=2, le=12)
    weeks: list[str] = Field(default_factory=list, max_length=12)
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

@app.get('/api/catalog')
def catalog(extended: bool = False):
    # Older installed clients assume every returned exercise has a live detector.
    exercises = exercise_entries()
    if not extended:
        exercises = [e for e in exercises if e.get('realtime_supported')]
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
    generation_id = payload.pop('generation_id')
    base_plan_id = payload.pop('base_plan_id')
    validate_plan_exercises(payload)
    with connection() as db:
        db.lock_user()
        current = progression.active_plan(db)
        draft = db.read('plan_draft', generation_id) if generation_id else None
        if generation_id and not draft:
            raise HTTPException(422, 'AI草稿不存在，请重新生成')
        if generation_id:
            existing = next((p for p in db.records('plan') if p.get('generation_id') == generation_id), None)
            if existing:
                if existing['name'] != payload['name'] or progression.day_inputs(existing['days']) != progression.day_inputs(payload['days']):
                    raise HTTPException(409, '该草稿已确认，修改当前计划请使用编辑入口')
                return {**existing, 'assessment': assess_plan(existing)}
            if draft['profile_snapshot'] != get_profile() or draft['rm_snapshot'] != get_rm():
                raise HTTPException(409, '画像或RM已变化，请重新生成AI计划')
            if draft.get('coach_profile_snapshot') != coach.state(db)['facts']:
                raise HTTPException(409, '画像偏好已变化，请重新生成AI计划')
            if draft.get('training_revision') != workouts.revision(db):
                raise HTTPException(409, '训练档案已变化，请重新生成AI计划')
            if draft.get('base_plan_id') != (current or {}).get('id'):
                raise HTTPException(409, '当前计划已更新，请重新生成')
        if base_plan_id and (not current or current['id'] != base_plan_id):
            raise HTTPException(409, '当前计划已更新，请刷新后修改')
        metadata_source = draft or (current if base_plan_id else {}) or {}
        metadata = {k: metadata_source[k] for k in ('rationale', 'warmup', 'recovery', 'progression', 'model',
            'profile_snapshot', 'rm_snapshot', 'coach_profile_snapshot', 'cycle_weeks', 'weeks', 'risk_warnings') if k in metadata_source}
        names = {e['id']: e['name'] for e in exercise_entries()}
        for day in payload['days']:
            if len({e['exercise_id'] for e in day['exercises']}) != len(day['exercises']):
                raise HTTPException(422, '同一训练日不能重复添加同一动作')
            for exercise in day['exercises']:
                exercise['name'] = names[exercise['exercise_id']]
        if draft and len(payload['days']) != draft['profile_snapshot']['days']:
            raise HTTPException(422, '确认计划的训练日数量需与画像一致')
        key = str(uuid4())
        saved = {**payload, **metadata, 'generation_id': generation_id,
            'base_plan_id': (current or {}).get('id'), 'version': (current or {}).get('version', 0) + 1,
            'cycle_id': current.get('cycle_id', current['id']) if base_plan_id else key,
            'cycle_week': current.get('cycle_week', 1) if base_plan_id else 1,
            'created_on': nutrition_today().isoformat(), 'source': 'ai' if draft else 'user',
            'note': 'AI生成、用户确认的训练计划。' if draft else '用户确认修改的训练计划。'}
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
    profile = get_profile()
    if not profile:
        raise HTTPException(422, '请先保存用户画像，再生成AI计划')
    rm_snapshot = get_rm()
    with connection() as db:
        coach_snapshot = coach.state(db)['facts']
        training_snapshot = workouts.memory(db)
        training_revision = workouts.revision(db)
        base_plan_id = (progression.active_plan(db) or {}).get('id')
    baselines = {r['exercise_id']: r for r in rm_snapshot if r['confirmed_maximum']
        and r['reference_1rm_kg'] and (nutrition_today() - date.fromisoformat(r['measured_on'])).days <= 90}
    available = [e for e in exercise_entries() if e['type'] == 'weighted']
    if not available:
        raise HTTPException(422, '动作库没有可用的负重动作')
    schema = AIPlan.model_json_schema()
    schema['properties']['days'].update(minItems=profile['days'], maxItems=profile['days'])
    schema['$defs']['PlanDay']['properties']['exercises']['maxItems'] = 6
    schema['$defs']['PlanExercise']['properties']['exercise_id']['enum'] = [e['id'] for e in available]
    schema['x-exercise-catalog'] = [{k: e.get(k) for k in ('id', 'name', 'category', 'equipment', 'weight_basis',
        'body_regions', 'joint_actions', 'primary_muscles')} for e in available]
    raw, model = await ai_planner.generate({**profile, **coach_snapshot,
        'training_memory': training_snapshot}, baselines, schema)
    try:
        generated = AIPlan.model_validate(raw).model_dump()
        if len(generated['days']) != profile['days'] or len({d['name'] for d in generated['days']}) != profile['days']:
            raise ValueError('训练日与画像不匹配')
        for day in generated['days']:
            if len(day['exercises']) > 6 or len({e['exercise_id'] for e in day['exercises']}) != len(day['exercises']):
                raise ValueError('动作重复或过多')
            for e in day['exercises']:
                if e['exercise_id'] not in {x['id'] for x in available}:
                    raise ValueError('动作不在可用库中')
                rm = baselines.get(e['exercise_id'])
                if not rm:
                    e['weight_kg'] = None
                elif e['weight_kg'] is not None and (e['reps'] not in RM_FRACTIONS or
                        e['weight_kg'] > rm['reference_1rm_kg'] * RM_FRACTIONS[e['reps']]):
                    raise ValueError('重量超出RM参考')
    except (ValidationError, ValueError, TypeError):
        raise HTTPException(502, 'AI计划不符合动作、训练日或负荷要求，请重新生成') from None
    weekdays = coach_snapshot.get('training_weekdays', [])
    for index, day in enumerate(generated['days']):
        if len(weekdays) == profile['days']:
            day['weekday'] = weekdays[index]
            day['name'] = '周' + '一二三四五六日'[weekdays[index] - 1] + f' · 训练{index + 1}'
        day['start_time'] = coach_snapshot.get('preferred_time')
        day['duration_minutes'] = coach_snapshot.get('session_minutes')
        if day['duration_minutes']:
            estimate = 300 + sum(e['sets'] * e['reps'] * 4 + max(0, e['sets'] - 1) * e['rest_seconds'] + 60 for e in day['exercises'])
            if estimate > day['duration_minutes'] * 60:
                raise HTTPException(502, 'AI计划的预计用时超出可训练时间，请重试或调整单次时长')
    if not generated['weeks']:
        generated['weeks'] = [f'第{i + 1}周：' + ('校准动作、实际负重与余力' if i == 0 else '依据完成记录评估渐进负荷、恢复和是否需要减量') for i in range(generated['cycle_weeks'])]
    if len(generated['weeks']) != generated['cycle_weeks']:
        raise HTTPException(502, 'AI周期安排与周期长度不匹配，请重试')
    if profile['restrictions'].strip():
        generated['risk_warnings'].append('已记录伤病或训练限制：' + profile['restrictions'] + '。仅作风险提示，不代表已获医疗许可；避开引起不适的动作。')
    if get_profile() != profile or get_rm() != rm_snapshot:
        raise HTTPException(409, '生成过程中画像或RM已变化，请重新生成')
    with connection() as db:
        if coach.state(db)['facts'] != coach_snapshot:
            raise HTTPException(409, '生成过程中画像偏好已变化，请重新生成')
        if workouts.revision(db) != training_revision:
            raise HTTPException(409, '生成过程中训练档案已变化，请重新生成')
    draft = save('plan_draft', {**generated, 'model': model, 'profile_snapshot': profile,
        'coach_profile_snapshot': coach_snapshot, 'training_revision': training_revision, 'base_plan_id': base_plan_id,
        'rm_snapshot': rm_snapshot, 'created_on': nutrition_today().isoformat()})
    return {**draft, 'generation_id': draft['id'], 'assessment': assess_plan(draft)}

def nutrition_target(profile):
    bmr = 10 * profile['weight_kg'] + 6.25 * profile['height_cm'] - 5 * profile['age'] + (5 if profile['sex'] == 'male' else -161)
    kcal = round(bmr * 1.4 + (-250 if profile['goal'] == 'fat_loss' else 200))
    protein = round(profile['weight_kg'] * 1.6)
    fat = round(profile['weight_kg'] * 0.8)
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return {'kcal': kcal, 'protein': protein, 'fat': fat, 'carbs': carbs}

@app.get('/api/plans')
def get_plans():
    return [{**p, 'assessment': assess_plan(p)} for p in records('plan') if p.get('source') in ('user', 'ai', 'progression')]

@app.post('/api/meals')
def add_meal(meal: Meal):
    today = nutrition_today()
    if meal.day is not None and meal.day != today:
        raise HTTPException(422, '饮食仅支持记录当天，请刷新页面后重试')
    food = library.find_entry(connection, 'foods', meal.food_id)
    if not food:
        raise HTTPException(422, '食物不存在')
    return save('meal', {**meal.model_dump(mode='json'), 'day': today.isoformat(), 'name': food['name'], 'food_state': food['state'], 'food_source': food['source_label'],
        'nutrients': {k: float((Decimal(str(food[k])) * Decimal(str(meal.grams)) / 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) for k in ['kcal', 'protein', 'fat', 'carbs']},
        'source': food.get('source_kind', 'user')})

@app.get('/api/meals')
def get_meals():
    today = nutrition_today().isoformat()
    return [item for item in records('meal') if item['day'] == today]

@app.get('/api/nutrition/today')
def nutrition_summary():
    today = nutrition_today().isoformat()
    items = [item for item in records('meal') if item['day'] == today]
    totals = nutrient_totals(items)
    groups = []
    for kind, label in MEAL_LABELS.items():
        entries = [item for item in items if item.get('meal_type', 'unassigned') == kind]
        if kind == 'unassigned' and not entries:
            continue
        groups.append({'meal_type': kind, 'label': label, 'items': entries, 'totals': nutrient_totals(entries)})
    profile = get_profile()
    target_status = 'missing'
    target = None
    if profile:
        target = nutrition_target(profile)
        target_status = 'ready'
    comparisons = {}
    for key in NUTRIENTS:
        goal = target[key] if target else None
        delta = round(totals[key] - goal, 1) if goal is not None else None
        comparisons[key] = {'consumed': totals[key], 'target': goal,
            'remaining': max(0, -delta) if delta is not None else None,
            'excess': max(0, delta) if delta is not None else None,
            'percent': round(totals[key] / goal * 100, 1) if goal and goal > 0 else None}
    return {'day': today, 'timezone': 'Asia/Shanghai', 'records': items, 'groups': groups,
            'totals': totals, 'target': target, 'target_status': target_status, 'comparison': comparisons}

@app.delete('/api/meals/{record_id}')
def delete_meal(record_id: str):
    with connection() as db:
        existing = db.read('meal', record_id)
        if not existing:
            raise HTTPException(404, '记录不存在')
        if existing['day'] != nutrition_today().isoformat():
            raise HTTPException(422, '该记录不属于当天，请刷新当天饮食')
        if not db.remove('meal', record_id):
            raise HTTPException(404, '记录不存在')
    return {'deleted': True}

@app.post('/api/training')
def add_training(training: Training):
    selected = require_weighted(training.exercise_id)
    return save('training', {**training.model_dump(mode='json'), 'name': selected['name'], 'weight_basis': selected['weight_basis'],
        'feedback': '记录到不适，请停止自动加重并寻求专业评估。' if training.pain else '已记录；当前版本不会自动增加重量。'})

@app.get('/api/training')
def get_training():
    return records('training')

def coach_context(message):
    exercises = exercise_entries()
    related = [e for e in exercises if any(term and term in message for term in
               [e['name'], *e.get('aliases', [])])]
    with connection() as db:
        reminder_settings = reminders.preferences(db)
        training_memory = workouts.memory(db)
        known_profile = coach.state(db)['facts']
    return {
        'coach_persona': {'id': reminder_settings['coach_id'], 'coach_name': reminder_settings['coach_name'], 'virtual_character': True},
        'reminder_settings': reminder_settings,
        'today': nutrition_today().isoformat(),
        'nutrition': nutrition_summary(), 'rm': get_rm(),
        'current_plan': get_plans()[:1], 'recent_training': get_training()[:5],
        'training_memory': training_memory,
        'known_profile': known_profile,
        'exercise_catalog': [{k: e.get(k) for k in
            ('id', 'name', 'type', 'movement_pattern', 'body_regions', 'weight_basis', 'realtime_supported')}
            for e in exercises],
        'related_exercise_details': [{k: e.get(k) for k in
            ('id', 'name', 'joint_actions', 'primary_muscles', 'secondary_muscles', 'technique', 'content_version')}
            for e in related[:3]],
        'video_evidence_available': False,
    }

app.include_router(coach.router(connection, Profile, coach_context))
app.include_router(reminders.router(connection, Profile))
app.include_router(workouts.router(connection, require_weighted, coach_context))
app.include_router(progression.router(connection, get_profile, get_rm, assess_plan))

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
    result = await movement_analysis.analyze(entry, request)
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
