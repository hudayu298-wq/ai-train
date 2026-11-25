"""Behavioral coverage: authorization, owner isolation, evidence and stale confirmation."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from test_app import module, client, PROFILE, isolate_records
import nutrition_guidance as guidance
from services import nutrition


@pytest.fixture
def api(monkeypatch, isolate_records):
    stamp = datetime.now(timezone.utc).replace(microsecond=0)
    monkeypatch.setattr(guidance, 'now', lambda: stamp)
    monkeypatch.setattr(module.health_data, 'today', lambda: stamp.astimezone(guidance.TZ).date())
    app = FastAPI()
    module.auth.install_middleware(app, module.DB)
    app.include_router(guidance.router(module.connection))
    result = TestClient(app)
    result.headers['Authorization'] = client.headers['Authorization']
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    return result


def authorize(api):
    assert client.put('/api/health-data/settings', json={'storage_enabled': True, 'ai_context_enabled': False}).status_code == 200
    config = {**nutrition.default_settings(), 'eligibility': 'eligible', 'calibration_enabled': True}
    assert api.put('/api/nutrition-guidance/settings', json=config).status_code == 200
    return config


def seed_window(api, *, rate=0.0, calorie_offset=0, weight_days=14, portion='weighed', goal='muscle_gain'):
    user = {**PROFILE, 'goal': goal}
    assert client.put('/api/profile', json=user).status_code == 200
    config = authorize(api)
    baseline = nutrition.target(user, config)['kcal']
    with module.connection() as db:
        for index in range(14):
            day = guidance.today() - timedelta(days=14 - index)
            stamp = datetime.combine(day, datetime.min.time(), guidance.TZ) + timedelta(hours=7)
            day = day.isoformat()
            db.write('nutrition_diary', day, {'status': 'complete'})
            db.write('meal', 'window-' + day, {'day': day, 'name': '全天食物（测试夹具）', 'portion_confirmed': True,
                'portion_source': portion, 'nutrients': {'kcal': baseline + calorie_offset, 'protein': 112, 'fat': 56, 'carbs': 300}})
            if index < weight_days:
                module.health_data.store(db, module.health_data.Observation(metric='weight_kg',
                    value=70 * (1 + (rate / 100 if index >= 7 else 0)), unit='kg',
                    observed_at=stamp, external_id='weight-window-' + day, device='同一体重秤',
                    method='scale', conditions='晨起如厕后'))
    return baseline


def make(api, key='calibration-request-1'):
    return api.post('/api/nutrition-guidance/suggestions', json={'request_id': key})


def test_formula_registry_units_scope_and_effective_summary(api):
    response = api.get('/api/nutrition-guidance/target').json()
    assert response['target'] == {'kcal': 2522, 'protein': 112, 'fat': 56, 'carbs': 392}
    assert response['steps'][0]['value'] == 1658.8
    assert response['warnings']
    assert all(rule['unit'] and rule['version'] and rule['population'] for rule in response['rules'])
    resting = next(r for r in response['rules'] if r['id'] == 'resting_energy')
    assert resting['product_default'] is False and resting['source_ids'] == ['mifflin-1990']
    config = {**nutrition.default_settings(), 'activity_factor': 1.6, 'protein_g_per_kg': 1.8}
    assert api.put('/api/nutrition-guidance/settings', json=config).status_code == 200
    effective = api.get('/api/nutrition-guidance/target').json()['target']
    assert effective['protein'] == 126 and effective['kcal'] != response['target']['kcal']
    assert client.get('/api/nutrition/today').json()['target'] == effective
    assert client.get('/api/nutrition/today').json()['target_basis']['version'] == nutrition.RULE_VERSION


def test_consent_missing_data_and_no_inferred_zero_intake(api):
    assessment = api.get('/api/nutrition-guidance/calibration').json()
    assert assessment['status'] == 'consent_required'
    authorize(api)
    assert make(api).status_code == 422
    assessment = api.get('/api/nutrition-guidance/calibration').json()
    assert assessment['complete_diet_days'] == 0
    assert assessment['weight_days'] == {'first_week': 0, 'second_week': 0}
    assert 'mean_intake_kcal' not in assessment
    assert api.get('/api/nutrition-guidance/suggestions').json() == {'items': []}


def test_suggestion_confirm_idempotence_effective_target_and_cooldown(api):
    baseline = seed_window(api)
    initial = make(api)
    assert initial.status_code == 200, initial.text
    draft = initial.json()
    assert draft == make(api).json()
    assert draft['assessment']['change_kcal'] == 100
    assert client.get('/api/nutrition/today').json()['target']['kcal'] == baseline
    confirm = '/api/nutrition-guidance/suggestions/' + draft['id'] + '/confirm'
    body = {'request_id': 'confirm-request-1'}
    applied = api.post(confirm, json=body)
    assert applied.status_code == 200, applied.text
    assert applied.json() == api.post(confirm, json=body).json()
    assert api.post(confirm, json={'request_id': 'confirm-request-2'}).status_code == 409
    summary = client.get('/api/nutrition/today').json()
    assert summary['target']['kcal'] == baseline + 100
    assert summary['target_basis']['target_source'] == 'confirmed_calibration'
    assert api.get('/api/nutrition-guidance/calibration').json()['status'] == 'cooldown'
    assert client.get('/api/health-data/settings').json()['ai_context_enabled'] is False


@pytest.mark.parametrize('mutation', ['meal', 'diary', 'weight', 'profile', 'settings', 'consent'])
def test_confirmation_rechecks_basis_and_consent(api, mutation):
    baseline = seed_window(api)
    draft = make(api).json()
    with module.connection() as db:
        day = (guidance.today() - timedelta(days=1)).isoformat()
        if mutation == 'meal':
            record = db.read('meal', 'window-' + day)
            record['nutrients']['kcal'] += 10
            db.write('meal', 'window-' + day, record)
        if mutation == 'diary':
            db.write('nutrition_diary', day, {'status': 'partial'})
        if mutation == 'weight':
            module.health_data.store(db, module.health_data.Observation(metric='weight_kg', value=70.1, unit='kg',
                observed_at=guidance.now() - timedelta(days=1), external_id='new-weight-record',
                device='同一体重秤', method='scale', conditions='晨起如厕后'))
    if mutation == 'profile':
        client.put('/api/profile', json={**PROFILE, 'weight_kg': 71})
    if mutation == 'settings':
        api.put('/api/nutrition-guidance/settings', json={**authorize(api), 'activity_factor': 1.5})
    if mutation == 'consent':
        client.put('/api/health-data/settings', json={'storage_enabled': False, 'ai_context_enabled': False})
    result = api.post('/api/nutrition-guidance/suggestions/' + draft['id'] + '/confirm', json={'request_id': 'changed-confirm-1'})
    assert result.status_code == 409, result.text
    with module.connection() as db:
        assert db.read('nutrition_active_target', 'current') is None


def test_expiry_and_owner_isolation(api, monkeypatch):
    seed_window(api)
    draft = make(api).json()
    with module.connection() as db:
        other = module.auth.new_user(db.conn, email='nutrition-other@example.com')
        access = module.auth.create_session(db.conn, other, 'test')['access_token']
    original = api.headers['Authorization']
    api.headers['Authorization'] = 'Bearer ' + access
    assert api.get('/api/nutrition-guidance/settings').json() == nutrition.default_settings()
    assert api.get('/api/nutrition-guidance/suggestions').json() == {'items': []}
    confirm = '/api/nutrition-guidance/suggestions/' + draft['id'] + '/confirm'
    assert api.post(confirm, json={'request_id': 'isolated-confirm-1'}).status_code == 404
    api.headers['Authorization'] = original
    stamp = guidance.now() + timedelta(hours=48)
    monkeypatch.setattr(guidance, 'now', lambda: stamp)
    assert api.post(confirm, json={'request_id': 'expired-confirm-1'}).status_code == 409


@pytest.mark.parametrize('kwargs,status', [
    ({'weight_days': 8}, 'insufficient_data'),
    ({'portion': 'estimated'}, 'insufficient_data'),
    ({'calorie_offset': -800}, 'adherence_review'),
    ({'rate': 1.5}, 'needs_review'),
    ({'rate': 0.2}, 'maintain'),
])
def test_observation_quality_stops_adjustment(api, kwargs, status):
    seed_window(api, **kwargs)
    assessment = api.get('/api/nutrition-guidance/calibration').json()
    assert assessment['status'] == status
    assert assessment['eligible'] is False


@pytest.mark.parametrize('goal,rate,change', [
    ('fat_loss', 0, -100),
    ('fat_loss', -0.9, 100),
    ('muscle_gain', 0.6, -100),
])
def test_trend_direction_matches_goal(api, goal, rate, change):
    baseline = seed_window(api, goal=goal, rate=rate)
    draft = make(api).json()
    assert draft['assessment']['change_kcal'] == change
    assert draft['assessment']['proposed_target']['kcal'] == baseline + change
    assert client.get('/api/nutrition/today').json()['target']['kcal'] == baseline


def test_device_energy_excluded_same_source_and_current_day_excluded(api):
    seed_window(api)
    before = api.get('/api/nutrition-guidance/calibration').json()
    with module.connection() as db:
        module.health_data.store(db, module.health_data.Observation(metric='active_energy_kcal', value=2000, unit='kcal',
            observed_at=guidance.now() - timedelta(days=1), end_at=guidance.now() - timedelta(hours=1),
            external_id='wearable-energy-test', method='wearable', provider='health_connect'))
        # An incompatible source cannot contaminate the chosen comparable source.
        module.health_data.store(db, module.health_data.Observation(metric='weight_kg', value=120, unit='kg',
            observed_at=guidance.now() - timedelta(days=1), external_id='other-device-test', device='其他体重秤', method='scale'))
        db.write('meal', 'current-day-test', {'day': guidance.today().isoformat(),
            'portion_source': 'estimated', 'nutrients': {'kcal': 9000, 'protein': 0, 'fat': 0, 'carbs': 0}})
    after = api.get('/api/nutrition-guidance/calibration').json()
    assert before == after
    assert after['device_energy_added_kcal'] == 0


def test_settings_validation_review_and_revoke_invalidate_active_target(api):
    assert api.put('/api/nutrition-guidance/settings', json={'activity_factor': 0.5}).status_code == 422
    assert api.put('/api/nutrition-guidance/settings', json={'calibration_enabled': True}).status_code == 422
    assert api.put('/api/nutrition-guidance/settings', json={'energy_adjustment_kcal': -100}).status_code == 422
    seed_window(api)
    draft = make(api).json()
    api.post('/api/nutrition-guidance/suggestions/' + draft['id'] + '/confirm', json={'request_id': 'revoke-confirm-1'})
    config = {**nutrition.default_settings(), 'eligibility': 'eligible', 'calibration_enabled': False}
    assert api.put('/api/nutrition-guidance/settings', json=config).status_code == 200
    assert api.get('/api/nutrition-guidance/target').json()['target_source'] == 'formula_estimate'
    assert api.put('/api/nutrition-guidance/settings', json={'eligibility': 'needs_professional_review'}).status_code == 200
    assert client.get('/api/nutrition/today').json()['target_status'] == 'needs_review'


def test_nutrition_knowledge_matches_executable_registry():
    from services.knowledge_nutrition import install_nutrition
    from knowledge_models import Bundle
    sources, nodes = [], []
    install_nutrition(sources, nodes)
    bundle = Bundle(version=nutrition.RULE_VERSION, name='营养定量规则', sources=sources, items=nodes)
    assert len(bundle.items) == len(nutrition.rules())
    assert {item.facts['rule_ids'][0] for item in bundle.items} == {rule['id'] for rule in nutrition.rules()}
