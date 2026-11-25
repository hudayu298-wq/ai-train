"""Cross-module consent regressions; provider calls are mocked and never leave the process."""
import copy
import json
from datetime import datetime, timezone
from fastapi import HTTPException

from test_app import module, client, PROFILE, isolate_records, ai_result, complete_strength_profile
from test_nutrition_guidance import api, seed_window, make
from test_mobility import body as mobility_body


def fail_checkpoint(monkeypatch, request_id):
    captured = []

    async def interrupted(messages, tools, **kwargs):
        captured.append(copy.deepcopy(messages))
        raise HTTPException(502, 'simulated provider interruption')

    monkeypatch.setattr(module.ai_planner, 'tool_turn', interrupted)
    response = client.post('/api/agent/runs', json={'request_id': request_id, 'message': '请结合我的记录给出建议'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'failed'
    assert len(captured) == 1
    return response.json()['run_id'], captured


def captured_context(messages):
    return json.loads(messages[1]['content'])['context']


def confirm_calibration(api):
    baseline = seed_window(api)
    suggestion = make(api, 'audit-calibration-request').json()
    result = api.post('/api/nutrition-guidance/suggestions/' + suggestion['id'] + '/confirm',
        json={'request_id': 'audit-calibration-confirm'})
    assert result.status_code == 200, result.text
    assert client.get('/api/nutrition/today').json()['target']['kcal'] == baseline + 100
    return baseline, suggestion


def test_resume_does_not_resend_revoked_mobility_context(monkeypatch):
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': True}).status_code == 200
    assert client.post('/api/mobility/measurements', json=mobility_body()).status_code == 200
    run_id, sent = fail_checkpoint(monkeypatch, 'audit-mobility-resume')
    assert captured_context(sent[0])['mobility_context']['enabled'] is True
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': False}).status_code == 200
    response = client.post('/api/agent/runs/' + run_id + '/resume')
    assert response.status_code == 409, response.text
    assert len(sent) == 1, 'revoked mobility summary must not be sent to the provider again'


def test_running_agent_rechecks_consent_before_tools_and_second_provider_call(monkeypatch):
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': True}).status_code == 200
    assert client.post('/api/mobility/measurements', json=mobility_body()).status_code == 200
    calls = []

    async def revoke_between_calls(messages, tools, **kwargs):
        calls.append(copy.deepcopy(messages))
        assert len(calls) == 1, 'revoked data must not be sent during another provider call'
        with module.connection() as db:
            db.write('mobility_settings', 'settings', {'storage_enabled': True, 'ai_context_enabled': False})
        return {'model': 'test-model', 'message': {'role': 'assistant', 'content': None, 'tool_calls': [
            {'id': 'audit-get-context', 'type': 'function',
             'function': {'name': 'get_user_context', 'arguments': '{}'}}]},
            'usage': {'total_tokens': 1}}

    monkeypatch.setattr(module.ai_planner, 'tool_turn', revoke_between_calls)
    response = client.post('/api/agent/runs', json={'request_id': 'audit-running-revoke', 'message': '请结合我的记录给出建议'})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'failed'
    assert len(calls) == 1
    with module.connection() as db:
        run = db.read('agent_run', response.json()['run_id'])
    assert not any(step.get('type') == 'tool' and step.get('name') == 'get_user_context'
        and step.get('result', {}).get('mobility_context', {}).get('enabled') is True for step in run['steps'])


def test_new_agent_does_not_reintroduce_revoked_record_summary_through_assistant_history(monkeypatch):
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': True}).status_code == 200
    assert client.post('/api/mobility/measurements', json=mobility_body()).status_code == 200
    derived_reply = '根据活动度记录，你的左侧膝触墙均值为8.1cm。'
    calls = []

    async def final(messages, tools, **kwargs):
        calls.append(copy.deepcopy(messages))
        return {'model': 'test-model', 'message': {'role': 'assistant', 'content': json.dumps({
            'reply': derived_reply if len(calls) == 1 else '请告诉我今天想讨论什么。',
            'profile_updates': [], 'citations': []}, ensure_ascii=False)}, 'usage': {'total_tokens': 1}}

    monkeypatch.setattr(module.ai_planner, 'tool_turn', final)
    first = client.post('/api/agent/runs', json={'request_id': 'audit-history-before', 'message': '请结合我的记录给出建议'})
    assert first.status_code == 200 and first.json()['status'] == 'completed'
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': False}).status_code == 200
    second = client.post('/api/agent/runs', json={'request_id': 'audit-history-after', 'message': '你好'})
    assert second.status_code == 200 and second.json()['status'] == 'completed'
    assert captured_context(calls[-1])['mobility_context']['enabled'] is False
    assert derived_reply not in json.dumps(calls[-1], ensure_ascii=False), 'revoked record-derived values must not return through assistant history'


def test_plan_generated_during_mobility_consent_change_is_not_saved(monkeypatch):
    complete_strength_profile()
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': True}).status_code == 200
    assert client.post('/api/mobility/measurements', json=mobility_body()).status_code == 200

    async def consent_changes_during_generation(profile, *args):
        assert profile['mobility_context']['enabled'] is True
        with module.connection() as db:
            db.write('mobility_settings', 'settings', {'storage_enabled': True, 'ai_context_enabled': False})
        return ai_result(), 'test-model'

    monkeypatch.setattr(module.ai_planner, 'generate', consent_changes_during_generation)
    response = client.post('/api/plans/generate')
    assert response.status_code == 409
    assert module.records('plan_draft') == []


def test_plan_confirmation_rechecks_mobility_basis_used_by_generation(monkeypatch):
    complete_strength_profile()
    assert client.put('/api/profile', json=PROFILE).status_code == 200
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': True}).status_code == 200
    assert client.post('/api/mobility/measurements', json=mobility_body()).status_code == 200

    async def generate(profile, *args):
        assert profile['mobility_context']['enabled'] is True
        return ai_result(), 'test-model'

    monkeypatch.setattr(module.ai_planner, 'generate', generate)
    response = client.post('/api/plans/generate')
    assert response.status_code == 200, response.text
    draft = response.json()
    assert client.put('/api/mobility/settings', json={'storage_enabled': True, 'ai_context_enabled': False}).status_code == 200
    response = client.post('/api/plans', json={k: draft[k] for k in ('name', 'days', 'generation_id')})
    assert response.status_code == 409
    assert module.records('plan') == []


def test_resume_does_not_resend_calibrated_target_after_health_storage_revoked(api, monkeypatch):
    baseline, _ = confirm_calibration(api)
    # Health AI summaries remain off throughout; nutrition has its separate consent.
    assert client.get('/api/health-data/settings').json()['ai_context_enabled'] is False
    run_id, sent = fail_checkpoint(monkeypatch, 'audit-calibration-resume')
    assert captured_context(sent[0])['nutrition']['target']['kcal'] == baseline + 100
    assert client.put('/api/health-data/settings', json={'storage_enabled': False, 'ai_context_enabled': False}).status_code == 200
    assert client.get('/api/nutrition/today').json()['target']['kcal'] == baseline
    response = client.post('/api/agent/runs/' + run_id + '/resume')
    assert response.status_code == 409, response.text
    assert len(sent) == 1, 'checkpoint must not restore a target whose evidence consent was withdrawn'


def test_source_correction_invalidates_calibration_built_from_that_measurement(api):
    baseline, _ = confirm_calibration(api)
    with module.connection() as db:
        row = next(r for r in module.health_data.rows(db, days=16)
            if r['external_id'].startswith('weight-window-'))
    payload = {k: v for k, v in row.items() if k in module.health_data.Observation.model_fields}
    payload.update(value=73, source_updated_at=datetime.now(timezone.utc).isoformat())
    response = client.post('/api/health-data/measurements', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['id'] == row['id']
    current = client.get('/api/nutrition/today').json()
    assert current['target']['kcal'] == baseline
    assert current['target_basis']['target_source'] == 'formula_estimate'


def test_private_checkpoint_measurement_and_calibration_owner_isolation(api, monkeypatch):
    _, suggestion = confirm_calibration(api)
    assert client.put('/api/mobility/settings', json={'storage_enabled': True}).status_code == 200
    measurement = client.post('/api/mobility/measurements', json=mobility_body()).json()
    run_id, sent = fail_checkpoint(monkeypatch, 'audit-owner-checkpoint')
    with module.connection() as db:
        other = module.auth.new_user(db.conn, email='cross-context-owner@example.com')
        access = module.auth.create_session(db.conn, other, 'test')['access_token']
    saved_client, saved_api = client.headers['Authorization'], api.headers['Authorization']
    client.headers['Authorization'] = api.headers['Authorization'] = 'Bearer ' + access
    try:
        assert client.post('/api/agent/runs/' + run_id + '/resume').status_code == 404
        assert client.get('/api/mobility/measurements').json()['items'] == []
        assert client.delete('/api/mobility/measurements/' + measurement['id']).status_code == 404
        assert api.get('/api/nutrition-guidance/suggestions').json()['items'] == []
        assert api.post('/api/nutrition-guidance/suggestions/' + suggestion['id'] + '/confirm',
            json={'request_id': 'cross-owner-confirm'}).status_code == 404
        assert len(sent) == 1
    finally:
        client.headers['Authorization'], api.headers['Authorization'] = saved_client, saved_api
