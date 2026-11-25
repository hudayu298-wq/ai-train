"""Regional strength intake and complete, provenance-labelled initial load proposals."""
from copy import deepcopy
from datetime import timedelta

import pytest

from test_app import module, client, PROFILE, isolate_records, ai_result


def intake(**overrides):
    body = {'items': [
        {'region': region, 'exercise_id': exercise, 'weight_kg': weight, 'reps': 8, 'rir': 2,
            'measured_on': module.nutrition_today().isoformat(), 'equipment_id': '', 'pain': False, 'confirmed': True}
        for region, exercise, weight in [('chest', 'bench', 60), ('back', 'barbell_row', 40), ('legs', 'squat', 80)]],
        'base_revision': client.get('/api/strength-profile').json()['revision']}
    return {**body, **overrides}


def ready():
    response = client.put('/api/strength-profile', json=intake())
    assert response.status_code == 200, response.text
    return response.json()


def fake_plan(monkeypatch, *, extra=False):
    raw = ai_result()
    if extra:
        raw['days'][0]['exercises'].append({'exercise_id': 'dumbbell_bench', 'weight_kg': 15,
            'sets': 3, 'reps': 8, 'rest_seconds': 120})
    async def fake(profile, rms, schema):
        assert profile['regional_strength']['ready']
        assert {a['region'] for a in profile['regional_strength']['items']} == {'chest', 'back', 'legs'}
        assert schema['$defs']['PlanExercise']['properties']['weight_kg']['type'] == 'number'
        return deepcopy(raw), 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    return raw


def test_three_actual_anchors_are_private_profile_not_rm_or_workouts():
    assert client.get('/api/strength-profile').json()['ready'] is False
    state = ready()
    assert state['ready'] and len(state['items']) == 3
    assert all(a['source'] == 'user_reported_performance' for a in state['items'])
    assert client.get('/api/rm').json() == []
    assert module.records('workout') == []
    assert client.get('/api/coach/profile').json()['strength_profile']['revision'] == state['revision']


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'wrong_region', 'unconfirmed', 'future', 'stale', 'nan', 'boolean_weight'])
def test_invalid_intake_is_atomic(change):
    body = intake()
    if change == 'missing': body['items'].pop()
    if change == 'duplicate': body['items'][1] = body['items'][0]
    if change == 'wrong_region': body['items'][0]['exercise_id'] = 'squat'
    if change == 'unconfirmed': body['items'][0]['confirmed'] = False
    if change == 'future': body['items'][0]['measured_on'] = (module.nutrition_today()+timedelta(days=1)).isoformat()
    if change == 'stale': body['items'][0]['measured_on'] = (module.nutrition_today()-timedelta(days=91)).isoformat()
    if change == 'nan': body['items'][0]['weight_kg'] = 'NaN'
    if change == 'boolean_weight': body['items'][0]['weight_kg'] = True
    assert client.put('/api/strength-profile', json=body).status_code == 422
    assert module.records('strength_profile') == []


def test_machine_units_require_identity_and_pain_is_not_ready():
    body = intake()
    body['items'][0].update(exercise_id='chest_press_machine')
    assert client.put('/api/strength-profile', json=body).status_code == 422
    body['items'][0].update(equipment_id='器械A', pain=True)
    result = client.put('/api/strength-profile', json=body)
    assert result.status_code == 200 and result.json()['ready'] is False
    assert result.json()['missing'][0]['region'] == 'chest'
    body = intake()
    body['items'][0].update(exercise_id='chest_press_machine', equipment_id='器械A')
    result = client.put('/api/strength-profile', json=body)
    assert result.status_code == 200 and result.json()['ready']
    assert '不跨器械' in result.json()['items'][0]['unit_label']


def test_missing_strength_blocks_all_generation_before_model_call(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    async def forbidden(*args): raise AssertionError('must not call model with incomplete strength')
    monkeypatch.setattr(module.ai_planner, 'generate', forbidden)
    response = client.post('/api/plans/generate')
    assert response.status_code == 422 and '胸' in response.json()['detail'] and '背' in response.json()['detail']
    assert not client.get('/api/onboarding').json()['profile_ready']
    assert module.records('plan_draft') == []


def test_full_plan_loads_have_provenance_and_never_create_inferred_rm(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    state = ready()
    fake_plan(monkeypatch, extra=True)
    response = client.post('/api/plans/generate')
    assert response.status_code == 200, response.text
    draft = response.json()
    for week in draft['cycle_schedule']:
        assert all(e['weight_kg'] > 0 and e['load_reference'] for d in week['days'] for e in d['exercises'])
    a, b = draft['days'][0]['exercises']
    assert a['load_reference']['kind'] == 'reported_performance'
    assert b['load_reference']['kind'] == 'regional_estimate'
    assert b['load_reference']['needs_calibration'] and b['load_reference']['strength_revision'] == state['revision']
    body = {k: draft[k] for k in ('name', 'days', 'generation_id')}
    body['cycle_schedule'] = deepcopy(draft['cycle_schedule'])
    for week in body['cycle_schedule']:
        for day in week['days']:
            for exercise in day['exercises']:
                exercise['load_reference'] = {'kind': 'confirmed_rm', 'needs_calibration': False}
    body['days'][0]['exercises'][1]['load_reference'] = {'kind': 'confirmed_rm', 'needs_calibration': False}
    result = client.post('/api/plans', json=body)
    assert result.status_code == 200, result.text
    assert result.json()['days'][0]['exercises'][1]['load_reference']['kind'] == 'regional_estimate'
    assert all(e['load_reference']['kind'] in ('regional_estimate', 'reported_performance')
        for week in result.json()['cycle_schedule'] for day in week['days'] for e in day['exercises'])
    assert client.get('/api/rm').json() == []
    assert module.records('workout') == []


@pytest.mark.parametrize('value', [None, 0, -1, 501])
def test_generation_never_returns_or_saves_blank_or_invalid_loads(monkeypatch, value):
    client.put('/api/profile', json=PROFILE)
    ready()
    raw = ai_result()
    raw['days'][0]['exercises'][0]['weight_kg'] = value
    async def fake(*args): return raw, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    response = client.post('/api/plans/generate')
    assert response.status_code == 502
    assert module.records('plan_draft') == []


def test_rm_limit_still_wins_over_regional_strength(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    ready()
    client.post('/api/rm', json={'exercise_id': 'bench', 'weight_kg': 50, 'reps': 1,
        'confirmed_maximum': True, 'measured_on': module.nutrition_today().isoformat()})
    fake_plan(monkeypatch)
    assert client.post('/api/plans/generate').status_code == 502


def test_strength_update_invalidates_generation_and_confirmation(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    ready()
    fake_plan(monkeypatch)
    draft = client.post('/api/plans/generate').json()
    changed = intake()
    changed['items'][0]['weight_kg'] = 55
    assert client.put('/api/strength-profile', json=changed).status_code == 200
    response = client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')})
    assert response.status_code == 409 and '力量资料' in response.text
    async def concurrent(*args):
        new = intake()
        new['items'][0]['weight_kg'] = 58
        assert client.put('/api/strength-profile', json=new).status_code == 200
        return ai_result(), 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', concurrent)
    assert client.post('/api/plans/generate').status_code == 409


def test_expired_or_changed_catalog_anchor_is_not_used(monkeypatch):
    ready()
    with module.connection() as db:
        entry = db.catalog_read('exercises', 'bench')
        db.catalog_update('exercises', 'bench', payload={**entry, 'weight_basis': '已改变的重量口径'})
    assert not client.get('/api/strength-profile').json()['ready']
    ready()
    monkeypatch.setattr(module.strength_profile, 'today', lambda: module.nutrition_today()+timedelta(days=91))
    assert not client.get('/api/strength-profile').json()['ready']


def test_owner_isolation_and_stale_write_revision():
    first = ready()
    old = intake(base_revision=None)
    assert client.put('/api/strength-profile', json=old).status_code == 409
    headers = dict(client.headers)
    with module.database.get_engine(module.DB).begin() as db:
        user = module.auth.new_user(db, email='strength-other@example.test', password_hash=module.auth.DUMMY_HASH)
        access = module.auth.create_session(db, user, 'test')['access_token']
    try:
        client.headers['Authorization'] = 'Bearer ' + access
        result = client.get('/api/strength-profile').json()
        assert result['items'] == [] and result['revision'] is None
        assert client.put('/api/strength-profile', json=intake(base_revision=first['revision'])).status_code == 409
    finally:
        client.headers.clear()
        client.headers.update(headers)
