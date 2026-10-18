"""Versioned, independent coach personalities layered over common rules."""
import json
from pathlib import Path
from typing import Literal
from fastapi import HTTPException

ROOT = Path(__file__).parent
CoachId = Literal['steady', 'energetic', 'analytical', 'gentle']
PERSONAS = json.loads((ROOT / 'data' / 'coach_personas.json').read_text(encoding='utf-8'))
BY_ID = {p['id']: p for p in PERSONAS}
PERSONALITY_PROMPTS = {key: (ROOT / 'prompts' / 'coaches' / f'{key}.md').read_text(encoding='utf-8')
                       for key in BY_ID}


def require(coach_id):
    if coach_id not in BY_ID:
        raise HTTPException(422, '请选择现有的四位教练之一')
    return BY_ID[coach_id]


def prompt(coach_id, common):
    require(coach_id)
    return common + '\n\n当前教练的独立性格提示词：\n' + PERSONALITY_PROMPTS[coach_id]
