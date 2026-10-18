import importlib
import os
import sys
import tempfile
from pathlib import Path
from datetime import date
import pytest

from fastapi.testclient import TestClient

temp = tempfile.TemporaryDirectory()
os.environ['FIT_DATA_DIR'] = temp.name
sys.path.insert(0, str(Path(__file__).parent))
module = importlib.import_module('app')
client = TestClient(module.app)
PROFILE = {'age': 28, 'height_cm': 175, 'weight_kg': 70, 'sex': 'male',
           'goal': 'muscle_gain', 'experience': 'beginner', 'days': 3}
PLAN = {'name': '我的周计划', 'days': [{'name': '周一', 'exercises': [
    {'exercise_id': 'bench', 'weight_kg': 75, 'sets': 4, 'reps': 5, 'rest_seconds': 150}]}]}

@pytest.fixture(autouse=True)
def isolate_records():
    with module.connection() as db:
        db.execute('DELETE FROM records')

def test_user_plan_is_preserved_and_versioned():
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    first = client.post('/api/plans', json=PLAN).json()
    second = client.post('/api/plans', json=PLAN).json()
    assert first['id'] != second['id']
    assert len(first['days']) == 1
    assert first['days'][0]['exercises'][0]['weight_kg'] == 75
    assert first['days'][0]['exercises'][0]['sets'] == 4
    assert first['days'][0]['exercises'][0]['rest_seconds'] == 150
    assert first['source'] == 'user'
    assert first['assessment']['items'][0]['status'] == 'missing_rm'
    assert client.post('/api/plans').status_code == 422  # No automatic generation.

def test_restrictions_require_review_but_keep_user_plan():
    client.put('/api/profile', json={**PROFILE, 'restrictions': '肩部疼痛'})
    result = client.post('/api/plans', json=PLAN)
    assert result.status_code == 200
    assert result.json()['assessment']['items'][0]['status'] == 'review_required'
    client.put('/api/profile', json=PROFILE)

def test_nutrients_and_delete():
    response = client.post('/api/meals', json={'food_id': 'rice', 'grams': 150})
    meal = response.json()
    assert meal['nutrients']['kcal'] == 174
    assert meal['nutrients']['carbs'] == 38.9
    assert client.delete('/api/meals/' + meal['id']).status_code == 200
    assert client.delete('/api/meals/' + meal['id']).status_code == 404
    assert client.post('/api/meals', json={'food_id': 'unknown', 'grams': 150}).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': -1}).status_code == 422

def test_pain_does_not_prescribe_more_load():
    response = client.post('/api/training', json={'exercise_id': 'bench', 'weight_kg': 20,
        'sets': 3, 'reps': 5, 'rpe': 7, 'pain': True})
    assert response.status_code == 200
    assert '停止自动加重' in response.json()['feedback']

def test_media_is_pending_not_fake_analysis():
    result = client.post('/api/media', data={'kind': 'video', 'exercise_id': 'squat'},
                         files={'file': ('test.mp4', b'local-test', 'video/mp4')})
    assert result.status_code == 200
    assert result.json()['status'] == 'awaiting_integration'
    assert 'score' not in result.json()
    assert (Path(temp.name) / 'uploads' / result.json()['stored_name']).exists()

def test_reject_empty_and_wrong_media_type():
    assert client.post('/api/media', data={'kind': 'meal'},
        files={'file': ('empty.jpg', b'', 'image/jpeg')}).status_code == 422
    assert client.post('/api/media', data={'kind': 'meal'},
        files={'file': ('bad.txt', b'bad', 'text/plain')}).status_code == 415
    assert client.post('/api/media', data={'kind': 'video', 'exercise_id': 'unknown'},
        files={'file': ('test.mp4', b'local-test', 'video/mp4')}).status_code == 422

def test_validation_and_preview():
    assert client.put('/api/profile', json={**PROFILE, 'age': 12}).status_code == 422
    assert client.get('/').status_code == 200
    assert client.get('/api/health').json()['vision_enabled'] is False

def test_today_meal_groups_and_target_comparison():
    client.put('/api/profile', json=PROFILE)
    target = module.nutrition_target(PROFILE)
    client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'egg', 'grams': 100, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'chicken', 'grams': 100, 'meal_type': 'lunch'})
    summary = client.get('/api/nutrition/today').json()
    assert summary['totals'] == {'kcal': 494.0, 'protein': 47.5, 'fat': 14.7, 'carbs': 40.0}
    assert summary['groups'][0]['totals']['kcal'] == 329
    assert summary['groups'][1]['totals']['kcal'] == 165
    assert summary['target'] == target
    assert summary['comparison']['protein']['remaining'] == 64.5
    assert summary['comparison']['kcal']['excess'] == 0

def test_rollover_excludes_old_food_and_rejects_backdating(monkeypatch):
    monkeypatch.setattr(module, 'nutrition_today', lambda: date(2026, 10, 10))
    previous = client.post('/api/meals', json={'food_id': 'rice', 'grams': 150}).json()
    assert len(client.get('/api/meals').json()) == 1
    monkeypatch.setattr(module, 'nutrition_today', lambda: date(2026, 10, 11))
    assert client.get('/api/meals').json() == []
    summary = client.get('/api/nutrition/today').json()
    assert summary['totals']['kcal'] == 0
    assert summary['day'] == '2026-10-11'
    assert client.delete('/api/meals/' + previous['id']).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'day': '2026-10-10'}).status_code == 422
    assert client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'day': '2026-10-12'}).status_code == 422
    assert len(module.records('meal')) == 1  # History retained; not included in today's totals.

def test_excess_and_delete_recalculates_totals():
    client.put('/api/profile', json=PROFILE)
    meal = client.post('/api/meals', json={'food_id': 'rice', 'grams': 3000, 'meal_type': 'dinner'}).json()
    comparison = client.get('/api/nutrition/today').json()['comparison']['kcal']
    assert comparison['excess'] > 0
    assert comparison['remaining'] == 0
    assert comparison['percent'] > 100
    client.delete('/api/meals/' + meal['id'])
    assert client.get('/api/nutrition/today').json()['totals']['kcal'] == 0

def test_nutrition_targets_update_without_a_training_plan():
    assert client.get('/api/nutrition/today').json()['target_status'] == 'missing'
    client.put('/api/profile', json=PROFILE)
    assert client.get('/api/nutrition/today').json()['target']['protein'] == 112
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 75})
    summary = client.get('/api/nutrition/today').json()
    assert summary['target_status'] == 'ready'
    assert summary['target']['protein'] == 120
    assert client.get('/api/plans').json() == []

def test_rm_reference_and_draft_assessment_do_not_change_plan():
    rm = client.post('/api/rm', json={'exercise_id':'bench','weight_kg':87,'reps':5,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True}).json()
    assert rm['reference_1rm_kg'] == 100
    result = client.post('/api/plans/assess', json=PLAN).json()
    assert result['items'][0]['load_percent'] == 75
    assert result['items'][0]['reference_1rm_kg'] == 100
    assert result['items'][0]['status'] == 'reference_only'
    assert client.get('/api/plans').json() == []
    saved = client.post('/api/plans', json=PLAN).json()
    assert saved['days'][0]['exercises'][0]['weight_kg'] == 75

def test_rm_evaluation_flags_high_load_and_rejects_unsupported_rm():
    from copy import deepcopy
    client.post('/api/rm',json={'exercise_id':'bench','weight_kg':100,'reps':1,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True})
    plan = deepcopy(PLAN)
    plan['days'][0]['exercises'][0]['weight_kg'] = 95
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'high_relative_load'
    plan['days'][0]['exercises'][0]['weight_kg'] = 105
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'above_reference'
    assert client.post('/api/rm',json={'exercise_id':'bench','weight_kg':80,'reps':11,
        'measured_on':module.nutrition_today().isoformat(),'confirmed_maximum':True}).status_code == 422

def test_rm_expiry_future_dates_and_nonmaximum_sets(monkeypatch):
    monkeypatch.setattr(module,'nutrition_today',lambda:date(2026,10,11))
    fields={'exercise_id':'bench','weight_kg':100,'reps':1,'confirmed_maximum':True}
    assert client.post('/api/rm',json={**fields,'measured_on':'2026-10-12'}).status_code == 422
    client.post('/api/rm',json={**fields,'measured_on':'2026-06-01'})
    assert client.post('/api/plans/assess',json=PLAN).json()['items'][0]['status'] == 'stale_rm'
    client.post('/api/rm',json={**fields,'measured_on':'2026-10-11','confirmed_maximum':False})
    assert client.post('/api/plans/assess',json=PLAN).json()['items'][0]['status'] == 'missing_rm'

def test_rm_is_matched_by_variant_and_measurement_date(monkeypatch):
    monkeypatch.setattr(module,'nutrition_today',lambda:date(2026,10,11))
    fields={'exercise_id':'bench','reps':1,'confirmed_maximum':True}
    client.post('/api/rm',json={**fields,'weight_kg':100,'measured_on':'2026-10-10'})
    client.post('/api/rm',json={**fields,'weight_kg':80,'measured_on':'2026-10-01'})
    assert client.get('/api/rm').json()[0]['weight_kg'] == 100
    plan={'name':'深蹲','days':[{'name':'周二','exercises':[{**PLAN['days'][0]['exercises'][0],'exercise_id':'squat'}]}]}
    assert client.post('/api/plans/assess',json=plan).json()['items'][0]['status'] == 'missing_rm'

def test_old_generated_templates_are_not_active_user_plans():
    module.save('plan',{'status':'starter_template','days':[]})
    assert client.get('/api/plans').json() == []

def test_legacy_meals_are_not_silently_assigned_to_breakfast():
    module.save('meal', {'day': module.nutrition_today().isoformat(), 'name': '旧记录',
        'nutrients': {'kcal': 100, 'protein': 10, 'fat': 2, 'carbs': 10}})
    summary = client.get('/api/nutrition/today').json()
    assert summary['groups'][-1]['meal_type'] == 'unassigned'
    assert summary['totals']['kcal'] == 100

def ai_result():
    return {'name': 'AI周计划', 'days': [{'name': f'训练日{i + 1}',
        'exercises': [{**PLAN['days'][0]['exercises'][0], 'weight_kg': None}]} for i in range(3)],
        'rationale': '根据增肌目标安排', 'warmup': '逐步热身',
        'recovery': '训练日之间恢复', 'progression': '根据完成情况复核'}

def test_ai_generation_is_a_draft_and_preserves_provenance(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    async def fake(profile, rm, schema):
        assert profile['goal'] == 'muscle_gain'
        assert rm == {}
        return ai_result(), 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    result = client.post('/api/plans/generate', json={})
    assert result.status_code == 200
    draft = result.json()
    assert client.get('/api/plans').json() == []
    assert draft['assessment']['items'][0]['status'] == 'missing_load'
    saved = client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')})
    assert saved.status_code == 200
    assert saved.json()['source'] == 'ai'
    assert saved.json()['model'] == 'test-model'
    assert len(client.get('/api/plans').json()) == 1
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 80})
    assert client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')}).status_code == 409

def test_ai_rejects_invalid_day_count_and_excessive_load(monkeypatch):
    client.put('/api/profile', json=PROFILE)
    result = ai_result()
    async def fake(*args):
        return result, 'test-model'
    monkeypatch.setattr(module.ai_planner, 'generate', fake)
    result['days'].pop()
    assert client.post('/api/plans/generate').status_code == 502
    result['days'].append({'name': '训练日3', 'exercises': [PLAN['days'][0]['exercises'][0].copy()]})
    client.post('/api/rm', json={'exercise_id': 'bench', 'weight_kg': 50, 'reps': 1,
        'measured_on': module.nutrition_today().isoformat(), 'confirmed_maximum': True})
    assert client.post('/api/plans/generate').status_code == 502
    assert module.records('plan_draft') == []

def test_ai_missing_config_is_explicit_and_secrets_not_exposed(monkeypatch):
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: {'AI_API_KEY': '', 'AI_BASE_URL': '', 'AI_MODEL': ''})
    assert client.post('/api/plans/generate').status_code == 422
    client.put('/api/profile', json=PROFILE)
    assert client.post('/api/plans/generate').status_code == 503
    assert client.get('/api/ai/status').json()['configured'] is False
    monkeypatch.setattr(module.ai_planner, 'settings', lambda: {'AI_API_KEY': 'secret', 'AI_BASE_URL': 'https://example.com', 'AI_MODEL': 'test'})
    assert 'secret' not in client.get('/api/ai/status').text
