"""Conversational coach with evidence-backed profile updates and durable turns."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

try:
    from . import ai_planner, coaches, workouts
except ImportError:
    import ai_planner
    import coaches
    import workouts

PROMPT = (Path(__file__).parent / 'prompts' / 'fitness_coach.md').read_text(encoding='utf-8')
PROMPT_VERSION = 'coach-2.2'
LABELS = {
    'age': '年龄', 'height_cm': '身高 / cm', 'weight_kg': '体重 / kg',
    'sex': '代谢估算性别', 'goal': '训练目标', 'experience': '训练经验',
    'days': '每周训练天数', 'restrictions': '伤病或训练限制',
    'dietary_preferences': '饮食偏好', 'equipment': '可用器械',
    'training_preferences': '训练偏好', 'schedule': '时间安排',
    'training_weekdays': '每周训练日', 'session_minutes': '单次训练时长',
    'preferred_time': '训练时间', 'training_months': '训练月数',
    'sleep_hours': '平均睡眠时长', 'recovery_status': '恢复情况',
    'goal_detail': '具体目标', 'injury_status': '伤病状态',
    'movement_constraints': '不适动作与可训练范围', 'load_increment_kg': '可用最小加重幅度',
}
CORE = {'age', 'height_cm', 'weight_kg', 'sex', 'goal', 'experience', 'days', 'restrictions'}
REQUIRED = CORE - {'restrictions'}


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    age: int | None = Field(default=None, ge=18, le=90, strict=True)
    height_cm: float | None = Field(default=None, ge=120, le=230, strict=True)
    weight_kg: float | None = Field(default=None, ge=35, le=250, strict=True)
    sex: Literal['male', 'female'] | None = None
    goal: Literal['fat_loss', 'muscle_gain'] | None = None
    experience: Literal['beginner', 'intermediate'] | None = None
    days: int | None = Field(default=None, ge=1, le=7, strict=True)
    restrictions: str | None = Field(default=None, max_length=1000)
    dietary_preferences: str | None = Field(default=None, max_length=1000)
    equipment: str | None = Field(default=None, max_length=1000)
    training_preferences: str | None = Field(default=None, max_length=1000)
    schedule: str | None = Field(default=None, max_length=1000)
    training_weekdays: list[int] | None = Field(default=None, min_length=1, max_length=7)
    session_minutes: int | None = Field(default=None, ge=15, le=180, strict=True)
    preferred_time: str | None = Field(default=None, pattern=r'^(?:[01]\d|2[0-3]):[0-5]\d$')
    training_months: int | None = Field(default=None, ge=0, le=600, strict=True)
    sleep_hours: float | None = Field(default=None, ge=0, le=14)
    recovery_status: Literal['good', 'normal', 'poor'] | None = None
    goal_detail: str | None = Field(default=None, max_length=1000)
    injury_status: Literal['none', 'historical', 'current'] | None = None
    movement_constraints: str | None = Field(default=None, max_length=1000)
    load_increment_kg: float | None = Field(default=None, gt=0, le=20)

    @field_validator('training_weekdays')
    @classmethod
    def weekdays(cls, value):
        if value is not None and (any(type(d) is not int or not 1 <= d <= 7 for d in value) or len(set(value)) != len(value)):
            raise ValueError('训练日必须是互不重复的1至7')
        return sorted(value) if value is not None else None


class MessageRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    message: str = Field(min_length=1, max_length=4000)
    coach_id: coaches.CoachId | None = None
    coach_name: str | None = Field(default=None, min_length=1, max_length=16, pattern=r'.*\S.*')


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    field: str
    value: Any
    evidence: str = Field(min_length=1, max_length=1000)


class CoachOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reply: str = Field(min_length=1, max_length=6000, pattern=r'.*\S.*')
    profile_updates: list[ProfileUpdate] = Field(max_length=12)


def read(db, kind, key):
    return db.read(kind, key)


def write(db, kind, key, payload):
    db.write(kind, key, payload)


def state(db):
    stored = read(db, 'coach_profile', 'local-coach-profile') or {}
    full = read(db, 'profile', 'local-profile') or {}
    facts = {**stored.get('facts', {}), **{k: v for k, v in full.items() if k in CORE}}
    missing = sorted(REQUIRED - facts.keys())
    return {'facts': facts, 'missing_fields': missing, 'labels': LABELS,
            'complete': not missing, 'updated_at': stored.get('updated_at'),
            'strength_records': db.records('rm'),
            'training_memory': workouts.memory(db)}


def turns(db, limit=40):
    return [{k: v for k, v in row.items() if k != 'id'}
            for row in reversed(db.records('coach_turn', limit=limit))]


def fingerprint(db):
    data = {'state': state(db), 'turns': turns(db),
            'persona_settings': read(db, 'coach_reminders', 'local-coach-reminders')}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def apply_profile(db, changes, profile_model, source):
    current = state(db)['facts']
    merged = {**current, **changes}
    if 'training_weekdays' in changes:
        merged['days'] = len(changes['training_weekdays'])
    elif 'days' in changes and len(merged.get('training_weekdays', [])) != changes['days']:
        merged.pop('training_weekdays', None)
    now = datetime.now(timezone.utc).isoformat()
    write(db, 'coach_profile', 'local-coach-profile',
          {'facts': merged, 'updated_at': now, 'last_source': source})
    # Keep incomplete facts without inventing defaults. Existing plan/diet APIs
    # receive a complete compatible profile once every required fact is known.
    if REQUIRED.issubset(merged):
        full = profile_model.model_validate({k: v for k, v in merged.items() if k in CORE})
        write(db, 'profile', 'local-profile', full.model_dump())
    return state(db)


def validate_updates(output, message):
    changes, evidence = {}, []
    for update in output.profile_updates:
        if update.field not in LABELS or update.field in changes:
            raise ValueError('invalid or repeated field')
        if update.evidence not in message or not update.evidence.strip() or update.value is None:
            raise ValueError('missing current-message evidence')
        validated = ProfilePatch.model_validate({update.field: update.value})
        if update.field in ('age', 'height_cm', 'weight_kg', 'days', 'session_minutes', 'training_months', 'sleep_hours', 'load_increment_kg'):
            numbers = [float(n) for n in re.findall(r'\d+(?:\.\d+)?', update.evidence)]
            candidates = list(numbers)
            if update.field == 'height_cm' and '米' in update.evidence:
                candidates.extend(n * 100 for n in numbers)
            if update.field == 'weight_kg' and '斤' in update.evidence:
                candidates.extend(n / 2 for n in numbers)
            if numbers and not any(abs(n - update.value) < .001 for n in candidates):
                raise ValueError('numeric value does not match evidence')
        changes[update.field] = validated.model_dump(exclude_unset=True)[update.field]
        evidence.append({'field': update.field, 'label': LABELS[update.field],
                         'value': changes[update.field], 'evidence': update.evidence})
    return changes, evidence


async def respond(message, history, profile, context):
    schema = CoachOutput.model_json_schema()
    schema['$defs']['ProfileUpdate']['properties']['field']['enum'] = list(LABELS)
    messages = [
        {'role': 'system', 'content': coaches.prompt(context['coach_persona'].get('id', 'steady'), PROMPT)},
        {'role': 'system', 'content': json.dumps({
            'known_profile': profile, 'fitness_context': context,
            'profile_field_schema': ProfilePatch.model_json_schema(),
            'output_schema': schema,
        }, ensure_ascii=False)},
    ]
    for turn in history[-12:]:
        messages.extend([{'role': 'user', 'content': turn['user_message']},
                         {'role': 'assistant', 'content':
                          f"[历史教练：{turn.get('coach_name', '先前教练')}]\n{turn['reply']}"}])
    messages.append({'role': 'user', 'content': message})
    return await ai_planner.chat_json(messages, max_tokens=2600)


def router(connection, profile_model, context_provider):
    api = APIRouter(prefix='/api/coach')

    @api.get('/status')
    def status():
        return {**ai_planner.status(), 'prompt_version': PROMPT_VERSION}

    @api.get('/prompt')
    def prompt(coach_id: coaches.CoachId | None = None):
        with connection() as db:
            saved = read(db, 'coach_reminders', 'local-coach-reminders') or {}
        selected = coach_id or saved.get('coach_id', 'steady')
        return {'prompt': coaches.prompt(selected, PROMPT), 'version': PROMPT_VERSION,
                'coach': coaches.require(selected), 'common_prompt': PROMPT,
                'personality_prompt': coaches.PERSONALITY_PROMPTS[selected]}

    @api.get('/personas')
    def personas():
        return {'items': coaches.PERSONAS, 'version': PROMPT_VERSION}

    @api.get('/profile')
    def profile():
        with connection() as db:
            return state(db)

    @api.patch('/profile')
    def edit_profile(patch: ProfilePatch):
        changes = patch.model_dump(exclude_unset=True, exclude_none=True)
        with connection() as db:
            db.lock_user()
            return apply_profile(db, changes, profile_model, 'manual')

    @api.get('/messages')
    def messages():
        with connection() as db:
            return {'turns': turns(db), 'profile': state(db)}

    @api.post('/messages')
    async def send(request: MessageRequest):
        key = 'coach-turn-' + request.request_id
        with connection() as db:
            cached = read(db, 'coach_turn', key)
            if cached:
                if cached['user_message'] != request.message or (
                    request.coach_id and cached.get('coach_id', 'steady') != request.coach_id):
                    raise HTTPException(409, '请求编号已用于其他消息')
                return {**cached, 'profile': state(db)}
            profile = state(db)
            history = turns(db)
            revision = fingerprint(db)
        context = context_provider(request.message)
        coach_id = request.coach_id or context.get('coach_persona', {}).get('id', 'steady')
        persona = coaches.require(coach_id)
        existing = context.get('coach_persona', {})
        coach_name = request.coach_name or (existing.get('coach_name') if existing.get('id') == coach_id else None) or persona['name']
        context['coach_persona'] = {**persona, 'coach_name': coach_name, 'virtual_character': True}
        raw, model = await respond(request.message, history, profile['facts'], context)
        try:
            output = CoachOutput.model_validate(raw)
            changes, evidence = validate_updates(output, request.message)
        except (ValidationError, ValueError, TypeError):
            raise HTTPException(502, 'AI回复或画像提取不符合要求，尚未记录，请重试') from None
        with connection() as db:
            db.lock_user()
            cached = read(db, 'coach_turn', key)
            if cached:
                if cached['user_message'] != request.message or (
                    request.coach_id and cached.get('coach_id', 'steady') != request.coach_id):
                    raise HTTPException(409, '请求编号已用于其他消息')
                return {**cached, 'profile': state(db)}
            if fingerprint(db) != revision:
                raise HTTPException(409, '对话或画像已在其他页面更新，请重试这条消息')
            if changes:
                apply_profile(db, changes, profile_model, key)
            result = {'request_id': request.request_id, 'user_message': request.message,
                      'reply': output.reply, 'profile_changes': evidence, 'model': model,
                      'coach_id': coach_id, 'coach_name': coach_name,
                      'prompt_version': PROMPT_VERSION, 'created_at': datetime.now(timezone.utc).isoformat()}
            write(db, 'coach_turn', key, result)
            return {**result, 'profile': state(db)}

    return api
