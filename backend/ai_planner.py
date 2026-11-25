"""Server-side, configurable Chat Completions provider; no template fallback."""
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values
from fastapi import HTTPException


def settings():
    file = dotenv_values(Path(__file__).resolve().parent.parent / '.env')
    return {key: os.environ.get(key, file.get(key) or '') for key in
            ('AI_API_KEY', 'AI_BASE_URL', 'AI_MODEL')}


def status():
    config = settings()
    return {'configured': all(config.values()), 'model': config['AI_MODEL'],
            'message': 'AI服务已配置' if all(config.values()) else '请在后端配置AI_API_KEY、AI_BASE_URL和AI_MODEL'}


try:
    from .services import model_gateway, prompt_registry
except ImportError:
    from services import model_gateway, prompt_registry


async def tool_turn(messages, tools, max_tokens=2500):
    return await model_gateway.complete(messages, settings(), tools=tools, max_tokens=max_tokens)


async def chat_json(messages, max_tokens=4000):
    response = await model_gateway.complete(messages, settings(), max_tokens=max_tokens)
    try:
        return json.loads(response['message']['content']), response['model']
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, 'AI服务返回内容无效，请重试') from None


async def generate(profile, baselines, schema):
    instruction = prompt_registry.text('plan.md')
    return await chat_json([
        {'role': 'system', 'content': instruction},
        {'role': 'user', 'content': json.dumps({'profile': profile,
            'valid_rm': baselines, 'output_schema': schema}, ensure_ascii=False)},
    ], max_tokens=8192)
