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

@pytest.fixture(autouse=True)
def isolate_records():
    with module.connection() as db:
        db.execute('DELETE FROM records')

def test_profile_and_versioned_plan():
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    first = client.post('/api/plans').json()
    second = client.post('/api/plans').json()
    assert first['id'] != second['id']
    assert len(first['days']) == 3
    assert {x['exercise_id'] for x in first['days'][0]['exercises']} == {'bench', 'squat', 'deadlift'}
    assert first['nutrition']['protein'] == 112
    assert first['profile_snapshot']['weight_kg'] == 70

def test_restrictions_block_template():
    client.put('/api/profile', json={**PROFILE, 'restrictions': '肩部疼痛'})
    assert client.post('/api/plans').status_code == 409
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
    plan = client.post('/api/plans').json()
    client.post('/api/meals', json={'food_id': 'rice', 'grams': 150, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'egg', 'grams': 100, 'meal_type': 'breakfast'})
    client.post('/api/meals', json={'food_id': 'chicken', 'grams': 100, 'meal_type': 'lunch'})
    summary = client.get('/api/nutrition/today').json()
    assert summary['totals'] == {'kcal': 494.0, 'protein': 47.5, 'fat': 14.7, 'carbs': 40.0}
    assert summary['groups'][0]['totals']['kcal'] == 329
    assert summary['groups'][1]['totals']['kcal'] == 165
    assert summary['target'] == plan['nutrition']
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
    client.post('/api/plans')
    meal = client.post('/api/meals', json={'food_id': 'rice', 'grams': 3000, 'meal_type': 'dinner'}).json()
    comparison = client.get('/api/nutrition/today').json()['comparison']['kcal']
    assert comparison['excess'] > 0
    assert comparison['remaining'] == 0
    assert comparison['percent'] > 100
    client.delete('/api/meals/' + meal['id'])
    assert client.get('/api/nutrition/today').json()['totals']['kcal'] == 0

def test_missing_or_stale_targets_do_not_claim_zero_requirement():
    assert client.get('/api/nutrition/today').json()['target_status'] == 'missing'
    client.put('/api/profile', json=PROFILE)
    client.post('/api/plans')
    client.put('/api/profile', json={**PROFILE, 'weight_kg': 75})
    summary = client.get('/api/nutrition/today').json()
    assert summary['target_status'] == 'stale'
    assert summary['comparison']['kcal']['target'] is None
    assert summary['comparison']['protein']['remaining'] is None

def test_legacy_meals_are_not_silently_assigned_to_breakfast():
    module.save('meal', {'day': module.nutrition_today().isoformat(), 'name': '旧记录',
        'nutrients': {'kcal': 100, 'protein': 10, 'fat': 2, 'carbs': 10}})
    summary = client.get('/api/nutrition/today').json()
    assert summary['groups'][-1]['meal_type'] == 'unassigned'
    assert summary['totals']['kcal'] == 100
