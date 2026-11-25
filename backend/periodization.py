"""Executable cycle schedules. Calendar time never silently skips unfinished work.

Numerical execution boundaries belong to a versioned product policy. ACSM 2026
does not require complex periodization for the average healthy adult.
"""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
try:
    from . import training_program
except ImportError:
    import training_program

try:
    from . import coach, workouts, library, strength_profile
except ImportError:
    import coach
    import workouts
    import library
    import strength_profile

POLICY = json.loads((Path(__file__).parent / 'policies' / 'training-v1.json').read_text(encoding='utf-8'))
POLICY_VERSION = POLICY['version']


def estimate_seconds(day):
    return POLICY['warmup_estimate_seconds'] + sum(
        e['sets'] * e['reps'] * POLICY['rep_estimate_seconds']
        + max(0, e['sets'] - 1) * e['rest_seconds'] + POLICY['exercise_transition_seconds']
        for e in day['exercises'])


def equipment_allowed(entry, facts):
    """Only enforce explicit exclusive inventories; free text is not an inventory."""
    available = facts.get('equipment', '')
    if not any(marker in available for marker in ('只有', '仅有', '仅限', 'only ')):
        return True
    return all(part.strip() in available for part in re.split(r'[/、,，+]', entry.get('equipment', '')) if part.strip())


def activation_guard(plan, facts, assessment, catalog=None):
    if plan.get('training_program_version'):
        value = normalized(plan)
        week = value['cycle_schedule'][value['cycle_week'] - 1]
        try:
            training_program.validate(value, {}, recovery=week['phase'] == 'deload')
        except ValueError as e:
            raise HTTPException(409, '调整不符合当前训练法，原计划保留，请复核：' + str(e)) from None
    if any(i['status'] in ('above_reference', 'high_relative_load', 'stale_rm') for i in assessment['items']):
        raise HTTPException(409, '下一周目标需要复核最新RM，请确认或修改计划后再切换')
    for day in plan['days']:
        limits = [n for n in (day.get('duration_minutes'), facts.get('session_minutes')) if n]
        if limits and estimate_seconds(day) > min(limits) * 60:
            raise HTTPException(409, '下一周目标预计超出当前可用时间，请先修改计划')
        for exercise in day['exercises']:
            entry = (catalog or {}).get(exercise['exercise_id'])
            if catalog is not None and (not entry or not equipment_allowed(entry, facts)):
                raise HTTPException(409, '下一周目标的动作或器械不符合当前可用范围，请先复核计划')
            if catalog is None and any(marker in facts.get('equipment', '') for marker in ('只有', '仅有', '仅限', 'only ')):
                raise HTTPException(409, '当前器械范围需复核后才能切换目标')
    snapshot = plan.get('coach_profile_snapshot', {})
    if any(snapshot.get(k) != facts.get(k) for k in ('equipment', 'training_weekdays', 'session_minutes', 'injury_status', 'movement_constraints')):
        raise HTTPException(409, '器械、安排或当前可训练范围已变化，请复核并确认计划')


def normalized(plan):
    """Read adapter for old plans; never writes a migrated plan on GET."""
    value = deepcopy(plan)
    if not value.get('cycle_id'):
        value['cycle_id'] = value.get('id') or 'legacy-' + hashlib.sha256(json.dumps(
            {k: value.get(k) for k in ('name', 'days', 'created_on', 'base_plan_id')}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]
    value.setdefault('cycle_weeks', POLICY['default_cycle_weeks'])
    value.setdefault('cycle_week', 1)
    value.setdefault('cycle_complete', False)
    value.setdefault('cycle_policy_version', POLICY_VERSION)
    value.setdefault('cycle_started_on', value.get('created_on', workouts.today().isoformat()))
    value.setdefault('week_started_on', value['cycle_started_on'])
    value.setdefault('week_attempt', 1)
    if not value.get('cycle_schedule'):
        notes = value.get('weeks', [])
        value['cycle_schedule'] = [{'week': index + 1, 'phase': 'foundation' if index == 0 else 'consolidate',
            'purpose': notes[index] if index < len(notes) else '保持可完成的目标，依据实际表现复核余力与恢复。',
            'days': deepcopy(value['days'])} for index in range(value['cycle_weeks'])]
        value.setdefault('cycle_schedule_origin', 'legacy_template')
    value.setdefault('cycle_baseline_days', deepcopy(value['cycle_schedule'][0]['days']))
    value.setdefault('next_cycle', {'status': 'review_when_complete',
        'guidance': '周期完成后复核目标、恢复、器械与最新有效RM，生成下一周期草稿并确认；不自动增加负重。'})
    return value


def day_signature(days):
    return [{k: d.get(k) for k in ('name', 'weekday', 'start_time', 'duration_minutes', 'focus', 'session_goal', 'training_method', 'primary_exercise_id')} | {
        'exercises': [{k: e.get(k) for k in ('exercise_id', 'weight_kg', 'sets', 'reps', 'rest_seconds', 'target_rir')}
                      for e in d['exercises']]} for d in days]


def schedule_signature(schedule):
    return [{k: week.get(k) for k in ('week', 'phase', 'purpose')} | {'days': day_signature(week['days'])} for week in schedule]


def sync_current_week(plan):
    """An explicit edit affects the current week; other weeks remain reviewable."""
    value = normalized(plan)
    value['cycle_schedule'][value['cycle_week'] - 1]['days'] = deepcopy(value['days'])
    return value


def validate_schedule(plan):
    value = normalized(plan)
    schedule = value['cycle_schedule']
    if len(schedule) != value['cycle_weeks'] or [w['week'] for w in schedule] != list(range(1, value['cycle_weeks'] + 1)):
        raise ValueError('周期周数必须连续且与长度一致')
    identities = [(d['name'], [e['exercise_id'] for e in d['exercises']]) for d in value['days']]
    for week in schedule:
        if [(d['name'], [e['exercise_id'] for e in d['exercises']]) for d in week['days']] != identities:
            raise ValueError('各周须保留相同训练日和动作，替换动作请另行确认计划')
    if day_signature(schedule[value['cycle_week'] - 1]['days']) != day_signature(value['days']):
        raise ValueError('当前执行目标与周期对应周不一致')
    return value


def prepare_generated(plan, facts, baselines, catalog, training_memory, regional_strength=None):
    """Apply the same load, duration and identity guards to every future week."""
    plan = deepcopy(plan)
    if plan.get('cycle_blueprint'):
        if plan.get('cycle_schedule'):
            raise ValueError('不能同时提交完整周目标和模板蓝图')
        if len(plan['cycle_blueprint']) != plan['cycle_weeks']:
            raise ValueError('模板蓝图周数与周期长度不一致')
        plan['cycle_schedule'] = []
        for week in plan['cycle_blueprint']:
            if (week['phase'] == 'deload') != (week['template'] == 'recovery'):
                raise ValueError('减量阶段与恢复模板必须一致，不能只更改阶段名称')
            days = deepcopy(plan['days'])
            if week['template'] == 'recovery':
                if week['week'] == 1:
                    raise ValueError('第一周须引用基础目标')
                for day in days:
                    for exercise in day['exercises']:
                        exercise['sets'] = max(1, math.floor(exercise['sets'] * POLICY['deload_set_fraction']))
            plan['cycle_schedule'].append({k: week[k] for k in ('week', 'phase', 'purpose')} | {'days': days})
    value = normalized(plan)
    weekdays = facts.get('training_weekdays', [])
    raw_names = [d['name'] for d in value['days']]
    for week in value['cycle_schedule']:
        if [d['name'] for d in week['days']] != raw_names:
            raise ValueError('各周训练日须与基础周一致')
    all_weeks = [value['days']] + [w['days'] for w in value['cycle_schedule']]
    for days in all_weeks:
        for index, day in enumerate(days):
            if len(weekdays) == facts['days']:
                day['weekday'] = weekdays[index]
                day['name'] = '周' + '一二三四五六日'[weekdays[index] - 1] + f' · 训练{index + 1}'
            day['start_time'] = facts.get('preferred_time')
            day['duration_minutes'] = facts.get('session_minutes')
            if len(day['exercises']) > POLICY['max_daily_ai_exercises'] or len({e['exercise_id'] for e in day['exercises']}) != len(day['exercises']):
                raise ValueError('动作重复或过多')
            for exercise in day['exercises']:
                entry = catalog.get(exercise['exercise_id'])
                if not entry:
                    raise ValueError('动作不在可用库中')
                if not equipment_allowed(entry, facts):
                    raise ValueError('动作需要画像未提供的器械')
                exercise.setdefault('target_rir', POLICY['default_target_rir'])
                if exercise['target_rir'] is None:
                    exercise['target_rir'] = POLICY['default_target_rir']
                rm = baselines.get(exercise['exercise_id'])
                if regional_strength is not None:
                    strength_profile.validate_load(exercise, regional_strength, baselines)
                elif not rm:
                    exercise['weight_kg'] = None
                elif exercise['weight_kg'] is not None:
                    # Same reference table used by the existing RM assessment.
                    fractions = {1: 1, 2: .95, 3: .93, 4: .90, 5: .87, 6: .85, 7: .83, 8: .80, 9: .77, 10: .75}
                    if exercise['reps'] not in fractions or exercise['weight_kg'] > rm['reference_1rm_kg'] * fractions[exercise['reps']]:
                        raise ValueError('重量超出RM参考')
            if day.get('duration_minutes') and estimate_seconds(day) > day['duration_minutes'] * 60:
                raise ValueError('周期中有训练日预计超时')
    value['cycle_week'] = 1
    value = validate_schedule(value)
    baseline = {(d['name'], e['exercise_id']): e for d in value['days'] for e in d['exercises']}
    for week in value['cycle_schedule'][1:]:
        for day in week['days']:
            for exercise in day['exercises']:
                first = baseline[(day['name'], exercise['exercise_id'])]
                if (exercise['sets'] > first['sets'] or exercise['reps'] > first['reps'] or
                        (first['weight_kg'] is None and exercise['weight_kg'] is not None) or
                        (first['weight_kg'] is not None and exercise['weight_kg'] is not None and exercise['weight_kg'] > first['weight_kg'])):
                    raise ValueError('未来周不能预先自动提高负荷，须由已确认训练后的进阶评估授权')
    value['cycle_schedule_origin'] = ('materialized_blueprint' if plan.get('cycle_blueprint') else
                                      'structured_ai' if plan.get('cycle_schedule') else 'legacy_template')
    painful = {d['exercise_id'] for d in training_memory.get('recent_discomfort', [])}
    planned_painful = painful & {e['exercise_id'] for d in value['days'] for e in d['exercises']}
    if planned_painful:
        if regional_strength is not None:
            raise ValueError('近期不适动作应选择可训练的替代动作，不能以空重量交付')
        value.setdefault('risk_warnings', []).append('近期不适动作（' + '、'.join(sorted(planned_painful)) + '）需暂停并确认可训练范围；以下目标不代表可以带痛执行，不自动加重。')
        for days in [value['days']] + [w['days'] for w in value['cycle_schedule']]:
            for day in days:
                for exercise in day['exercises']:
                    if exercise['exercise_id'] in planned_painful:
                        exercise['weight_kg'] = None
    value['cycle_policy_version'] = POLICY_VERSION
    return value


def compact_plan(plan):
    if not plan:
        return None
    value = normalized(plan)
    current = value['cycle_schedule'][value['cycle_week'] - 1]
    return {k: value.get(k) for k in ('id', 'name', 'version', 'cycle_id', 'cycle_week', 'cycle_weeks', 'cycle_complete', 'days', 'split_type', 'training_program_version')} | {
        'phase': current['phase'], 'purpose': current['purpose'], 'policy_version': value['cycle_policy_version'],
        'cycle_overview': [{k: week[k] for k in ('week', 'phase', 'purpose')} for week in value['cycle_schedule']]}


def compact_workout(workout, exercise_ids=None):
    if not workout:
        return None
    value = {k: v for k, v in workout.items() if k not in ('input', 'plan_snapshot', 'plan_progression', 'ai_review', 'summary')}
    if exercise_ids is not None:
        value['exercises'] = [{k: v for k, v in e.items() if k in ('exercise_id', 'name', 'sets', 'equipment_id', 'load_basis', 'discomfort_area')}
            for e in workout['exercises'] if e['exercise_id'] in exercise_ids]
    return value


def completed(workout, day):
    if not workout.get('completed_plan_day'):
        return False
    actual = {e['exercise_id']: e for e in workout['exercises']}
    for target in day['exercises']:
        item = actual.get(target['exercise_id'])
        sets = [s for s in (item or {}).get('sets', []) if s.get('set_type', 'working') == 'working']
        if not item or item.get('load_basis', 'catalog') != 'catalog' or len(sets) < target['sets']:
            return False
        if any(s.get('assisted') or s.get('pain') or s['reps'] < target['reps'] or
               (target['weight_kg'] is not None and s['weight_kg'] < target['weight_kg']) for s in sets[:target['sets']]):
            return False
    return True


def workout_cycle_id(workout):
    snapshot = workout.get('plan_snapshot') or {}
    # Old snapshots lacked cycle_id and often lacked id. The explicit workout
    # plan_id is the reliable link; unlinked old records cannot establish a cycle.
    return snapshot.get('cycle_id') or workout.get('plan_id') or snapshot.get('id')


def status(plan, history, today=None, facts=None):
    today = today or workouts.today()
    value = normalized(plan)
    related = [w for w in history if workout_cycle_id(w) == value['cycle_id']]
    current = [w for w in related if (w.get('plan_snapshot') or {}).get('cycle_week', 1) == value['cycle_week']
               and (w.get('plan_snapshot') or {}).get('week_attempt', 1) == value['week_attempt']
               and w['day'] >= value['week_started_on']]
    done = {w.get('plan_day') for w in current if any(d['name'] == w.get('plan_day') and completed(w, d)
        for d in (w.get('plan_snapshot') or {}).get('days', []))}
    pending = [d['name'] for d in value['days'] if d['name'] not in done]
    last = max((w['day'] for w in history if w['day'] <= today.isoformat()), default=value['cycle_started_on'])
    if value.get('cycle_reviewed_on'):
        last = max(last, value['cycle_reviewed_on'])
    gap = max(0, (today - date.fromisoformat(last)).days)
    elapsed = max(0, (today - date.fromisoformat(value['week_started_on'])).days)
    discomfort = sorted({e['exercise_id'] for w in history
        if 0 <= (today - date.fromisoformat(w['day'])).days < POLICY['recent_discomfort_days']
        for e in w['exercises'] if any(s.get('pain') for s in e['sets'])})
    recent = sorted([w for w in history if 0 <= (today - date.fromisoformat(w['day'])).days < POLICY['fatigue_feedback_days']],
                    key=lambda w: w['day'], reverse=True)[:POLICY['fatigue_feedback_sessions']]
    fatigue = any(w.get('readiness') == 'poor' or any(s['rpe'] >= POLICY['reduction_rpe_floor'] for e in w['exercises'] for s in e['sets']) for w in recent)
    interrupted = gap >= POLICY['interruption_review_days']
    review = interrupted or bool(discomfort) or fatigue or (facts or {}).get('recovery_status') == 'poor'
    return {'policy_version': POLICY_VERSION, 'week': value['cycle_week'], 'phase': value['cycle_schedule'][value['cycle_week'] - 1]['phase'],
        'purpose': value['cycle_schedule'][value['cycle_week'] - 1]['purpose'],
        'completed_days': sorted(done), 'pending_days': pending, 'ready_to_advance': not pending and not value['cycle_complete'] and not review,
        'missed_week': bool(pending) and elapsed >= POLICY['week_review_days'], 'days_since_training': gap,
        'interruption_review_required': interrupted, 'deload_suggested': review,
        'recent_discomfort_exercise_ids': discomfort, 'cycle_complete': value['cycle_complete'],
        'deload_preview': [{'day': d['name'], 'exercise_id': e['exercise_id'], 'before_sets': e['sets'],
            'after_sets': max(1, math.floor(e['sets'] * POLICY['deload_set_fraction']))}
            for d in value['days'] for e in d['exercises']] if review else [],
        'guidance': ('本周期已完成：复核画像、恢复和有效RM，再生成并确认下一周期。' if value['cycle_complete'] else
                     '存在断训、恢复不佳、高用力或近期不适；先复核，可确认降低组数后重启本周。' if review else
                     '有漏练时保留当前周，不赶进度或在同一天补齐多次训练；可继续本周。' if pending else
                     '本周目标已完成，可进入下一周目标。')}


def advance(plan, *, today=None):
    """Switch actual days. Preserve earned changes only across identical templates."""
    value = sync_current_week(plan)
    today = today or workouts.today()
    index = value['cycle_week'] - 1
    if index + 1 >= value['cycle_weeks']:
        value['cycle_complete'] = True
        value['next_cycle']['status'] = 'ready_for_review'
        return value
    original = normalized(plan)['cycle_baseline_days']
    following = deepcopy(value['cycle_schedule'][index + 1]['days'])
    for prev, current, next_day in zip(original, value['days'], following):
        for baseline, actual, target in zip(prev['exercises'], current['exercises'], next_day['exercises']):
            if all(target.get(k) == baseline.get(k) for k in ('weight_kg', 'reps', 'sets')):
                target.update({k: actual[k] for k in ('weight_kg', 'reps')})
    value['cycle_week'] += 1
    value['days'] = following
    value['cycle_schedule'][index + 1]['days'] = deepcopy(following)
    value['week_started_on'] = today.isoformat()
    value['week_attempt'] = 1
    return value


class CycleAction(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    base_plan_id: str = Field(min_length=1, max_length=100)
    action: Literal['repeat_week', 'deload_week', 'advance_week']


def router(connection, get_profile, get_rm, assess_plan):
    api = APIRouter(prefix='/api')

    @api.get('/plans/cycle/current')
    def current_cycle():
        try:
            from .progression import active_plan
        except ImportError:
            from progression import active_plan
        with connection() as db:
            plan = active_plan(db)
            return {'plan': normalized(plan), 'status': status(plan, workouts.history(db), facts=coach.state(db)['facts'])} if plan else {'plan': None, 'status': None}

    @api.post('/plans/cycle/actions')
    def cycle_action(body: CycleAction):
        try:
            from .progression import active_plan
        except ImportError:
            from progression import active_plan
        event_id = 'cycle-' + body.request_id
        fingerprint = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
        with connection() as db:
            db.lock_user()
            cached = db.read('plan_change', event_id)
            if cached:
                if cached.get('request_fingerprint') != fingerprint:
                    raise HTTPException(409, '请求编号已用于其他周期操作')
                return {'id': event_id, **cached}
            plan = active_plan(db)
            if not plan or plan['id'] != body.base_plan_id:
                raise HTTPException(409, '当前计划已变化，请刷新后重试')
            value = normalized(plan)
            state = status(value, workouts.history(db), facts=coach.state(db)['facts'])
            if value['cycle_complete']:
                raise HTTPException(422, '周期已完成，请生成并确认下一周期')
            if body.action == 'advance_week':
                if not state['ready_to_advance']:
                    raise HTTPException(422, '仍有未完成训练或恢复待复核，不能跳周')
                value = advance(value)
                activation_guard(value, coach.state(db)['facts'], assess_plan(value),
                    {e['id']: e for e in library.all_entries(connection, 'exercises')})
                summary = '已按已完成记录切换下一周实际目标。'
            else:
                if body.action == 'deload_week':
                    if not state['deload_suggested'] and coach.state(db)['facts'].get('recovery_status') != 'poor':
                        raise HTTPException(422, '暂无减量依据，可保留当前目标重复本周')
                    for day in value['days']:
                        for exercise in day['exercises']:
                            exercise['sets'] = max(1, math.floor(exercise['sets'] * POLICY['deload_set_fraction']))
                    value = sync_current_week(value)
                value['week_started_on'] = workouts.today().isoformat()
                value['week_attempt'] = value.get('week_attempt', 1) + 1
                value['cycle_reviewed_on'] = workouts.today().isoformat()
                summary = '已确认降低本周组数并重新开始，暂停引起不适的动作。' if body.action == 'deload_week' else '已保留本周目标并重新开始，不补课叠加训练量。'
            key = str(uuid4())
            event = {'status': 'applied', 'summary': summary, 'changes': [], 'from_plan_id': plan['id'], 'to_plan_id': key,
                'request_fingerprint': fingerprint, 'policy_version': POLICY_VERSION,
                'created_at': datetime.now(timezone.utc).isoformat(), 'action': body.action}
            value.pop('id', None)
            value.update(source='progression', base_plan_id=plan['id'], version=plan.get('version', 1) + 1,
                         latest_change={'id': event_id, **event})
            db.write('plan', key, value)
            db.write('plan_change', event_id, event)
            return {'id': event_id, **event}

    return api
