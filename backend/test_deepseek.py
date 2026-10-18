import asyncio
import json

import httpx
import pytest

from backend import ai_planner


@pytest.mark.parametrize('base,expected_url,deepseek', [
    ('https://api.deepseek.com', 'https://api.deepseek.com/chat/completions', True),
    ('https://api.deepseek.com/v1/', 'https://api.deepseek.com/v1/chat/completions', True),
    ('https://model.example/v1', 'https://model.example/v1/chat/completions', False),
])
def test_json_transport_is_compatible_with_deepseek_without_changing_other_providers(monkeypatch, base, expected_url, deepseek):
    monkeypatch.setattr(ai_planner, 'settings', lambda: {
        'AI_API_KEY': 'test-credential', 'AI_BASE_URL': base, 'AI_MODEL': 'deepseek-flash'})
    def handler(request):
        assert str(request.url) == expected_url
        assert request.headers['authorization'] == 'Bearer test-credential'
        body = json.loads(request.content)
        assert body['response_format'] == {'type': 'json_object'}
        assert body['max_tokens'] == 128
        if deepseek:
            assert body['thinking'] == {'type': 'disabled'}
        else:
            assert 'thinking' not in body
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop',
            'message': {'content': '{"ok": true}'}}]})
    original = httpx.AsyncClient
    monkeypatch.setattr(ai_planner.httpx, 'AsyncClient',
                        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    output, model = asyncio.run(ai_planner.chat_json([
        {'role': 'system', 'content': 'Respond with a JSON object.'}], max_tokens=128))
    assert output == {'ok': True}
    assert model == 'deepseek-flash'
