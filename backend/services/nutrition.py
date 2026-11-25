"""Deterministic nutrition calculations and recording completeness."""
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

RULE_VERSION = 'nutrition-2026.10.22-v1'
SOURCES = [
    {'id': 'mifflin-1990', 'title': 'Mifflin et al. A new predictive equation for resting energy expenditure in healthy individuals',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/2305711/', 'published': '1990', 'kind': 'original_research',
     'scope': '498名健康成人，19–78岁；静息能量预测方程，不能测得个人实际消耗'},
    {'id': 'issn-protein-2017', 'title': 'ISSN Position Stand: protein and exercise',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/28642676/', 'published': '2017', 'kind': 'position_stand',
     'scope': '多数健康运动成人；蛋白质1.4–2.0 g/kg/日，不适用于个体疾病处方'},
    {'id': 'niddk-bwp-2017', 'title': 'NIDDK About the Body Weight Planner',
     'url': 'https://www.niddk.nih.gov/health-information/weight-management/body-weight-planner',
     'published': '2017-05', 'kind': 'official_guidance', 'scope': '成人工具；排除未成年人、孕期与哺乳期；本产品未实现其动态模型'},
    {'id': 'wearables-2017', 'title': 'Shcherbina et al. Accuracy in Wrist-Worn Sensor-Based Measurements of Heart Rate and Energy Expenditure',
     'url': 'https://pubmed.ncbi.nlm.nih.gov/28538708/', 'published': '2017', 'kind': 'original_research',
     'scope': '当时测试设备和实验条件的能耗误差研究；不能代表所有当前设备的精度'},
]


def rules():
    """Executable parameters distinguish evidence from explicit product policy."""
    population = '健康运动成人；孕哺期、需治疗性饮食或进食障碍请由专业人员评估'
    entries = [
        ('resting_energy', '静息能量估算', 'kcal/日', '10×kg + 6.25×cm − 5×岁 + (男性5 / 女性−161)',
         False, ['mifflin-1990'], '简化的Mifflin–St Jeor方程；不是基础代谢实测值'),
        ('activity_factor', '活动系数', '无量纲', 1.4, True, [], '1.2–2.2由用户选择；1.4为产品起点，不由训练天数或手表消耗推导'),
        ('energy_adjustment', '目标能量调整', 'kcal/日', {'fat_loss': -250, 'muscle_gain': 200}, True, [],
         '减脂允许−500至0，增肌允许0至400；属于可调整的产品起点'),
        ('protein', '蛋白质', 'g/kg/日', 1.6, True, ['issn-protein-2017'], '默认1.6；设置限1.4–2.0，来自运动成人共识范围，个人需求可不同'),
        ('fat', '脂肪', 'g/kg/日', 0.8, True, [], '允许0.6–1.2；这是产品分配策略，未宣称为临床阈值'),
        ('macro_energy', '宏量营养素能量换算', 'kcal/g', {'protein': 4, 'carbs': 4, 'fat': 9}, True, [],
         '产品采用常规4/4/9近似分配剩余碳水；不能替代食物库逐项热量'),
        ('calibration', '趋势校准', '日、次/周、kcal/日', {'window_days': 14, 'weight_days_per_week': 5,
          'step_kcal': 100, 'expires_hours': 48, 'cooldown_days': 14,
          'max_cumulative_adjustment_kcal': 300, 'adherence_tolerance_percent': 15,
          'fat_loss_weekly_percent': [-0.75, -0.25], 'muscle_gain_weekly_percent': [0.1, 0.25],
          'rapid_change_stop_percent': 1.0}, True, ['wearables-2017'],
         '这些数字均为保守产品策略；不以7700 kcal/kg反推代谢，不直接叠加设备热量；建议确认后生效'),
        ('energy_guardrail', '自动目标范围', 'kcal/日', {'female_min': 1200, 'male_min': 1500, 'max': 4500}, True, [],
         '产品自动计算边界，不是所有人的安全摄入下限；超出时停止并请专业评估'),
    ]
    return [{'id': key, 'label': label, 'unit': unit, 'value': value, 'product_default': default,
             'source_ids': sources, 'version': RULE_VERSION, 'population': population, 'limitations': note,
             'reviewed_on': '2026-10-22'} for key, label, unit, value, default, sources, note in entries]


def default_settings():
    return {'activity_factor': 1.4, 'protein_g_per_kg': 1.6, 'fat_g_per_kg': 0.8,
            'energy_adjustment_kcal': None, 'eligibility': 'not_confirmed',
            'calibration_enabled': False}


def settings(db):
    return {**default_settings(), **(db.read('nutrition_settings', 'settings') or {})}

NUTRIENTS = ('kcal', 'protein', 'fat', 'carbs')
MEAL_LABELS = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '加餐', 'unassigned': '未分类'}


def totals(items):
    return {k: float(sum((Decimal(str(item['nutrients'][k])) for item in items), Decimal(0)).quantize(
        Decimal('.1'), rounding=ROUND_HALF_UP)) for k in NUTRIENTS}


def macros(profile, config, kcal):
    protein = round(profile['weight_kg'] * config['protein_g_per_kg'])
    fat = round(profile['weight_kg'] * config['fat_g_per_kg'])
    return {'kcal': kcal, 'protein': protein, 'fat': fat, 'carbs': max(0, round((kcal - protein * 4 - fat * 9) / 4))}


def target_explanation(profile, config=None):
    config = {**default_settings(), **(config or {})}
    result = {'version': RULE_VERSION, 'status': 'missing', 'target': None, 'settings': config,
              'rules': rules(), 'sources': SOURCES, 'steps': [], 'warnings': [],
              'note': '这是营养计划起点和趋势建议，未经本产品临床验证；设备消耗不直接叠加。'}
    if not profile:
        result['warnings'].append('请先完善年龄、身高、体重、公式性别和训练目标')
        return result
    if config['eligibility'] == 'needs_professional_review' or profile['age'] < 18:
        result.update(status='needs_review', warnings=['当前人群不适合自动营养目标，请由专业人员评估'])
        return result
    weight, height, age = profile['weight_kg'], profile['height_cm'], profile['age']
    bmi = weight / (height / 100) ** 2
    resting = 10 * weight + 6.25 * height - 5 * age + (5 if profile['sex'] == 'male' else -161)
    adjustment = config['energy_adjustment_kcal']
    if adjustment is None:
        adjustment = -250 if profile['goal'] == 'fat_loss' else 200
    if (profile['goal'] == 'fat_loss' and not -500 <= adjustment <= 0 or
            profile['goal'] == 'muscle_gain' and not 0 <= adjustment <= 400):
        result.update(status='needs_review', warnings=['目标已变化，请重新保存匹配当前目标的能量调整'])
        return result
    kcal = round(resting * config['activity_factor'] + adjustment)
    result['inputs'] = {k: profile[k] for k in ('age', 'height_cm', 'weight_kg', 'sex', 'goal')}
    result['steps'] = [
        {'label': '静息能量估算', 'value': round(resting, 1), 'unit': 'kcal/日', 'rule_id': 'resting_energy'},
        {'label': '活动系数', 'value': config['activity_factor'], 'unit': '无量纲', 'rule_id': 'activity_factor'},
        {'label': '维持能量估算', 'value': round(resting * config['activity_factor']), 'unit': 'kcal/日', 'rule_id': 'activity_factor'},
        {'label': '目标调整', 'value': adjustment, 'unit': 'kcal/日', 'rule_id': 'energy_adjustment'},
    ]
    floor = 1500 if profile['sex'] == 'male' else 1200
    calculated = macros(profile, config, kcal)
    if kcal < floor or kcal > 4500 or calculated['protein'] * 4 + calculated['fat'] * 9 > kcal or (bmi < 18.5 and profile['goal'] == 'fat_loss'):
        result.update(status='needs_review', warnings=['计算超出自动营养范围，请调整设置或由专业人员评估；不会把结果截断后当作目标'])
        return result
    result.update(status='estimated', target=calculated)
    if not 19 <= age <= 78:
        result['warnings'].append('年龄超出原始方程研究的19–78岁范围，不能用于自动趋势校准')
    if config['eligibility'] != 'eligible':
        result['warnings'].append('尚未确认适用人群；请在设置中确认健康成人、非孕哺期且无需治疗性饮食')
    return result


def target(profile, config=None):
    return target_explanation(profile, config)['target']


def baseline_signature(profile, config):
    import hashlib
    import json
    fields = {key: profile.get(key) for key in ('age', 'height_cm', 'weight_kg', 'sex', 'goal')} if profile else None
    return hashlib.sha256(json.dumps([RULE_VERSION, fields, config], sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def effective_explanation(db, profile):
    config = settings(db)
    result = target_explanation(profile, config)
    active = db.read('nutrition_active_target', 'current')
    result['target_source'] = 'formula_estimate'
    if (result['target'] and active and config['calibration_enabled'] and config['eligibility'] == 'eligible'
            and (db.read('health_settings', 'settings') or {}).get('storage_enabled')
            and active['baseline_signature'] == baseline_signature(profile, config)):
        result.update(target=macros(profile, config, active['kcal']), target_source='confirmed_calibration',
                      calibration_id=active['suggestion_id'], confirmed_at=active['confirmed_at'])
        result['steps'].append({'label': '已确认的趋势调整', 'value': active['kcal'], 'unit': 'kcal/日', 'rule_id': 'calibration'})
    return result


def effective_target(db, profile):
    return effective_explanation(db, profile)['target']


def record_meal(db, payload, food, day):
    from . import privacy
    db.lock_user()
    if payload.get('day') and payload['day'] != day:
        raise HTTPException(422, '饮食仅支持记录当天，请刷新页面后重试')
    if not payload.get('portion_confirmed', True):
        raise HTTPException(422, '请先确认食物和实际份量')
    request_id = payload.get('request_id')
    key = 'meal-' + request_id if request_id else str(uuid4())
    privacy.require_not_deleted(db,'meal',key)
    existing = db.read('meal', key)
    if existing:
        if existing.get('input') != payload:
            raise HTTPException(409, '请求编号已用于其他饮食记录')
        return {'id': key, **existing}
    value = {**payload, 'input': payload, 'day': day, 'name': food['name'],
        'food_state': food['state'], 'food_source': food['source_label'],
        'nutrients': {k: float((Decimal(str(food[k])) * Decimal(str(payload['grams'])) / 100).quantize(
            Decimal('.1'), rounding=ROUND_HALF_UP)) for k in NUTRIENTS},
        'source': food.get('source_kind', 'user'), 'created_at': datetime.now(timezone.utc).isoformat()}
    db.write('meal', key, value)
    invalidate_diary(db, day)
    return {'id': key, **value}


def invalidate_diary(db, day):
    diary = db.read('nutrition_diary', day)
    if diary and diary['status'] == 'complete':
        db.write('nutrition_diary', day, {**diary, 'status': 'partial', 'changed_after_confirmation': True})


def summary(db, day, profile):
    items = [r for r in db.records('meal') if r['day'] == day]
    consumed = totals(items)
    explanation = effective_explanation(db, profile)
    goal = explanation['target']
    diary = db.read('nutrition_diary', day) or {'status': 'unknown', 'notes': ''}
    groups = [{'meal_type': key, 'label': label, 'items': entries, 'totals': totals(entries)}
        for key, label in MEAL_LABELS.items()
        if (entries := [r for r in items if r.get('meal_type', 'unassigned') == key]) or key != 'unassigned']
    comparison = {}
    for key in NUTRIENTS:
        needed = goal[key] if goal else None
        delta = round(consumed[key] - needed, 1) if needed is not None else None
        comparison[key] = {'consumed': consumed[key], 'target': needed,
            'remaining': max(0, -delta) if delta is not None else None,
            'excess': max(0, delta) if delta is not None else None,
            'percent': round(consumed[key] / needed * 100, 1) if needed else None}
    return {'day': day, 'timezone': 'Asia/Shanghai', 'records': items, 'groups': groups,
        'totals': consumed, 'target': goal, 'target_status': 'ready' if goal else explanation['status'],
        'target_basis': {key: explanation[key] for key in ('version', 'target_source', 'steps', 'warnings', 'note')},
        'comparison': comparison, 'diary': diary,
        'interpretation': '仅汇总已记录食物；记录不完整时不能据此判断全天热量不足。设备消耗不直接叠加到目标。'}
