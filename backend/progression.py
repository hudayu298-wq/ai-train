"""Onboarding and bounded, versioned AI progression from confirmed workouts."""
import hashlib
import json
from pathlib import Path
from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    from . import progression_settings, strength_profile
    from . import ai_planner, coach, workouts, health_data, periodization, library
    from .services import research_store, knowledge_store,privacy
except ImportError:
    import progression_settings
    import strength_profile
    import ai_planner
    import coach
    import workouts
    import health_data
    import periodization
    import library
    from services import research_store, knowledge_store,privacy


def active_plan(db):
    plan = next((p for p in db.records('plan') if p.get('source') in ('ai', 'user', 'progression')
        and (not p.get('effective_until') or p['effective_until'] >= workouts.today().isoformat())), None)
    return periodization.normalized(plan) if plan else None


def day_inputs(days):
    return [{**{k: d.get(k) for k in ('name', 'weekday', 'start_time', 'duration_minutes', 'focus', 'session_goal', 'training_method', 'primary_exercise_id')},
        'exercises': [{k: e.get(k) for k in ('exercise_id', 'weight_kg', 'sets', 'reps', 'rest_seconds', 'target_rir')} for e in d['exercises']]} for d in days]


def profile_ready(facts):
    weekdays = facts.get('training_weekdays', [])
    return coach.REQUIRED.issubset(facts) and bool(weekdays) and len(weekdays) == facts['days'] and bool(facts.get('session_minutes')) and bool(facts.get('preferred_time'))


def complete_day(workout, target_day):
    return periodization.completed(workout, target_day)


def snapshot(db):
    return hashlib.sha256(json.dumps({'privacy_revision':privacy.revision(db),'facts': coach.state(db)['facts'], 'rm': db.records('rm'),
        'strength_revision': strength_profile.state(db)['revision'],
        'plan': active_plan(db), 'workouts': db.records('workout'), 'health': health_data.revision(db), 'settings': progression_settings.settings(db)}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Adjustment(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    exercise_id: str = Field(min_length=1, max_length=80)
    weight_kg: float | None = Field(ge=0, le=500)
    reps: int = Field(ge=1, le=30, strict=True)
    reason: str = Field(min_length=1, max_length=500)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=1200)
    changes: list[Adjustment] = Field(max_length=20)


def router(connection, get_profile, get_rm, assess_plan):
    api = APIRouter(prefix='/api')

    @api.get('/onboarding')
    def onboarding():
        with connection() as db:
            facts = coach.state(db)['facts']
            marker = db.read('onboarding', 'setup')
            profile_saved = get_profile() is not None
            ready = profile_ready(facts)
            strength = strength_profile.state(db)
            ready = ready and strength['ready']
            # Entry guidance is separate from eligibility to generate a new plan.
            # Saved profiles and completed guidance must not reopen automatically
            # when strength expires or no current plan has been confirmed yet.
            return {'required': not (profile_saved or marker), 'profile_saved': profile_saved,
                'step': 'plan' if ready else 'profile', 'profile_ready': ready, 'strength_profile': strength,
                'facts': facts, 'current_plan': active_plan(db)}

    @api.post('/onboarding/complete')
    def finish_onboarding():
        with connection() as db:
            db.lock_user()
            plan = active_plan(db)
            if not profile_ready(coach.state(db)['facts']) or not plan:
                raise HTTPException(422, '请完成画像并确认训练计划')
            strength_profile.require_ready(db)
            db.write('onboarding', 'setup', {'completed_at': datetime.now(timezone.utc).isoformat(), 'plan_id': plan['id']})
        return {'complete': True}

    api.add_api_route('/workouts/{workout_id}/progression', progress_service(connection, get_profile, get_rm, assess_plan), methods=['POST'])

    @api.post('/plans/changes/{event_id}/undo')
    def undo(event_id: str):
        with connection() as db:
            db.lock_user()
            event = db.read('plan_change', event_id)
            if not event or event.get('status') != 'applied':
                raise HTTPException(404, '计划变更不存在')
            if event.get('undone_by'):
                return {'plan_id': event['undone_by'], 'undone': True}
            current = active_plan(db)
            if not current or current['id'] != event['to_plan_id']:
                raise HTTPException(409, '计划已继续更新，请通过修改当前计划调整目标')
            previous = db.read('plan', event['from_plan_id'])
            key = str(uuid4())
            restored = {**previous, 'source': 'user', 'version': current['version'] + 1,
                'base_plan_id': current['id'], 'latest_change': None, 'note': '已撤销上一次AI进阶，恢复对应训练目标。'}
            db.write('plan', key, restored)
            event['undone_by'] = key
            db.write('plan_change', event_id, event)
        return {'plan_id': key, 'undone': True}

    return api


def progress_service(connection, get_profile, get_rm, assess_plan):
    async def progress(workout_id: str):
        event_id = 'progress-' + workout_id
        with connection() as db:
            db.lock_user()
            private_revision=privacy.revision(db)
            cached = db.read('plan_change', event_id)
            if cached:
                return {'id': event_id, **cached}
            workout = db.read('workout', workout_id)
            if not workout:
                raise HTTPException(404, '训练记录不存在')
            plan = active_plan(db)
            preferences = progression_settings.settings(db)
            policy = {**periodization.POLICY, 'progression_rpe_ceiling': preferences['rpe_ceiling'],
                'max_weight_increase_fraction': preferences['max_weight_increase_fraction'],
                'max_rep_change': preferences['max_rep_change']}
            reason = None
            if not plan or not workout.get('plan_id'):
                reason = '本次训练未关联当前计划，已沉淀到画像；记录计划训练后可评估进阶。'
            elif workout['plan_id'] != plan['id']:
                reason = '当前计划已有更新，本次记录保留为训练事实，不覆盖较新的安排。'
            elif workout['day'] != workouts.today().isoformat():
                reason = '补录历史训练已沉淀到画像，不直接改变今天的训练目标。'
            elif plan.get('cycle_complete'):
                reason = '本周期已完成，请根据最新画像与力量数据生成并确认下一周期计划。'
            target_day = next((d for d in (plan or {}).get('days', []) if d['name'] == workout.get('plan_day')), None)
            if not target_day and not reason:
                reason = '未找到关联训练日，计划暂不调整。'
            if not preferences['enabled']:
                reason = '已关闭自动进阶评估，训练事实与统计照常保存。'
            if workout.get('execution_id') and plan and day_inputs(workout['plan_snapshot']['days']) != day_inputs(plan['days']):
                reason = '开练后计划目标已改变，本次按冻结快照保存，不覆盖新安排。'
            if reason:
                value = {'status': 'held', 'summary': reason, 'changes': [], 'workout_id': workout_id}
                db.write('plan_change', event_id, value)
                return {'id': event_id, **value}
            facts = coach.state(db)['facts']
            cycle_state = periodization.status(plan, workouts.history(db), facts=facts)
            prior_cycle_state = periodization.status(plan, [w for w in workouts.history(db) if w['id'] != workout_id], facts=facts)
            prior = [w for w in workouts.history(db) if w['id'] != workout_id and w['day'] < workout['day'] and
                     w.get('plan_day') == workout['plan_day'] and
                     periodization.workout_cycle_id(w) == plan['cycle_id']]
            current_complete = complete_day(workout, target_day)
            cycle_advance = cycle_state['ready_to_advance'] and not prior_cycle_state['interruption_review_required'] and facts.get('recovery_status') != 'poor'
            previous = prior[0] if prior else None
            two_completed = current_complete and previous is not None and complete_day(previous, target_day)
            max_rpe = max(s['rpe'] for e in workout['exercises'] for s in e['sets'])
            recovery = workout.get('readiness', 'normal')
            prior_rpe = max((s['rpe'] for e in (previous or {}).get('exercises', []) for s in e['sets']), default=10)
            previous_equipment = {e['exercise_id']: (e.get('equipment_id', ''), e.get('load_basis', 'catalog')) for e in (previous or {}).get('exercises', [])}
            comparable_equipment = all(previous_equipment.get(e['exercise_id']) == (e.get('equipment_id', ''), e.get('load_basis', 'catalog')) for e in workout['exercises'])
            can_increase = (two_completed and comparable_equipment and max_rpe <= policy['progression_rpe_ceiling']
                and prior_rpe <= policy['progression_rpe_ceiling'] and recovery != 'poor'
                and facts.get('recovery_status') != 'poor' and not prior_cycle_state['interruption_review_required'])
            comparable_dates = {w['day'] for w in prior if complete_day(w, target_day) and
                all(s['rpe'] <= preferences['rpe_ceiling'] and not s['pain'] for e in w['exercises'] for s in e['sets']) and
                all({e['exercise_id']:(e.get('equipment_id',''),e.get('load_basis','catalog')) for e in w['exercises']}.get(e['exercise_id']) == (e.get('equipment_id',''),e.get('load_basis','catalog')) for e in workout['exercises'])}
            can_increase = can_increase and len(comparable_dates) >= preferences['min_sessions'] - 1
            rms = get_rm()
            health_context = health_data.summarize(db, for_ai=True)
            knowledge = research_store.active(db)
            evidence = research_store.retrieve(db, 'progressive overload resistance training strength 渐进负荷', release=knowledge)
            foundation = knowledge_store.context(db, '渐进调整策略 持续训练 伤病风险', limit=3)
            foundation_revision = knowledge_store.revision(db)
            token = snapshot(db)
        target_ids = {e['exercise_id'] for e in target_day['exercises']}
        context = {'profile': facts, 'rm': rms, 'current_plan': periodization.compact_plan(plan),
            'workout': periodization.compact_workout(workout, target_ids),
            'previous_same_day': periodization.compact_workout(previous, target_ids), 'target_day': target_day,
            'completed_as_planned': current_complete, 'increase_eligible': can_increase,
            'cycle_status': cycle_state, 'cycle_product_policy': policy, 'user_progression_settings': preferences,
            'health_context': health_context,
            'published_evidence': evidence, 'knowledge_release_id': knowledge['id'],
            'foundation_knowledge': foundation,
            'output_schema': Decision.model_json_schema()}
        try:from .services import prompt_registry
        except ImportError:from services import prompt_registry
        instruction = prompt_registry.text('progression.md')
        with connection() as db:
            db.lock_user()
            privacy.require(db,private_revision)
        raw, model = await ai_planner.chat_json([
            {'role': 'system', 'content': instruction},
            {'role': 'user', 'content': json.dumps(context, ensure_ascii=False)}], max_tokens=2500)
        try:
            decision = Decision.model_validate(raw)
            changes = []
            seen = set()
            targets = {e['exercise_id']: e for e in target_day['exercises']}
            actual = {e['exercise_id']: e for e in workout['exercises']}
            rm_map = {r['exercise_id']: r for r in rms if r['confirmed_maximum'] and r.get('reference_1rm_kg') and
                      0 <= (workouts.today() - date.fromisoformat(r['measured_on'])).days <= policy['rm_max_age_days']}
            for adjustment in decision.changes:
                eid = adjustment.exercise_id
                if eid in seen or eid not in targets or eid not in actual:
                    raise ValueError('重复或无关动作')
                seen.add(eid)
                before = targets[eid]
                after = adjustment.model_dump()
                old_w, new_w = before['weight_kg'], after['weight_kg']
                if new_w == old_w and after['reps'] == before['reps']:
                    continue
                if any(s['pain'] for s in actual[eid]['sets']) or eid in cycle_state['recent_discomfort_exercise_ids']:
                    raise ValueError('本次不适动作不能自动调整目标')
                if old_w is None and new_w is not None or old_w is not None and new_w is None:
                    raise ValueError('不能自动补写或清空负重')
                increase_weight = old_w is not None and new_w > old_w
                increase_reps = after['reps'] > before['reps']
                if old_w != new_w and after['reps'] != before['reps']:
                    raise ValueError('每次只改变一个负荷参数')
                if (increase_weight or increase_reps) and (not can_increase or increase_weight and increase_reps):
                    raise ValueError('不满足进阶条件')
                if (increase_weight and preferences['mode'] == 'reps') or (increase_reps and preferences['mode'] == 'weight'):
                    raise ValueError('调整类型不符合用户设置')
                if abs(after['reps'] - before['reps']) > policy['max_rep_change']:
                    raise ValueError('次数变化过大')
                if old_w is not None and not old_w * (1 - policy['max_weight_reduction_fraction']) <= new_w <= old_w * (1 + policy['max_weight_increase_fraction']) + 1e-8:
                    raise ValueError('负荷变化过大')
                if increase_weight:
                    rm = rm_map.get(eid)
                    increment = facts.get('load_increment_kg', policy['default_load_increment_kg'])
                    ratio = (new_w - old_w) / increment
                    if not rm or abs(ratio - round(ratio)) > 1e-6:
                        raise ValueError('无有效RM或加重幅度不可用')
                if (increase_weight or increase_reps) and eid in rm_map:
                    fractions = {1: 1, 2: .95, 3: .93, 4: .90, 5: .87, 6: .85, 7: .83, 8: .80, 9: .77, 10: .75}
                    if new_w is not None and (after['reps'] not in fractions or new_w > rm_map[eid]['reference_1rm_kg'] * fractions[after['reps']]):
                        raise ValueError('超过RM参考')
                if not increase_weight and not increase_reps and max_rpe < policy['reduction_rpe_floor'] and recovery != 'poor' and facts.get('recovery_status') != 'poor':
                    raise ValueError('缺少减量依据')
                changes.append({'exercise_id': eid, 'name': before['name'], 'before': {k: before[k] for k in ('weight_kg', 'reps', 'sets')},
                    'after': {'weight_kg': new_w, 'reps': after['reps'], 'sets': before['sets']}, 'reason': after['reason']})
        except (ValidationError, ValueError, TypeError, KeyError):
            raise HTTPException(502, 'AI调整不符合已完成记录或进阶范围，训练已保存，原计划保持不变，可重试') from None
        with connection() as db:
            db.lock_user()
            cached = db.read('plan_change', event_id)
            if cached:
                return {'id': event_id, **cached}
            if snapshot(db) != token:
                raise HTTPException(409, '画像、计划或训练记录已更新，请重新评估')
            if knowledge_store.revision(db) != foundation_revision:
                raise HTTPException(409, '知识版本或来源已变化，请重新评估')
            value = {'status': 'applied' if changes or cycle_advance else 'held', 'summary': decision.summary,
                'changes': changes, 'workout_id': workout_id, 'from_plan_id': plan['id'],
                'model': model, 'created_at': datetime.now(timezone.utc).isoformat()}
            value['knowledge_release_id'] = knowledge['id']
            value['foundation_revision'] = foundation_revision
            value['prompt_version'] = coach.prompt_registry.version('progression')
            value['policy_version'] = periodization.POLICY_VERSION
            if changes or cycle_advance:
                updated = json.loads(json.dumps(plan))
                updated.pop('id')
                key = str(uuid4())
                for day in updated['days']:
                    if day['name'] == target_day['name']:
                        for e in day['exercises']:
                            delta = next((c for c in changes if c['exercise_id'] == e['exercise_id']), None)
                            if delta:
                                e.update(delta['after'])
                value['to_plan_id'] = key
                updated.update(source='progression', version=plan.get('version', 1) + 1,
                    base_plan_id=plan['id'], generation_id=None, latest_change={'id': event_id, **value},
                    note='AI已依据完成记录更新下一次目标；请查看本次变化，可修改或撤销。')
                if cycle_advance:
                    week = plan.get('cycle_week', 1)
                    updated = periodization.advance(updated)
                    if week < plan.get('cycle_weeks', 4):
                        value['summary'] += f' 本周训练日已完成，进入第{week + 1}周。'
                    else:
                        value['summary'] += ' 整体周期已完成，请结合最新画像与力量数据生成下一周期。'
                    updated['latest_change'] = {'id': event_id, **value}
                else:
                    updated = periodization.sync_current_week(updated)
                # A future-week switch cannot bypass load and time checks.
                periodization.activation_guard(updated, facts, assess_plan(updated),
                    {e['id']: e for e in library.all_entries(connection, 'exercises')})
                db.write('plan', key, updated)
            db.write('plan_change', event_id, value)
            stored = db.read('workout', workout_id)
            stored['plan_progression'] = {'id': event_id, **value}
            db.write('workout', workout_id, stored)
        return {'id': event_id, **value}

    return progress
