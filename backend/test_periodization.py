"""Executable-cycle integration contracts and conservative transition guards."""
from copy import deepcopy
from datetime import timedelta
import asyncio
import json

import pytest
from fastapi import HTTPException

from test_app import module, client, PROFILE, PLAN, isolate_records, _plan_workout, _progress_plan, ai_result, complete_strength_profile


@pytest.fixture(autouse=True)
def regional_strength_ready(isolate_records):
    complete_strength_profile()


def schedule_for(days, weeks=2):
    return [{'week': i + 1, 'phase': 'foundation' if i == 0 else 'deload',
             'purpose': '校准动作与余力' if i == 0 else '减少工作组、复核恢复', 'days': deepcopy(days)} for i in range(weeks)]


def structured_plan():
    _progress_plan()
    schedule = schedule_for(PLAN['days'])
    schedule[1]['days'][0]['exercises'][0].update(sets=2, reps=5, rest_seconds=180, target_rir=4)
    return client.post('/api/plans', json={**PLAN, 'cycle_weeks': 2, 'cycle_schedule': schedule}).json()


def hold_ai(monkeypatch):
    async def fake(*args, **kwargs):
        return {'summary': '本次保持负荷，按已确认周期目标执行。', 'changes': []}, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'chat_json', fake)


def test_real_week_switches_sets_rest_and_rir_then_finishes_and_undoes(monkeypatch):
    plan = structured_plan()
    hold_ai(monkeypatch)
    workout = _plan_workout(plan, 'structured-week-one')
    response = client.post(f"/api/workouts/{workout['id']}/progression")
    assert response.status_code == 200, response.text
    next_plan = client.get('/api/plans').json()[0]
    assert next_plan['cycle_week'] == 2
    exercise = next_plan['days'][0]['exercises'][0]
    assert (exercise['sets'], exercise['rest_seconds'], exercise['target_rir']) == (2, 180, 4)
    assert next_plan['cycle_schedule'][1]['days'] == next_plan['days']
    second = _plan_workout(next_plan, 'structured-week-two')
    response = client.post(f"/api/workouts/{second['id']}/progression")
    assert response.status_code == 200, response.text
    completed = client.get('/api/plans').json()[0]
    assert completed['cycle_complete'] and completed['next_cycle']['status'] == 'ready_for_review'
    assert client.post('/api/plans/changes/' + response.json()['id'] + '/undo').status_code == 200
    restored = client.get('/api/plans').json()[0]
    assert not restored['cycle_complete'] and restored['days'][0]['exercises'][0]['sets'] == 2


def test_old_saved_plan_is_adapted_without_rewriting_or_skipping_missed_week():
    client.put('/api/profile', json=PROFILE)
    old = module.save('plan', {**PLAN, 'source': 'user', 'version': 1,
        'created_on': (module.nutrition_today() - timedelta(days=10)).isoformat(), 'cycle_week': 1})
    with module.connection() as db:
        before = deepcopy(db.read('plan', old['id']))
    listed = client.get('/api/plans').json()[0]
    assert listed['cycle_week'] == 1 and len(listed['cycle_schedule']) == 4
    assert listed['cycle_status']['missed_week'] and not listed['cycle_status']['ready_to_advance']
    assert client.post('/api/plans/cycle/actions', json={'request_id': 'cannot-skip-week',
        'base_plan_id': old['id'], 'action': 'advance_week'}).status_code == 422
    with module.connection() as db:
        assert db.read('plan', old['id']) == before


def test_interruption_deload_is_confirmed_idempotent_stale_safe_and_undoable():
    plan = _progress_plan()
    with module.connection() as db:
        raw = db.read('plan', plan['id'])
        raw.update(cycle_started_on=(module.nutrition_today() - timedelta(days=20)).isoformat(),
                   week_started_on=(module.nutrition_today() - timedelta(days=20)).isoformat())
        db.write('plan', plan['id'], raw)
    state = client.get('/api/plans/cycle/current').json()['status']
    assert state['interruption_review_required'] and state['deload_suggested']
    body = {'request_id': 'confirmed-deload-week', 'base_plan_id': plan['id'], 'action': 'deload_week'}
    response = client.post('/api/plans/cycle/actions', json=body)
    assert response.status_code == 200, response.text
    assert client.post('/api/plans/cycle/actions', json=body).json() == response.json()
    assert client.post('/api/plans/cycle/actions', json={**body, 'action': 'repeat_week'}).status_code == 409
    assert client.post('/api/plans/cycle/actions', json={**body, 'request_id': 'stale-repeat-week'}).status_code == 409
    current = client.get('/api/plans').json()[0]
    assert current['days'][0]['exercises'][0]['sets'] == 3 and current['cycle_week'] == 1 and current['week_attempt'] == 2
    assert client.post('/api/plans/changes/' + response.json()['id'] + '/undo').status_code == 200
    assert client.get('/api/plans').json()[0]['days'][0]['exercises'][0]['sets'] == 4


def test_repeating_same_day_does_not_reuse_completed_attempt():
    plan = _progress_plan()
    _plan_workout(plan, 'before-repeat-complete')
    response = client.post('/api/plans/cycle/actions', json={'request_id': 'repeat-after-complete',
        'base_plan_id': plan['id'], 'action': 'repeat_week'})
    assert response.status_code == 200
    assert client.get('/api/plans').json()[0]['cycle_status']['pending_days'] == ['周一']


def test_ai_full_cycle_survives_old_client_confirmation(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    raw = ai_result()
    raw['cycle_weeks'] = 2
    raw['cycle_schedule'] = schedule_for(raw['days'])
    for d in raw['cycle_schedule'][1]['days']:
        d['exercises'][0]['sets'] = 2
    async def fake(*args):
        return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    draft = client.post('/api/plans/generate').json()
    assert 'generation_id' in draft, draft
    saved = client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')})
    assert saved.status_code == 200, saved.text
    assert saved.json()['cycle_schedule'][1]['days'][0]['exercises'][0]['sets'] == 2


def test_compact_blueprint_materializes_real_recovery_and_preserves_legacy_rir(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    raw = ai_result()
    raw['cycle_weeks'] = 2
    raw['cycle_blueprint'] = [
        {'week': 1, 'phase': 'foundation', 'purpose': '校准实际余力', 'template': 'base'},
        {'week': 2, 'phase': 'deload', 'purpose': '复核恢复并减少工作组', 'template': 'recovery'}]
    async def fake(profile, rms, schema):
        assert 'cycle_schedule' not in schema['properties']
        assert 'cycle_blueprint' in schema['required']
        return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    response = client.post('/api/plans/generate')
    assert response.status_code == 200, response.text
    draft = response.json()
    assert draft['cycle_schedule_origin'] == 'materialized_blueprint'
    assert draft['cycle_schedule'][1]['days'][0]['exercises'][0]['sets'] == 3
    legacy_days = deepcopy(draft['days'])
    for day in legacy_days:
        for exercise in day['exercises']:
            exercise.pop('target_rir')
    body = {'name': draft['name'], 'days': legacy_days, 'generation_id': draft['generation_id']}
    result = client.post('/api/plans', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['days'][0]['exercises'][0]['target_rir'] == 3
    assert client.post('/api/plans', json=body).status_code == 200


@pytest.mark.parametrize('phase,template', [('deload', 'base'), ('build', 'recovery')])
def test_blueprint_cannot_label_an_unchanged_week_as_deload(monkeypatch, phase, template):
    client.put('/api/profile', json=PROFILE)
    raw = ai_result()
    raw['cycle_weeks'] = 2
    raw['cycle_blueprint'] = [
        {'week': 1, 'phase': 'foundation', 'purpose': '校准实际余力', 'template': 'base'},
        {'week': 2, 'phase': phase, 'purpose': '复核恢复', 'template': template}]
    async def fake(*args):
        return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    result = client.post('/api/plans/generate')
    assert result.status_code == 502
    assert module.records('plan_draft') == []


def test_plan_generator_reserves_output_for_a_full_base_week_without_paid_calls(monkeypatch):
    async def fake(messages, **kwargs):
        assert kwargs['max_tokens'] == 8192
        payload = json.loads(messages[1]['content'])
        assert payload['profile']['days'] == 7
        assert payload['output_schema'] == {'type': 'object'}
        return {'name': 'seven-day-base-week'}, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'chat_json', fake)
    result = asyncio.run(module.ai_planner.generate({'days': 7}, {}, {'type': 'object'}))
    assert result == ({'name': 'seven-day-base-week'}, 'test-model')


def test_ai_confirmation_cannot_replace_verified_future_weeks(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    raw = ai_result()
    raw['cycle_weeks'] = 2
    raw['cycle_schedule'] = schedule_for(raw['days'])
    async def fake(*args):
        return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    draft = client.post('/api/plans/generate').json()
    body = {k: draft[k] for k in ('name', 'days', 'generation_id', 'cycle_schedule')}
    body['cycle_schedule'][1]['days'][0]['exercises'][0]['sets'] = 20
    assert client.post('/api/plans', json=body).status_code == 422
    assert module.records('plan') == []


def test_current_edits_sync_only_that_week_and_compact_context_excludes_history():
    plan = structured_plan()
    edited = deepcopy(PLAN)
    edited['base_plan_id'] = plan['id']
    edited['days'][0]['exercises'][0]['sets'] = 3
    response = client.post('/api/plans', json=edited)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved['cycle_schedule'][0]['days'][0]['exercises'][0]['sets'] == 3
    assert saved['cycle_schedule'][1]['days'][0]['exercises'][0]['sets'] == 2
    full = module.periodization.normalized(saved)
    full['cycle_weeks'] = 12
    full['cycle_schedule'] = [deepcopy(full['cycle_schedule'][0]) for _ in range(12)]
    context = module.periodization.compact_plan(full)
    assert 'cycle_schedule' not in context and len(context['cycle_overview']) == 12
    assert len(json.dumps(context)) < 7000
    workout = {'id': 'workout', 'exercises': [], 'plan_snapshot': full, 'input': {'plan': full}, 'plan_progression': {'plan': full}}
    assert module.periodization.compact_workout(workout) == {'id': 'workout', 'exercises': []}


@pytest.mark.parametrize('unsafe', ['load', 'time', 'identity', 'count'])
def test_every_ai_week_has_guards_not_just_first_week(monkeypatch, unsafe):
    client.put('/api/profile', json=PROFILE)
    client.post('/api/rm', json={'exercise_id': 'bench', 'weight_kg': 100, 'reps': 1,
        'measured_on': module.nutrition_today().isoformat(), 'confirmed_maximum': True})
    client.patch('/api/coach/profile', json={'session_minutes': 30})
    raw = ai_result()
    raw['cycle_weeks'] = 2
    raw['cycle_schedule'] = schedule_for(raw['days'])
    future = raw['cycle_schedule'][1]['days'][0]
    if unsafe == 'load':
        future['exercises'][0]['weight_kg'] = 120
    elif unsafe == 'time':
        future['exercises'][0].update(sets=20, reps=100, rest_seconds=1800)
    elif unsafe == 'identity':
        future['exercises'][0]['exercise_id'] = 'squat'
    else:
        raw['cycle_schedule'].pop()
    async def fake(*args):
        return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    assert client.post('/api/plans/generate').status_code == 502
    assert module.records('plan_draft') == []


def test_recent_pain_blocks_automatic_week_transition(monkeypatch):
    plan = structured_plan()
    hold_ai(monkeypatch)
    workout = _plan_workout(plan, 'pain-no-week-advance', pain=True)
    response = client.post(f"/api/workouts/{workout['id']}/progression")
    assert response.status_code == 200
    current = client.get('/api/plans').json()[0]
    assert current['id'] == plan['id'] and current['cycle_week'] == 1
    assert current['cycle_status']['deload_suggested']


def test_earned_progression_survives_multiple_day_week_switch(monkeypatch):
    _progress_plan()
    plan = client.post('/api/plans', json={**PLAN, 'days': [PLAN['days'][0], {**PLAN['days'][0], 'name': '周四'}]}).json()
    _plan_workout(plan, 'prior-earned-progress', day=module.nutrition_today() - timedelta(days=7))
    one = _plan_workout(plan, 'day-one-earned-progress')
    async def fake(messages, **kwargs):
        context = json.loads(messages[1]['content'])
        changes = [{'exercise_id': 'bench', 'weight_kg': 75, 'reps': 6, 'reason': '两次达标'}] if context['increase_eligible'] else []
        return {'summary': '按记录执行', 'changes': changes}, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'chat_json', fake)
    assert client.post(f"/api/workouts/{one['id']}/progression").status_code == 200
    current = client.get('/api/plans').json()[0]
    two = client.post('/api/workouts', json={'request_id': 'day-two-earned-progress', 'plan_id': current['id'],
        'plan_day': '周四', 'completed_plan_day': True, 'exercises': [{'exercise_id': 'bench',
        'sets': [{'weight_kg': 75, 'reps': 5, 'rpe': 7} for _ in range(4)]}]}).json()
    assert client.post(f"/api/workouts/{two['id']}/progression").status_code == 200
    after = client.get('/api/plans').json()[0]
    assert after['cycle_week'] == 2 and after['days'][0]['exercises'][0]['reps'] == 6


def test_identity_edit_cannot_silently_erase_real_recovery_week():
    plan = structured_plan()
    edited = deepcopy(PLAN)
    edited['base_plan_id'] = plan['id']
    edited['days'][0]['name'] = '周二'
    response = client.post('/api/plans', json=edited)
    assert response.status_code == 422 and '不同周目标' in response.text
    current = client.get('/api/plans').json()[0]
    assert current['id'] == plan['id'] and current['cycle_schedule'][1]['days'][0]['exercises'][0]['sets'] == 2


def test_repeated_template_identity_edit_preserves_purpose_and_origin():
    plan = _progress_plan()
    with module.connection() as db:
        raw = db.read('plan', plan['id'])
        raw['cycle_schedule'][1]['purpose'] = '复核训练习惯'
        db.write('plan', plan['id'], raw)
    edited = deepcopy(PLAN)
    edited['base_plan_id'] = plan['id']
    edited['days'][0]['name'] = '周二'
    result = client.post('/api/plans', json=edited)
    assert result.status_code == 200, result.text
    value = result.json()
    assert value['cycle_schedule_origin'] == 'user_rebased_template'
    assert value['cycle_schedule'][1]['purpose'] == '复核训练习惯'
    assert all(w['days'][0]['name'] == '周二' for w in value['cycle_schedule'])


def test_legacy_cycles_match_explicit_plan_identity_not_missing_values():
    old_a = {**deepcopy(PLAN), 'id': 'old-plan-a', 'created_on': module.nutrition_today().isoformat()}
    old_b = {**deepcopy(PLAN), 'id': 'old-plan-b', 'created_on': module.nutrition_today().isoformat()}
    workout = {'id': 'legacy-workout', 'day': module.nutrition_today().isoformat(), 'plan_id': 'old-plan-a',
        'plan_snapshot': {k: v for k, v in old_a.items() if k != 'id'}, 'plan_day': '周一', 'completed_plan_day': True,
        'exercises': [{'exercise_id': 'bench', 'sets': [{'weight_kg': 75, 'reps': 5, 'rpe': 7} for _ in range(4)]}]}
    assert module.periodization.status(old_a, [workout])['ready_to_advance']
    assert not module.periodization.status(old_b, [workout])['ready_to_advance']
    assert module.periodization.normalized(old_a)['cycle_id'] == 'old-plan-a'


def test_unlinked_legacy_workout_cannot_complete_any_cycle():
    old = {**deepcopy(PLAN), 'id': 'legacy-plan', 'created_on': module.nutrition_today().isoformat()}
    workout = {'day': module.nutrition_today().isoformat(),
        'plan_snapshot': deepcopy(PLAN), 'plan_day': '周一', 'completed_plan_day': True,
        'exercises': [{'exercise_id': 'bench', 'sets': [{'weight_kg': 75, 'reps': 5, 'rpe': 7} for _ in range(4)]}]}
    state = module.periodization.status(old, [workout])
    assert state['pending_days'] == ['周一']
    assert not state['ready_to_advance']


@pytest.mark.parametrize('constraint', ['new_equipment', 'current_time', 'new_discomfort'])
def test_activation_checks_new_constraints_even_without_old_snapshot(constraint):
    plan = deepcopy(PLAN)
    facts = {}
    catalog = {'bench': {'id': 'bench', 'equipment': '杠铃/平凳'}}
    if constraint == 'new_equipment':
        facts['equipment'] = '只有哑铃'
    elif constraint == 'current_time':
        facts['session_minutes'] = 1
    else:
        facts['movement_constraints'] = '卧推当前不适'
    with pytest.raises(HTTPException) as error:
        module.periodization.activation_guard(plan, facts, {'items': [{'status': 'reference_only'}]}, catalog)
    assert error.value.status_code == 409
