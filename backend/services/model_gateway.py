"""Provider boundary shared by structured tasks and bounded tool execution."""
import time
from contextvars import ContextVar
from contextlib import contextmanager
import httpx
from fastapi import HTTPException


budget_context = ContextVar('model_budget', default=None)


@contextmanager
def budget(events, max_calls=7, max_tokens=30000):
    token = budget_context.set((events, max_calls, max_tokens))
    try:
        yield
    finally:
        budget_context.reset(token)


def begin_event(model, *, kind='generation'):
    scope = budget_context.get()
    event = None
    if scope:
        events, call_limit, token_limit = scope
        if len(events) >= call_limit or sum(e.get('usage', {}).get('total_tokens') or 0 for e in events) >= token_limit:
            raise HTTPException(429, '模型任务预算已用完，请缩小任务范围')
        event = {'status': 'started', 'model': model, 'kind':kind}
        events.append(event)
    return event


async def complete(messages, config, *, tools=None, max_tokens=4000):
    event=begin_event(config['AI_MODEL'])
    if not all(config.values()):
        raise HTTPException(503, '请在后端配置AI_API_KEY、AI_BASE_URL和AI_MODEL')
    try:
        url = httpx.URL(config['AI_BASE_URL'])
    except httpx.InvalidURL:
        raise HTTPException(503, 'AI_BASE_URL格式无效') from None
    if url.scheme != 'https' and not (url.scheme == 'http' and url.host in ('localhost', '127.0.0.1')):
        raise HTTPException(503, 'AI_BASE_URL必须使用HTTPS')
    payload = {'model': config['AI_MODEL'], 'messages': messages, 'max_tokens': max_tokens,
        'response_format': {'type': 'json_object'}}
    if tools:
        payload['tools'] = tools
        payload['tool_choice'] = 'auto'
    if url.host == 'api.deepseek.com':
        payload['thinking'] = {'type': 'disabled'}
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90, connect=15)) as client:
            response = await client.post(str(url).rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + config['AI_API_KEY']}, json=payload)
        if response.status_code in (401, 403):
            raise HTTPException(502, '模型服务拒绝访问，请检查API密钥和模型权限')
        if response.status_code == 429:
            raise HTTPException(502, '模型服务额度不足或请求过多，请检查余额后重试')
        if response.status_code >= 400:
            raise HTTPException(502, '模型服务请求失败，请检查服务地址、模型与工具/JSON输出支持')
        raw = response.json()
        choice = raw['choices'][0]
        allowed = ('stop', 'tool_calls') if tools is not None else ('stop',)
        if choice.get('finish_reason') not in allowed:
            raise HTTPException(502, 'AI回复不完整，请重试')
        message = {k: v for k, v in choice['message'].items() if k in ('content', 'tool_calls')}
        message['role'] = 'assistant'
        usage = {k: raw.get('usage', {}).get(k) for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        if event is not None:
            event.update(status='completed', usage=usage, latency_ms=round((time.monotonic() - started) * 1000))
        return {'message': message, 'model': raw.get('model') or config['AI_MODEL'], 'usage': usage,
            'latency_ms': round((time.monotonic() - started) * 1000), 'finish_reason': choice['finish_reason']}
    except httpx.TimeoutException:
        raise HTTPException(504, 'AI回复超时，请稍后重试') from None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        raise HTTPException(502, 'AI服务连接失败或返回内容无效，请重试') from None
