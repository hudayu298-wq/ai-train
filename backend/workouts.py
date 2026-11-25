"""Confirmed workout history, factual profile memory and grounded reviews."""
import hashlib
import json
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

try:
    from . import ai_planner, coaches
    from .services import privacy
except ImportError:
    import ai_planner
    import coaches
    from services import privacy


def today():
    return datetime.now(timezone(timedelta(hours=8))).date()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class WorkSet(StrictModel):
    weight_kg: float = Field(ge=0, le=500)
    reps: int = Field(ge=1, le=100, strict=True)
    rpe: float = Field(ge=1, le=10)
    pain: bool = False
    set_type: Literal['working', 'warmup'] = 'working'
    assisted: bool = False
    rest_seconds: int | None = Field(default=None, ge=0, le=1800, strict=True)
    rir: int | None = Field(default=None, ge=0, le=10, strict=True)


class WorkExercise(StrictModel):
    exercise_id: str = Field(min_length=1, max_length=80)
    sets: list[WorkSet] = Field(min_length=1, max_length=20)
    notes: str = Field(default='', max_length=500)
    detected_reps: int | None = Field(default=None, ge=0, le=10000, strict=True)
    equipment_id: str = Field(default='', max_length=100)
    load_basis: Literal['catalog', 'total', 'per_hand', 'machine_display'] = 'catalog'
    discomfort_area: str = Field(default='', max_length=150)


class Workout(StrictModel):
    execution_id: str | None = Field(default=None, max_length=100)
    execution_groups: list[list[str]] = Field(default_factory=list, max_length=10)
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    day: date = Field(default_factory=today)
    duration_minutes: int | None = Field(default=None, ge=1, le=600, strict=True)
    exercises: list[WorkExercise] = Field(min_length=1, max_length=20)
    notes: str = Field(default='', max_length=1500)
    source: Literal['manual', 'live_confirmed'] = 'manual'
    plan_id: str | None = Field(default=None, max_length=100)
    plan_day: str | None = Field(default=None, max_length=80)
    completed_plan_day: bool = False
    readiness: Literal['good', 'normal', 'poor'] = 'normal'
    completion_reason: Literal['unknown', 'as_planned', 'time', 'equipment', 'fatigue', 'discomfort', 'other'] = 'unknown'
    completion_notes: str = Field(default='', max_length=500)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @model_validator(mode='after')
    def valid_times(self):
        grouped = [key for group in self.execution_groups for key in group]
        if any(not 2 <= len(group) <= 4 for group in self.execution_groups) or len(set(grouped)) != len(grouped) or not set(grouped) <= {e.exercise_id for e in self.exercises}:
            raise ValueError('交替组须由2至4个互不重复的本次训练动作组成')
        for value in (self.started_at, self.ended_at):
            if value and (value.tzinfo is None or value > datetime.now(timezone.utc)):
                raise ValueError('实际时间必须带时区且不能在未来')
        if bool(self.started_at) != bool(self.ended_at):
            raise ValueError('开始和结束时间须同时提供')
        if self.started_at and (self.ended_at <= self.started_at or self.started_at.astimezone(timezone(timedelta(hours=8))).date() != self.day):
            raise ValueError('实际时间与训练日期不一致')
        if self.completed_plan_day and self.completion_reason not in ('unknown', 'as_planned'):
            raise ValueError('已完成训练日与未完成原因矛盾')
        return self


class ReviewRequest(StrictModel):
    coach_id: coaches.CoachId = 'steady'


class AIReview(StrictModel):
    summary: str = Field(min_length=1, max_length=1500)
    strengths: list[str] = Field(min_length=1, max_length=4)
    next_steps: list[str] = Field(min_length=1, max_length=5)


def read(db, kind, key):
    return db.read(kind, key)


def write(db, kind, key, payload):
    db.write(kind, key, payload, replace=False)


def history(db):
    items = db.records('workout')
    # Older installed apps still write one exercise at a time. Expose those
    # records as legacy entries, without copying or counting linked rows twice.
    rows = db.records('training')
    for row in rows:
        value = row
        if value.get('workout_id'):
            continue
        items.append({'id': row['id'], 'day': value['day'], 'source': 'legacy',
            'created_at': '', 'duration_minutes': None, 'notes': '',
            'exercises': [{'exercise_id': value['exercise_id'], 'name': value.get('name', value['exercise_id']),
                'weight_basis': value.get('weight_basis', ''), 'notes': '', 'detected_reps': None,
                'sets': [{k: value[k] for k in ('weight_kg', 'reps', 'rpe', 'pain')} for _ in range(value['sets'])]}]})
    return sorted(items, key=lambda w: (w['day'], w.get('created_at', '')), reverse=True)


def stats(exercise):
    sets = [s for s in exercise['sets'] if s.get('set_type', 'working') == 'working']
    return {'sets': len(sets), 'reps': sum(s['reps'] for s in sets),
        'volume_kg': round(sum(s['weight_kg'] * s['reps'] for s in sets), 1),
        'average_rpe': round(sum(s['rpe'] for s in sets) / len(sets), 1) if sets else None,
        'max_rpe': max((s['rpe'] for s in sets), default=0),
        'warmup_sets': len(exercise['sets']) - len(sets),
        'pain': any(s['pain'] for s in exercise['sets']),
        'assisted_sets': sum(bool(s.get('assisted')) for s in sets)}


def target_comparison(workout):
    """Targets come only from the server snapshot taken at record confirmation."""
    plan = workout.get('plan_snapshot')
    if not plan:
        return None
    day = next((d for d in plan.get('days', []) if d['name'] == workout.get('plan_day')), None)
    if not day:
        return None
    actual = {e['exercise_id']: e for e in workout['exercises']}
    rows = []
    for prescribed in day['exercises']:
        exercise = actual.get(prescribed['exercise_id'], {})
        sets = [s for s in exercise.get('sets', []) if s.get('set_type', 'working') == 'working']
        for index in range(max(prescribed['sets'], len(sets))):
            target = {k: prescribed.get(k) for k in ('weight_kg', 'reps', 'target_rir', 'rest_seconds')} if index < prescribed['sets'] else None
            performed = sets[index] if index < len(sets) else None
            comparable = exercise.get('load_basis', 'catalog') == 'catalog' and not exercise.get('equipment_id')
            delta = {}
            if target and performed:
                for key in ('reps', 'rest_seconds'):
                    if target.get(key) is not None and performed.get(key) is not None:
                        delta[key] = round(performed[key] - target[key], 2)
                if comparable and target.get('weight_kg') is not None:
                    delta['weight_kg'] = round(performed['weight_kg'] - target['weight_kg'], 2)
                if target.get('target_rir') is not None and performed.get('rir') is not None:
                    delta['rir'] = performed['rir'] - target['target_rir']
            status = 'extra_set' if target is None else 'not_recorded' if performed is None else 'recorded'
            rows.append({'exercise_id': prescribed['exercise_id'], 'set_number': index + 1,
                'target': target, 'actual': performed, 'delta': delta,
                'weight_comparable': bool(comparable), 'status': status})
    return {'basis': 'server_plan_at_start' if workout.get('execution_id') else 'server_plan_at_confirmation', 'plan_id': workout.get('plan_id'),
        'plan_version': plan.get('version', 1), 'cycle_week': plan.get('cycle_week', 1),
        'plan_day': workout.get('plan_day'), 'sets': rows,
        'planned_sets': sum(d['sets'] for d in day['exercises']),
        'recorded_planned_sets': sum(r['target'] is not None and r['actual'] is not None for r in rows),
        'note': ('目标取自开练时冻结的计划版本；' if workout.get('execution_id') else '目标取自确认保存时的计划版本；') + '按工作组顺序对照。记录组数不代表达标，热身组不占目标组；未记录不等于确认未训练。不同口径或注明器械编号时不比较重量。'}


def period_stats(items):
    """Twenty-eight calendar days, descriptive facts grouped by exact load identity."""
    first = today() - timedelta(days=27)
    sessions = [w for w in items if first <= date.fromisoformat(w['day']) <= today()]
    groups = {}
    for workout in sessions:
        for e in workout['exercises']:
            key = (e['exercise_id'], e.get('weight_basis', ''), e.get('load_basis', 'catalog'), e.get('equipment_id', ''))
            value = groups.setdefault(key, {'exercise_id': key[0], 'name': e['name'],
                'weight_basis': key[1], 'load_basis': key[2], 'equipment_id': key[3],
                'working_sets': 0, 'reps': 0, 'volume_kg': 0, 'pain_sets': 0})
            sets = [s for s in e['sets'] if s.get('set_type', 'working') == 'working']
            value['working_sets'] += len(sets)
            value['reps'] += sum(s['reps'] for s in sets)
            value['volume_kg'] = round(value['volume_kg'] + sum(s['weight_kg'] * s['reps'] for s in sets), 1)
            value['pain_sets'] += sum(bool(s.get('pain')) for s in sets)
    return {'from': first.isoformat(), 'through': today().isoformat(),
        'sessions': len(sessions), 'training_days': len({w['day'] for w in sessions}),
        'working_sets': sum(g['working_sets'] for g in groups.values()),
        'by_exercise': list(groups.values()),
        'note': '按确认记录统计，热身组不计入工作组；不同动作、器械及重量口径分开，不推断RM、热量或肌肉增长。'}


def summarize(workout, prior):
    items = []
    for exercise in workout['exercises']:
        current = stats(exercise)
        previous_session = next((w for w in prior if w['day'] <= workout['day'] and
            any(e['exercise_id'] == exercise['exercise_id'] and
                e.get('weight_basis', '') == exercise.get('weight_basis', '') and
                e.get('load_basis', 'catalog') == exercise.get('load_basis', 'catalog') and
                e.get('equipment_id', '') == exercise.get('equipment_id', '') for e in w['exercises'])), None)
        previous = next((e for e in previous_session['exercises'] if e['exercise_id'] == exercise['exercise_id']), None) if previous_session else None
        comparison = None
        if previous:
            before = stats(previous)
            # Compare only the exact variant. Volume is descriptive, never proof
            # of strength gain, form quality, plan completion or a new RM.
            comparison = {'workout_id': previous_session['id'], 'day': previous_session['day'],
                'volume_delta_kg': round(current['volume_kg'] - before['volume_kg'], 1),
                'previous': before}
        if current['pain']:
            advice = '本次记录有疼痛或不适。暂停引起不适的动作，不按本次表现加重；持续或明显不适时寻求专业评估。'
        elif current['max_rpe'] >= 9:
            advice = '本次主观用力较高。下次先确认恢复和动作控制，保留余力；先复核或减少重量/组数，不自动加重。'
        else:
            advice = '下次先以本次记录作参考，确认恢复、无不适及动作可控后再评估调整；单次记录不足以确定加重量。'
        items.append({'exercise_id': exercise['exercise_id'], 'name': exercise['name'],
            'weight_basis': exercise.get('weight_basis', ''), **current,
            'comparison': comparison, 'next_step': advice})
    total_sets = sum(e['sets'] for e in items)
    total_reps = sum(e['reps'] for e in items)
    return {'version': 'workout-rules-2', 'source': 'record_rules',
        'summary': f"已记录{len(items)}个动作、{total_sets}组、{total_reps}次。",
        'total_sets': total_sets, 'total_reps': total_reps,
        'total_volume_kg': round(sum(e['volume_kg'] for e in items), 1),
        'has_pain': any(e['pain'] for e in items), 'exercises': items,
        'target_comparison': target_comparison(workout),
        'note': '依据用户确认记录计算；总训练量只作同动作同口径参考，不代表动作质量、热量消耗、力量提升或新的RM。'}


def memory(db):
    return db.cached_user('training_memory',[today().isoformat()],lambda:_memory(db))


def _memory(db):
    all_items = history(db)
    if not all_items:
        return {'session_count': 0, 'training_days_last_28': 0, 'last_training_day': None,
                'total_sets': 0, 'exercise_progress': [], 'recent_sessions': [], 'recent_discomfort': [],
                'last_28_days': period_stats([])}
    recent = [w for w in all_items if today() - timedelta(days=27) <= date.fromisoformat(w['day']) <= today()]
    progress = {}
    discomfort = []
    for w in all_items:
        for e in w['exercises']:
            if e['exercise_id'] not in progress:
                progress[e['exercise_id']] = {'exercise_id': e['exercise_id'], 'name': e['name'],
                    'last_day': w['day'], **stats(e),
                    'last_sets': e['sets'], 'weight_basis': e.get('weight_basis', ''),
                    'source_workout_id': w['id']}
            if w in recent and stats(e)['pain']:
                discomfort.append({'day': w['day'], 'exercise_id': e['exercise_id'], 'name': e['name'],
                                    'source_workout_id': w['id']})
    return {'session_count': len(all_items), 'last_28_days': period_stats(all_items), 'training_days_last_28': len({w['day'] for w in recent}),
        'last_training_day': all_items[0]['day'],
        'total_sets': sum(stats(e)['sets'] for w in all_items for e in w['exercises']),
        'exercise_progress': list(progress.values()), 'recent_discomfort': discomfort[:20],
        'recent_sessions': [{k: w.get(k) for k in
            ('id', 'day', 'duration_minutes', 'source', 'notes', 'exercises', 'summary', 'ai_review',
             'completion_reason', 'completion_notes', 'readiness', 'plan_id', 'plan_day', 'completed_plan_day')} for w in all_items[:8]],
        'note': '已确认训练记录形成的动态档案；AI建议不等同于用户事实，训练量不等同于进步，不自动修改经验等级、训练限制或RM。'}


def model_memory(db):
    value=memory(db)
    for session in value.get('recent_sessions',[]):
        session.pop('ai_review',None)
    return value


def revision(db):
    return hashlib.sha256(json.dumps(memory(db), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_workout(db, request, require_weighted):
    db.lock_user()
    key = 'workout-' + request.request_id
    privacy.require_not_deleted(db,'workout',key)
    payload = request.model_dump(mode='json')
    existing = read(db, 'workout', key)
    if existing:
        if Workout.model_validate(existing['input']).model_dump(mode='json') != payload:
            raise HTTPException(409, '请求编号已用于其他训练记录')
        return {'id': key, **existing}
    if request.day > today():
        raise HTTPException(422, '已完成训练的日期不能晚于今天')
    if len({e.exercise_id for e in request.exercises}) != len(request.exercises):
        raise HTTPException(422, '同一动作请合并到一条记录的各组中')
    exercises = []
    plan_snapshot = None
    if (request.plan_id or request.plan_day) and not request.execution_id:
        plan_snapshot = db.read('plan', request.plan_id or '')
        if not plan_snapshot or request.plan_day not in {d['name'] for d in plan_snapshot['days']}:
            raise HTTPException(422, '关联计划或训练日不存在，请刷新当前计划')
    execution = None
    if request.execution_id:
        execution = db.read('workout_execution', request.execution_id)
        if not execution:
            raise HTTPException(404, '开练快照不存在或不属于当前账户')
        if execution.get('workout_id') and execution['workout_id'] != key:
            raise HTTPException(409, '该开练快照已用于另一条训练，原记录保留')
        if datetime.fromisoformat(execution['started_at']).astimezone(timezone(timedelta(hours=8))).date() != request.day:
            raise HTTPException(409, '训练日期与开练快照不一致，历史补录请解除冻结后重新核对')
        if execution['plan_id'] != request.plan_id or execution['plan_day'] != request.plan_day:
            raise HTTPException(409, '关联训练日与开练快照不一致，请保留原关联或重新开练')
        plan_snapshot = execution['plan_snapshot']
    for e in request.exercises:
        entry = require_weighted(e.exercise_id)
        exercises.append({**e.model_dump(), 'name': entry['name'], 'weight_basis': entry['weight_basis']})
    result = {**payload, 'input': payload, 'exercises': exercises, 'plan_snapshot': plan_snapshot,
        'created_at': datetime.now(timezone.utc).isoformat(), 'ai_review': None}
    result['summary'] = summarize(result, history(db))
    write(db, 'workout', key, result)
    if execution is not None:
        db.write('workout_execution', request.execution_id, {**execution, 'workout_id': key})
    # Preserve old-client training history without a second memory entry.
    for i, e in enumerate(exercises):
        for j, s in enumerate(e['sets']):
            write(db, 'training', f'{key}-{i}-{j}', {**s, 'sets': 1,
                'exercise_id': e['exercise_id'], 'name': e['name'], 'day': payload['day'],
                'weight_basis': e['weight_basis'], 'workout_id': key,
                'feedback': result['summary']['exercises'][i]['next_step']})
    return {'id': key, **result}


class StartExecution(StrictModel):
    day: date = Field(default_factory=today)
    plan_id: str = Field(min_length=1,max_length=100)
    plan_day: str = Field(min_length=1,max_length=80)
    request_id: str = Field(min_length=8,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')


def refresh_summaries(db):
    """Rebuild copied historical comparisons from remaining confirmed facts."""
    prior=[]
    for row in reversed(history(db)):
        if row.get('source')=='legacy':
            prior.insert(0,row)
            continue
        value={k:v for k,v in row.items() if k!='id'}
        value['summary']=summarize(value,prior)
        db.write('workout',row['id'],value)
        prior.insert(0,{'id':row['id'],**value})


def delete_workout(db,key):
    db.lock_user()
    if not db.read('workout',key):raise HTTPException(404,'训练记录不存在')
    db.remove('workout',key)
    for row in db.records('training'):
        if row.get('workout_id')==key:db.remove('training',row['id'])
    for row in db.records('workout_execution'):
        if row.get('workout_id')==key:db.remove('workout_execution',row['id'])
    refresh_summaries(db)
    privacy.remember_deleted(db,'workout',key)
    privacy.invalidate(db,reason='workout_source_deleted',domains={'training'})
    return {'deleted':True}


def router(connection, require_weighted, context_provider):
    api = APIRouter(prefix='/api/workouts')

    @api.post('/start')
    def start(body: StartExecution):
        if body.day != today():
            raise HTTPException(422, '开练冻结仅用于当天训练；历史补录请直接核对并保存训练日志')
        with connection() as db:
            db.lock_user()
            key = 'execution-' + body.request_id
            existing = db.read('workout_execution', key)
            if existing:
                if existing['plan_id'] != body.plan_id or existing['plan_day'] != body.plan_day:
                    raise HTTPException(409, '开练编号已被其他计划使用')
                return {'id': key, **existing}
            plan = db.read('plan', body.plan_id)
            if not plan or body.plan_day not in {day['name'] for day in plan['days']}:
                raise HTTPException(422, '计划或训练日不存在')
            value = {'plan_id': body.plan_id, 'plan_day': body.plan_day,
                'plan_snapshot': {'id': body.plan_id, **{k: plan[k] for k in ('name','version','cycle_id','cycle_week','cycle_weeks','week_attempt','days','source') if k in plan}}, 'started_at': datetime.now(timezone.utc).isoformat()}
            db.write('workout_execution', key, value)
            return {'id': key, **value}

    @api.get('')
    def list_workouts():
        with connection() as db:
            return {'items': history(db), 'training_memory': memory(db)}

    @api.post('')
    def complete(request: Workout):
        with connection() as db:
            db.lock_user()
            result = save_workout(db, request, require_weighted)
            return {**result, 'training_memory': memory(db)}

    @api.delete('/{workout_id}')
    def remove_workout(workout_id:str):
        with connection() as db:return delete_workout(db,workout_id)

    api.add_api_route('/{workout_id}/review', review_service(connection, require_weighted, context_provider), methods=['POST'])

    return api


def review_service(connection, require_weighted, context_provider):
    async def review(workout_id: str, request: ReviewRequest):
        try:from . import coach
        except ImportError:import coach
        with connection() as db:
            db.lock_user()
            workout = read(db, 'workout', workout_id)
            if not workout:
                raise HTTPException(404, '训练记录不存在或属于旧版记录')
            access=coach.context_access(db)
            if workout.get('ai_review') and workout['ai_review'].get('context_access')==access:
                return {'id': workout_id, **workout}
            if workout.get('ai_review'):
                workout['ai_review']=None
                db.write('workout',workout_id,workout)
            snapshot = revision(db)
        context = context_provider('训练结束复盘 持续训练 ' + ' '.join(require_weighted(e['exercise_id'])['name'] for e in workout['exercises'][:3]))
        try:from .services import context as context_service
        except ImportError:from services import context as context_service
        context = context_service.compact(context)
        context['related_exercise_details'] = [require_weighted(e['exercise_id']) for e in workout['exercises']]
        try:from .services import prompt_registry
        except ImportError:from services import prompt_registry
        instruction = prompt_registry.text('review.md')
        with connection() as db:
            db.lock_user()
            if coach.context_access(db)!=access:raise HTTPException(409,'资料授权或来源已变化，请重新生成复盘')
        model_workout={k:v for k,v in workout.items() if k not in ('ai_review','plan_progression')}
        if model_workout.get('plan_snapshot'):model_workout['plan_snapshot']=privacy.plan_targets(model_workout['plan_snapshot'],invalidated=False)
        raw, model = await ai_planner.chat_json([
            {'role': 'system', 'content': coaches.PERSONALITY_PROMPTS[request.coach_id] + '\n' + instruction},
            {'role': 'user', 'content': json.dumps({'workout': model_workout, 'context': context,
                'output_schema': AIReview.model_json_schema()}, ensure_ascii=False)}], max_tokens=2200)
        try:
            output = AIReview.model_validate(raw)
            if any(len(s) > 300 or not s.strip() for s in output.strengths + output.next_steps):
                raise ValueError('invalid item')
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, 'AI复盘格式无效；训练记录和基础总结已保存，可重试') from None
        with connection() as db:
            db.lock_user()
            current = read(db, 'workout', workout_id)
            if not current:
                raise HTTPException(404, '训练记录不存在')
            if coach.context_access(db)!=access:raise HTTPException(409,'资料授权或来源已变化，未保存旧复盘，请重新生成')
            if current.get('ai_review') and current['ai_review'].get('context_access')==access:
                return {'id': workout_id, **current}
            if revision(db) != snapshot:
                raise HTTPException(409, '训练档案已变化，请重新生成复盘；本次训练记录已保存')
            current['ai_review'] = {**output.model_dump(), 'source': 'ai_advice', 'model': model,
                'context_access':access,
                'knowledge_release_id': context.get('knowledge_release_id', 'baseline'), 'prompt_version': 'review-2',
                'foundation_version': context.get('foundation_knowledge', {}).get('version'),
                'coach_id': request.coach_id, 'created_at': datetime.now(timezone.utc).isoformat()}
            db.write('workout', workout_id, current)
            return {'id': workout_id, **current}

    return review
