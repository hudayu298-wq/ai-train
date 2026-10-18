"""Persistent food/exercise catalog, including custom entries and atomic JSON import."""
import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
try:
    from . import exercise_content
except ImportError:
    import exercise_content

class FoodEntry(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    id: str | None = Field(default=None, pattern=r'^[a-z0-9_]+$', max_length=80)
    name: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    category: str = Field(min_length=1, max_length=40)
    state: Literal['raw', 'cooked', 'prepared'] = 'prepared'
    aliases: list[str] = Field(default_factory=list, max_length=15)
    kcal: float = Field(ge=0, le=900)
    protein: float = Field(ge=0, le=100)
    fat: float = Field(ge=0, le=100)
    carbs: float = Field(ge=0, le=100)
    source_label: str = Field(min_length=1, max_length=500)
    notes: str = Field(default='', max_length=1500)

    @model_validator(mode='after')
    def mass(self):
        if self.protein + self.fat + self.carbs > 105:
            raise ValueError('每100克的三大营养素总量异常，请核对单位')
        return self

class ExerciseEntry(BaseModel):
    id: str | None = Field(default=None, pattern=r'^[a-z0-9_]+$', max_length=80)
    name: str = Field(min_length=1, max_length=100, pattern=r'.*\S.*')
    category: str = Field(min_length=1, max_length=40)
    type: Literal['weighted', 'bodyweight'] = 'weighted'
    equipment: str = Field(min_length=1, max_length=80)
    difficulty: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    aliases: list[str] = Field(default_factory=list, max_length=15)
    summary: str = Field(default='', max_length=1500)
    weight_basis: str = Field(default='含器械总重量；同一器械和变式单独记录', max_length=300)
    view: str = Field(default='尚未支持实时检测，可记录训练。', max_length=500)
    source_label: str = Field(default='用户维护的动作条目，未审核', max_length=500)
    movement_pattern: str | None = Field(default=None, max_length=80)
    joint_actions: list[str] | None = Field(default=None, max_length=15)
    primary_muscles: list[str] | None = Field(default=None, max_length=15)
    secondary_muscles: list[str] | None = Field(default=None, max_length=15)
    body_regions: list[str] | None = Field(default=None, max_length=15)
    technique: exercise_content.Technique | None = None

KINDS = {'foods': FoodEntry, 'exercises': ExerciseEntry}

def initialize(connection):
    with connection() as db:
        for kind in KINDS:
            entries = json.loads((Path(__file__).parent / 'data' / f'{kind}.json').read_text(encoding='utf-8'))
            for order, entry in enumerate(entries):
                KINDS[kind].model_validate(entry)
                db.catalog_write(kind, entry, ignore=True, order=order)

def all_entries(connection, kind):
    with connection() as db:
        entries = db.catalog_read(kind)
    return [exercise_content.enrich(e) for e in entries] if kind == 'exercises' else entries

def find_entry(connection, kind, entry_id):
    with connection() as db:
        entry = db.catalog_read(kind, entry_id)
    if not entry:
        return None
    return exercise_content.enrich(entry) if kind == 'exercises' else entry

def custom_payload(kind, entry, entry_id=None):
    payload = entry.model_dump(exclude={'id'}, exclude_none=True)
    payload.update(id=entry_id or entry.id or f'{kind}_{uuid4().hex}', source_kind='user',
        review_status='user_supplied')
    if kind == 'foods':
        payload.update(basis_g=100)
    else:
        payload.update(realtime_supported=False, rm_supported=entry.type == 'weighted')
        payload = exercise_content.enrich(payload)
    return payload

def router(connection):
    routes = APIRouter(prefix='/api/library', tags=['library'])

    @routes.get('/{kind}')
    def search(kind: Literal['foods', 'exercises'], q: str = Query(default='', max_length=100),
               category: str = '', type: str = '', body_part: str = '', limit: int = Query(default=50, ge=1, le=200),
               offset: int = Query(default=0, ge=0)):
        entries = all_entries(connection, kind)
        categories = sorted({e['movement_pattern'] if kind == 'exercises' else e['category'] for e in entries})
        body_parts = sorted({part for e in entries for part in e.get('body_regions', [])})
        term = q.strip().casefold()
        result = [e for e in entries if (not category or e['category'] == category or e.get('movement_pattern') == category)
                  and (not body_part or body_part in e.get('body_regions', []))
                  and (not type or e.get('type') == type)
                  and (not term or term in json.dumps([e['name'], e.get('aliases', []),
                       e.get('original_name', ''), e.get('equipment', ''), e.get('joint_actions', []),
                       e.get('primary_muscles', []), e.get('movement_pattern', '')], ensure_ascii=False).casefold())]
        return {'items': result[offset:offset + limit], 'total': len(result),
                'limit': limit, 'offset': offset, 'categories': categories, 'body_parts': body_parts,
                'category_dimension': 'joint_movement' if kind == 'exercises' else 'food_type'}

    @routes.get('/exercises/{entry_id}/analysis-context')
    def context(entry_id: str):
        entry = find_entry(connection, 'exercises', entry_id)
        if not entry:
            raise HTTPException(404, '动作不存在或已停用')
        return exercise_content.analysis_context(entry)

    @routes.get('/{kind}/export')
    def export(kind: Literal['foods', 'exercises']):
        return {'schema_version': 1, 'kind': kind, 'items': all_entries(connection, kind)}

    @routes.post('/{kind}/import')
    def import_items(kind: Literal['foods', 'exercises'], items: list[dict]):
        if not 1 <= len(items) <= 500:
            raise HTTPException(422, '一次导入1–500条JSON记录')
        try:
            payloads = [custom_payload(kind, KINDS[kind].model_validate(e)) for e in items]
        except ValueError:
            raise HTTPException(422, '导入失败，请核对字段、营养单位和数据范围') from None
        if len({p['id'] for p in payloads}) != len(payloads):
            raise HTTPException(409, '导入ID重复')
        with connection() as db:
            for p in payloads:
                if db.catalog_read(kind, p['id'], active=False):
                    raise HTTPException(409, 'ID已存在，导入未执行；修改已有条目请使用编辑功能')
            for p in payloads:
                db.catalog_write(kind, p)
        return {'imported': len(payloads)}

    @routes.post('/foods')
    def add_food(entry: FoodEntry):
        return insert('foods', entry)

    @routes.post('/exercises')
    def add_exercise(entry: ExerciseEntry):
        return insert('exercises', entry)

    def insert(kind, entry):
        payload = custom_payload(kind, entry)
        with connection() as db:
            if db.catalog_read(kind, payload['id'], active=False):
                raise HTTPException(409, '条目ID已存在')
            db.catalog_write(kind, payload)
        return payload

    @routes.get('/{kind}/{entry_id}')
    def detail(kind: Literal['foods', 'exercises'], entry_id: str):
        entry = find_entry(connection, kind, entry_id)
        if not entry:
            raise HTTPException(404, '条目不存在或已停用')
        return entry

    def update(kind, entry_id, entry):
        existing = find_entry(connection, kind, entry_id)
        if not existing:
            raise HTTPException(404, '条目不存在或已停用')
        if kind == 'exercises' and existing.get('realtime_supported') and (entry.name != existing['name'] or entry.view != existing['view'] or entry.category != existing['category']):
            raise HTTPException(422, '实时检测动作的身份和拍摄定义固定；可编辑教学文案，其他变式请新建')
        if entry.id and entry.id != entry_id:
            raise HTTPException(422, '不能修改条目ID')
        if kind == 'exercises' and existing['type'] != entry.type:
            raise HTTPException(422, '不能改变已有动作的训练类型，请新建变式')
        if kind == 'exercises' and (existing['equipment'] != entry.equipment or existing['weight_basis'] != entry.weight_basis):
            raise HTTPException(422, '器械或重量口径变化会影响已有RM，请新建动作变式')
        payload = custom_payload(kind, entry, entry_id)
        if kind == 'exercises':
            # Catalog editing must never change the live detector's built-in movement definition.
            payload['realtime_supported'] = existing.get('realtime_supported', False)
            payload['content_version'] = 'user-draft-1'
        with connection() as db:
            db.catalog_update(kind, entry_id, name=payload['name'], category=payload['category'], payload=payload)
        return payload

    @routes.put('/foods/{entry_id}')
    def edit_food(entry_id: str, entry: FoodEntry):
        return update('foods', entry_id, entry)

    @routes.put('/exercises/{entry_id}')
    def edit_exercise(entry_id: str, entry: ExerciseEntry):
        return update('exercises', entry_id, entry)

    @routes.delete('/{kind}/{entry_id}')
    def archive(kind: Literal['foods', 'exercises'], entry_id: str):
        with connection() as db:
            changed = db.catalog_update(kind, entry_id, active=False)
            if not changed:
                raise HTTPException(404, '条目不存在或已停用')
        return {'archived': True}

    return routes
