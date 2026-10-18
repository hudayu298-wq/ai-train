import importlib
import os
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

temp = tempfile.TemporaryDirectory()
os.environ['FIT_DATA_DIR'] = temp.name
sys.path.insert(0, str(Path(__file__).parent))
module = importlib.import_module('app')
client = TestClient(module.app)
PROFILE = {'age': 28, 'height_cm': 175, 'weight_kg': 70, 'sex': 'male',
           'goal': 'muscle_gain', 'experience': 'beginner', 'days': 3}

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
