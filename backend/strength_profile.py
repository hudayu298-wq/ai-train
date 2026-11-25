"""Owner-scoped, user-reported regional strength anchors, never inferred RM facts.

Chest/back/legs are product intake groups, not a validated whole-body strength score.
Cross-exercise plan loads are model proposals and remain explicitly uncalibrated.
"""
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

VERSION = 'regional-strength-1'
REGIONS = {'chest': '胸部', 'back': '背部', 'legs': '腿部'}
OPTIONS = {
    'chest': ('bench', 'incline_barbell_bench', 'dumbbell_bench', 'incline_dumbbell_bench', 'chest_press_machine'),
    'back': ('barbell_row', 'dumbbell_row', 'seated_cable_row', 'lat_pulldown', 'chest_supported_row'),
    'legs': ('squat', 'low_bar_squat', 'front_squat', 'goblet_squat', 'leg_press', 'deadlift', 'romanian_deadlift', 'barbell_hip_thrust'),
}
# These are coarse proposal-source groups, not equations converting one lift into another.
PLAN_REGIONS = {eid: region for region, ids in OPTIONS.items() for eid in ids} | {
    'cable_fly': 'chest', 'barbell_overhead_press': 'chest', 'seated_dumbbell_press': 'chest',
    'dumbbell_lateral_raise': 'chest', 'triceps_pushdown': 'chest',
    'cable_face_pull': 'back', 'barbell_curl': 'back', 'dumbbell_curl': 'back', 'hammer_curl': 'back',
    'leg_extension': 'legs', 'leg_curl': 'legs', 'dumbbell_split_squat': 'legs', 'standing_calf_raise': 'legs',
}
MAX_AGE = json.loads((Path(__file__).parent / 'policies/training-v1.json').read_text(encoding='utf-8'))['rm_max_age_days']
FRACTIONS = {1: 1., 2: .95, 3: .93, 4: .90, 5: .87, 6: .85, 7: .83, 8: .80, 9: .77, 10: .75}


def today():
    return (datetime.now(timezone.utc) + timedelta(hours=8)).date()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def catalog_basis(entry):
    return digest({k: entry.get(k) for k in ('id', 'type', 'equipment', 'weight_basis')})


def requires_machine_id(entry):
    return entry['id'] in {'chest_press_machine', 'seated_cable_row', 'lat_pulldown', 'chest_supported_row', 'leg_press'} or any(
        w in entry.get('equipment', '') for w in ('器械', '绳索', '龙门架', '史密斯', '机'))


def unit_label(entry):
    if entry['id'] == 'goblet_squat':
        return '单个哑铃或壶铃重量'
    if '哑铃' in entry.get('equipment', ''):
        return '单只哑铃重量'
    if requires_machine_id(entry):
        return '该台器械显示重量，不跨器械比较'
    return '含杠铃杆的总重量'


class Anchor(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)
    region: Literal['chest', 'back', 'legs']
    exercise_id: str = Field(min_length=1, max_length=80)
    weight_kg: float = Field(gt=0, le=500, strict=True)
    reps: int = Field(ge=1, le=15, strict=True)
    rir: int = Field(ge=0, le=5, strict=True)
    measured_on: date
    equipment_id: str = Field(default='', max_length=80)
    pain: bool = Field(strict=True)
    confirmed: bool = Field(strict=True)

    @model_validator(mode='after')
    def actual_report(self):
        if self.exercise_id not in OPTIONS[self.region]:
            raise ValueError('请选择该部位支持的评估动作')
        if not self.confirmed:
            raise ValueError('请确认是本人实际完成的数据')
        if not 0 <= (today() - self.measured_on).days <= MAX_AGE:
            raise ValueError('请填写有效期内的实际表现')
        return self


class Intake(BaseModel):
    model_config = ConfigDict(extra='forbid')
    items: list[Anchor] = Field(min_length=3, max_length=3)
    base_revision: str | None = Field(default=None, max_length=64)

    @model_validator(mode='after')
    def three_regions(self):
        if {a.region for a in self.items} != set(REGIONS):
            raise ValueError('胸、背、腿各填写一项，不可重复')
        return self


def state(db, *, with_options=False):
    stored = db.read('strength_profile', 'current') or {}
    wanted = {eid for ids in OPTIONS.values() for eid in ids} if with_options else {a['exercise_id'] for a in stored.get('items', [])}
    catalog = {eid: entry for eid in wanted if (entry := db.catalog_read('exercises', eid))}
    options = {region: [{k: e.get(k) for k in ('id', 'name', 'equipment', 'weight_basis')} | {
        'unit_label': unit_label(e), 'requires_equipment_id': requires_machine_id(e)}
        for eid in ids if (e := catalog.get(eid)) and e.get('type') == 'weighted'] for region, ids in OPTIONS.items()} if with_options else {}
    by_region = {a['region']: a for a in stored.get('items', [])}
    missing, items = [], []
    for region, label in REGIONS.items():
        a = by_region.get(region)
        entry = catalog.get((a or {}).get('exercise_id'))
        reason = None
        if not a:
            reason = '尚未填写'
        elif not entry or entry.get('type') != 'weighted' or catalog_basis(entry) != a.get('catalog_basis'):
            reason = '动作或负重口径已变化，请重新核对'
        elif not 0 <= (today() - date.fromisoformat(a['measured_on'])).days <= MAX_AGE:
            reason = '表现日期已失效，请更新'
        elif a.get('pain'):
            reason = '这项表现有不适，请选择当前可无不适完成的替代动作'
        if reason:
            missing.append({'region': region, 'label': label, 'reason': reason})
        if a:
            # Exact observed capacity, no universal novice/intermediate norm or cross-machine score.
            items.append({**a, 'name': (entry or {}).get('name', a.get('name')), 'ready': reason is None,
                'summary': f"{label}：{a.get('name')} {a['weight_kg']:g}kg × {a['reps']}次，主观余力{a['rir']}次"})
    return {'version': VERSION, 'revision': digest(stored) if stored else None, 'ready': not missing,
        'items': items, 'missing': missing, 'options': options,
        'note': '胸、背、腿是力量画像的三个参考方向；不同动作、器械的公斤数不等价，不据此评定统一力量等级。'}


def require_ready(db):
    result = state(db)
    if not result['ready']:
        details = '；'.join(f"{m['label']}：{m['reason']}" for m in result['missing'])
        raise HTTPException(422, '请先在画像补齐胸、背、腿力量评估。' + details)
    return result


def reference(exercise_id, anchors, rms):
    if exercise_id in rms:
        return {'kind': 'confirmed_rm', 'label': '同动作有效RM参考', 'source_id': rms[exercise_id]['id'],
            'needs_calibration': False, 'version': VERSION}
    region = PLAN_REGIONS[exercise_id]
    anchor = next(a for a in anchors['items'] if a['region'] == region)
    direct = exercise_id == anchor['exercise_id']
    return {'kind': 'reported_performance' if direct else 'regional_estimate',
        'label': '同动作实际表现参考' if direct else f'{REGIONS[region]}力量参考估计',
        'region': region, 'source_exercise_id': anchor['exercise_id'], 'source_name': anchor['name'],
        'source_equipment_id': anchor['equipment_id'], 'source_unit': anchor['unit_label'],
        'strength_revision': anchors['revision'], 'needs_calibration': True, 'version': VERSION,
        'note': '起始重量建议，首训逐步热身核对；不代表实测RM，也不作为已完成训练。'}


def validate_load(exercise, anchors, rms):
    weight = exercise.get('weight_kg')
    if weight is None or not isinstance(weight, (float, int)) or not 0 < weight <= 500:
        raise ValueError('每个负重动作必须有具体的建议重量')
    rm = rms.get(exercise['exercise_id'])
    if rm:
        if exercise['reps'] not in FRACTIONS or weight > rm['reference_1rm_kg'] * FRACTIONS[exercise['reps']]:
            raise ValueError('重量超出同动作RM参考')
    else:
        a = next((a for a in anchors['items'] if a['exercise_id'] == exercise['exercise_id']), None)
        # A same-action first proposal cannot exceed the user's reported working load,
        # or ask for more reps at that same load. This is a product bound, not an RM conversion.
        if a and (weight > a['weight_kg'] or weight == a['weight_kg'] and exercise['reps'] > a['reps']):
            raise ValueError('首次同动作建议超过已报告表现，请重新生成更保守的目标')


def add_references(plan, anchors, rms):
    for days in [plan['days']] + [w['days'] for w in plan['cycle_schedule']]:
        for day in days:
            for exercise in day['exercises']:
                validate_load(exercise, anchors, rms)
                exercise['load_reference'] = reference(exercise['exercise_id'], anchors, rms)


def preserve_reference(exercise, previous):
    if previous.get('load_reference') and all(exercise.get(k) == previous.get(k) for k in ('weight_kg', 'reps')):
        exercise['load_reference'] = deepcopy(previous['load_reference'])
    elif exercise.get('weight_kg') is not None:
        exercise['load_reference'] = {'kind': 'user_selected', 'label': '用户确认的计划目标',
            'needs_calibration': True, 'version': VERSION}


def router(connection):
    api = APIRouter(prefix='/api/strength-profile', tags=['strength-profile'])

    @api.get('')
    def get_state():
        with connection() as db:
            return state(db, with_options=True)

    @api.put('')
    def save_intake(body: Intake):
        with connection() as db:
            db.lock_user()
            current = state(db)
            if body.base_revision != current['revision']:
                raise HTTPException(409, '力量画像已在其他窗口更新，请刷新后核对')
            items = []
            for a in body.items:
                entry = db.catalog_read('exercises', a.exercise_id)
                if not entry or entry.get('type') != 'weighted':
                    raise HTTPException(422, '评估动作不存在或已停用')
                if requires_machine_id(entry) and not a.equipment_id:
                    raise HTTPException(422, REGIONS[a.region] + '评估请注明所用器械编号或名称')
                items.append({**a.model_dump(mode='json'), 'name': entry['name'], 'unit_label': unit_label(entry),
                    'catalog_basis': catalog_basis(entry), 'source': 'user_reported_performance'})
            db.write('strength_profile', 'current', {'items': items, 'version': VERSION,
                'updated_at': datetime.now(timezone.utc).isoformat()})
            return state(db, with_options=True)

    return api
