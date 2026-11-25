"""Explicit plan organization. These are supported product formats, not efficacy rankings."""
from typing import Literal
from fastapi import HTTPException

SplitPreference = Literal['auto', 'full_body', 'upper_lower', 'push_pull_legs', 'bodypart_four', 'bodypart_five']
MethodPreference = Literal['auto', 'straight_sets', 'five_by_five', 'strength_hypertrophy']
Focus = Literal['full_body', 'upper', 'lower', 'push', 'pull', 'legs', 'chest', 'back', 'shoulders', 'shoulders_arms', 'arms']
SPLITS = {
    'full_body': ('全身训练', ('full_body',)),
    'upper_lower': ('二分化 · 上肢/下肢', ('upper', 'lower')),
    'push_pull_legs': ('三分化 · 推/拉/腿', ('push', 'pull', 'legs')),
    'bodypart_four': ('四分化 · 胸/背/肩臂/腿', ('chest', 'back', 'shoulders_arms', 'legs')),
    'bodypart_five': ('五分化 · 胸/背/肩/腿/手臂', ('chest', 'back', 'shoulders', 'legs', 'arms')),
}
METHODS = {'straight_sets': '常规固定组', 'five_by_five': '主项5×5', 'strength_hypertrophy': '力量与增肌混合'}
FAMILIES = {
    'chest': {'bench', 'incline_barbell_bench', 'dumbbell_bench', 'incline_dumbbell_bench', 'chest_press_machine', 'cable_fly'},
    'back': {'barbell_row', 'dumbbell_row', 'seated_cable_row', 'lat_pulldown', 'chest_supported_row'},
    'legs': {'squat', 'low_bar_squat', 'front_squat', 'goblet_squat', 'leg_press', 'deadlift', 'romanian_deadlift', 'barbell_hip_thrust', 'leg_extension', 'leg_curl', 'dumbbell_split_squat', 'standing_calf_raise'},
    'shoulders': {'barbell_overhead_press', 'seated_dumbbell_press', 'dumbbell_lateral_raise', 'cable_face_pull'},
    'biceps': {'barbell_curl', 'dumbbell_curl', 'hammer_curl'}, 'triceps': {'triceps_pushdown'},
}
FOCUS_FAMILIES = {'full_body': set(FAMILIES), 'upper': set(FAMILIES)-{'legs'}, 'lower': {'legs'},
    'legs': {'legs'}, 'push': {'chest','shoulders','triceps'}, 'pull': {'back','biceps'},
    'chest': {'chest','triceps'}, 'back': {'back','biceps'}, 'shoulders': {'shoulders'},
    'shoulders_arms': {'shoulders','biceps','triceps'}, 'arms': {'biceps','triceps'}}
DAY_FIELDS = ('focus', 'session_goal', 'training_method', 'primary_exercise_id')
VERSION = 'training-program-1'

def allowed_exercises(focus):
    allowed = set().union(*(FAMILIES[f] for f in FOCUS_FAMILIES[focus]))
    # Programming categories overlap: face pulls train rear delts/scapular pulling;
    # deadlifts may be programmed on a pull/back day or a lower-body day.
    if focus in ('pull', 'back'):
        allowed |= {'cable_face_pull', 'deadlift'}
    return allowed

def check_schedule(facts):
    split = facts.get('training_split') or 'auto'
    if split != 'auto' and facts['days'] < len(SPLITS[split][1]):
        raise HTTPException(422, f"{SPLITS[split][0]}在当前周模板中至少需要{len(SPLITS[split][1])}个训练日，请调整画像训练日或分化偏好")

def contract(facts=None, exercise_ids=None):
    facts = facts or {}
    available = set(exercise_ids) if exercise_ids is not None else set().union(*FAMILIES.values())
    preference = facts.get('training_split') or 'auto'
    splits = {k:v for k,v in SPLITS.items() if preference in ('auto', k)
        and len(v[1]) <= facts.get('days', 7) and all(allowed_exercises(focus) & available for focus in v[1])}
    focuses = {f for _, groups in splits.values() for f in groups}
    return {'version': VERSION, 'splits': {k:{'label':v[0], 'required_focuses':v[1]} for k,v in splits.items()},
        'methods': METHODS, 'focus_exercise_ids': {k:sorted(allowed_exercises(k) & available) for k in sorted(focuses)},
        'method_rules': '常规组按动作固定组次；主项5×5每天明确一个主项5组5次；力量增肌混合仅指定主项3–6次、其余所有辅助动作均8–15次，至少一个辅助动作。减量周保留训练法来源并降低组数，不强称仍完成5组。'}

def validate(plan, facts, *, recovery=False):
    split = plan.get('split_type')
    if split not in SPLITS or (facts.get('training_split', 'auto') not in (None, 'auto', split)):
        raise ValueError('实际分化与画像选择不一致')
    required = set(SPLITS[split][1])
    if {d.get('focus') for d in plan['days']} != required:
        raise ValueError('训练日未按分化覆盖全部分组')
    preferred = facts.get('training_method') or 'auto'
    for index, day in enumerate(plan['days']):
        location = f'第{index + 1}个训练日：'
        if any(not day.get(k) for k in DAY_FIELDS):
            raise ValueError(location + '必须填写部位、目标、训练法和主项')
        if day['training_method'] not in METHODS or preferred not in ('auto', day['training_method']):
            raise ValueError(location + '训练法与画像不一致')
        allowed = allowed_exercises(day['focus'])
        if any(e['exercise_id'] not in allowed for e in day['exercises']):
            raise ValueError(location + '动作与当天分组不一致')
        main = next((e for e in day['exercises'] if e['exercise_id'] == day['primary_exercise_id']), None)
        if not main:
            raise ValueError(location + '主项不在当天动作中')
        if day['training_method'] == 'five_by_five' and (main['reps'] != 5 or not (1 <= main['sets'] <= 5 if recovery else main['sets'] == 5)):
            raise ValueError(location + '主项5×5必须有5组5次的主项')
        if day['training_method'] == 'strength_hypertrophy' and (not 3 <= main['reps'] <= 6 or len(day['exercises']) < 2 or
                any(not 8 <= e['reps'] <= 15 for e in day['exercises'] if e is not main)):
            raise ValueError(location + '混合训练法只允许指定主项3–6次，其余辅助动作需8–15次')

def preserve_day(day, previous, fields_set):
    for key in DAY_FIELDS:
        if key not in fields_set and previous.get(key) is not None:
            day[key] = previous[key]
