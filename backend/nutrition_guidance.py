"""Owner-scoped, deterministic nutrition guidance; calibration requires explicit confirmation."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

try:
    from . import health_data
    from .services import nutrition,privacy
except ImportError:
    import health_data
    from services import nutrition,privacy

TZ = timezone(timedelta(hours=8))


def now():
    return datetime.now(timezone.utc)


def today():
    return now().astimezone(TZ).date()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Settings(Strict):
    activity_factor: float = Field(default=1.4, ge=1.2, le=2.2)
    protein_g_per_kg: float = Field(default=1.6, ge=1.4, le=2.0)
    fat_g_per_kg: float = Field(default=0.8, ge=0.6, le=1.2)
    energy_adjustment_kcal: int | None = Field(default=None, ge=-500, le=400)
    eligibility: Literal['not_confirmed', 'eligible', 'needs_professional_review'] = 'not_confirmed'
    calibration_enabled: bool = False


class Request(Strict):
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')


def profile(db):
    entries = db.records('profile')
    return entries[0] if entries else None


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def calibration(db):
    """Evaluate past ended days only; never interprets absent meals as zero intake."""
    user = profile(db)
    config = nutrition.settings(db)
    basis = nutrition.effective_explanation(db, user)
    end = today() - timedelta(days=1)
    start = end - timedelta(days=13)
    result = {'eligible': False, 'status': 'insufficient_data', 'reasons': [], 'version': nutrition.RULE_VERSION,
              'window': {'start': start.isoformat(), 'end': end.isoformat(), 'days': 14},
              'policy': {'kind': 'product_policy', 'weight_days_per_week': 5, 'complete_diet_days': 14,
                         'step_kcal': 100, 'cooldown_days': 14, 'max_cumulative_adjustment_kcal': 300,
                         'adherence_tolerance_percent': 15,
                         'goal_weekly_percent': {'fat_loss': [-0.75, -0.25], 'muscle_gain': [0.1, 0.25]}},
              'device_energy_added_kcal': 0,
              'note': '以下窗口与阈值是产品策略，未经临床验证；短期水分变化、疾病和漏记都可能影响判断。'}
    if not config['calibration_enabled'] or not (db.read('health_settings', 'settings') or {}).get('storage_enabled'):
        result.update(status='consent_required', reasons=['请授权保存健康测量，并单独授权营养趋势校准使用体重与完整饮食记录'])
        return result
    if not user or not basis['target']:
        result['reasons'].append('需要有效的个人资料和营养目标')
        return result
    bmi = user['weight_kg'] / (user['height_cm'] / 100) ** 2
    if config['eligibility'] != 'eligible' or not 19 <= user['age'] <= 78 or not 18.5 <= bmi <= 40:
        result.update(status='needs_review', reasons=['自动校准限已确认适用的19–78岁健康运动成人，BMI 18.5–40；其他情况请专业评估'])
        return result
    active = db.read('nutrition_active_target', 'current')
    if active and active['baseline_signature'] == nutrition.baseline_signature(user, config):
        since = (today() - datetime.fromisoformat(active['confirmed_at']).astimezone(TZ).date()).days
        if since < 14:
            result.update(status='cooldown', reasons=['上次调整后需至少积累14个完整日再评估'], days_remaining=14 - since)
            return result

    dates = [(start + timedelta(days=i)).isoformat() for i in range(14)]
    diaries = {day: db.read('nutrition_diary', day) for day in dates}
    meals = [r for r in db.records('meal') if r.get('day') in dates]
    day_intake = {}
    complete = 0
    portions_ok = True
    for day in dates:
        items = [r for r in meals if r['day'] == day]
        if diaries[day] and diaries[day].get('status') == 'complete' and items:
            complete += 1
            day_intake[day] = nutrition.totals(items)['kcal']
        if any(not r.get('portion_confirmed', True) or r.get('portion_source') not in ('weighed', 'label') for r in items):
            portions_ok = False
    result['complete_diet_days'] = complete
    if complete != 14:
        result['reasons'].append(f'需要连续14个已结束且确认完整、有食物记录的饮食日，当前{complete}天')
    if not portions_ok:
        result['reasons'].append('窗口内食物份量需称重或按标签确认；估算份量不足以支持自动校准')

    # Select one comparable source; never merge device/source/conditions or sum energy.
    weight_rows = [r for r in health_data.rows(db, days=16) if r.get('metric') == 'weight_kg'
                   and r.get('unit') == 'kg' and not r.get('estimated')
                   and r.get('method') in ('scale', 'self_report')
                   and start <= datetime.fromisoformat(r['observed_at']).astimezone(TZ).date() <= end]
    groups = {}
    for row in weight_rows:
        signature = tuple(row.get(k, '') for k in ('provider', 'device', 'method', 'conditions', 'source_app'))
        stamp = datetime.fromisoformat(row['observed_at']).astimezone(TZ).date().isoformat()
        groups.setdefault(signature, {}).setdefault(stamp, []).append(row)
    source, daily = max(groups.items(), key=lambda item: (len(item[1]), str(item[0]))) if groups else (None, {})
    values = {day: median([r['value'] for r in rows]) for day, rows in daily.items()}
    first = [values[day] for day in dates[:7] if day in values]
    second = [values[day] for day in dates[7:] if day in values]
    result['weight_days'] = {'first_week': len(first), 'second_week': len(second)}
    result['weight_source'] = dict(zip(('provider', 'device', 'method', 'conditions', 'source_app'), source)) if source else None
    if len(first) < 5 or len(second) < 5:
        result['reasons'].append('同一来源和测量条件的体重每周至少5天，重复称重按日中位数计一次')
    if result['reasons']:
        return result
    intake = mean(day_intake.values())
    result['mean_intake_kcal'] = round(intake)
    current = basis['target']['kcal']
    if abs(intake - current) / current > 0.15:
        result.update(status='adherence_review', reasons=['完整记录的平均摄入与当前目标相差超过15%，请先核对份量和执行情况'])
        return result
    weekly_percent = (mean(second) - mean(first)) / mean(first) * 100
    result['weight_trend'] = {'first_week_mean_kg': round(mean(first), 2),
                              'second_week_mean_kg': round(mean(second), 2),
                              'weekly_change_percent': round(weekly_percent, 3)}
    if abs(weekly_percent) > 1.0:
        result.update(status='needs_review', reasons=['体重周变化超过1%，可能受水分或健康因素影响，请先核对并寻求专业评估'])
        return result
    low, high = result['policy']['goal_weekly_percent'][user['goal']]
    # Gain below range -> increase; loss above range -> decrease.
    delta = 100 if weekly_percent < low else -100 if weekly_percent > high else 0
    if delta == 0:
        result.update(status='maintain', reasons=['当前趋势处于产品观察区间，继续记录即可'])
        return result
    proposed = current + delta
    baseline = nutrition.target(user, config)['kcal']
    candidate = nutrition.macros(user, config, proposed)
    floor = 1500 if user['sex'] == 'male' else 1200
    if proposed < floor or proposed > 4500 or abs(proposed - baseline) > 300 or candidate['protein'] * 4 + candidate['fat'] * 9 > proposed:
        result.update(status='needs_review', reasons=['建议超出产品自动调整范围，请由专业人员评估'])
        return result
    result.update(eligible=True, status='ready', current_target=basis['target'], proposed_target=candidate,
                  change_kcal=delta, reasons=['基于同源体重周均值与完整饮食记录的小步建议；确认后才改变目标'])
    result['data_signature'] = fingerprint({'window': result['window'], 'diaries': diaries, 'meals': meals,
        'weights': sorted([r for rows in daily.values() for r in rows], key=lambda r: r['id']),
        'baseline': nutrition.baseline_signature(user, config), 'current_target': current})
    return result


def create_suggestion(db, body):
    db.lock_user()
    key = 'nutrition-' + body.request_id
    existing = db.read('nutrition_suggestion', key)
    if existing:
        if existing.get('privacy_invalidated'):raise HTTPException(409,'来源数据或授权已变化，请用新的请求重新评估')
        return {'id': key, **existing}
    assessment = calibration(db)
    if not assessment['eligible']:
        raise HTTPException(422, assessment)
    stamp = now()
    value = {'status': 'pending', 'request_id': body.request_id, 'created_at': stamp.isoformat(),
             'expires_at': (stamp + timedelta(hours=48)).isoformat(),
             'baseline_signature': nutrition.baseline_signature(profile(db), nutrition.settings(db)),
             'assessment': assessment}
    db.write('nutrition_suggestion', key, value)
    return {'id': key, **value}


def confirm_suggestion(db, key, body):
    db.lock_user()
    draft = db.read('nutrition_suggestion', key)
    if not draft:
        raise HTTPException(404, '建议不存在')
    if draft.get('privacy_invalidated'):raise HTTPException(409,'来源数据或授权已变化，旧建议已清除，请重新评估')
    if draft['status'] == 'applied':
        if draft.get('confirmation_request_id') != body.request_id:
            raise HTTPException(409, '建议已确认，请刷新当前目标')
        return {'id': key, **draft}
    if datetime.fromisoformat(draft['expires_at']) <= now():
        raise HTTPException(409, '建议已过期，请重新评估')
    current = calibration(db)
    if not current['eligible'] or current.get('data_signature') != draft['assessment']['data_signature']:
        raise HTTPException(409, '资料、授权、目标或依据数据已变化，请重新评估')
    stamp = now().isoformat()
    draft.update(status='applied', confirmed_at=stamp, confirmation_request_id=body.request_id)
    db.write('nutrition_active_target', 'current', {'suggestion_id': key, 'confirmed_at': stamp,
        'kcal': current['proposed_target']['kcal'], 'baseline_signature': draft['baseline_signature']})
    db.write('nutrition_suggestion', key, draft)
    return {'id': key, **draft}


def router(connection):
    api = APIRouter(prefix='/api/nutrition-guidance', tags=['nutrition-guidance'])

    @api.get('/rules')
    def get_rules():
        return {'version': nutrition.RULE_VERSION, 'items': nutrition.rules(), 'sources': nutrition.SOURCES}

    @api.get('/settings')
    def get_settings():
        with connection() as db:
            return nutrition.settings(db)

    @api.put('/settings')
    def put_settings(body: Settings):
        with connection() as db:
            db.lock_user()
            value = body.model_dump()
            if body.calibration_enabled and body.eligibility != 'eligible':
                raise HTTPException(422, '趋势校准需要先确认适用人群')
            user = profile(db)
            explanation = nutrition.target_explanation(user, value)
            if user and explanation['status'] == 'needs_review' and body.eligibility != 'needs_professional_review':
                raise HTTPException(422, explanation['warnings'])
            old=nutrition.settings(db)
            if old.get('calibration_enabled') and not body.calibration_enabled:
                privacy.invalidate(db,reason='nutrition_calibration_consent_revoked',domains={'nutrition'})
            if value != old:
                db.remove('nutrition_active_target', 'current')
            db.write('nutrition_settings', 'settings', value)
            return value

    @api.get('/target')
    def get_target():
        with connection() as db:
            return nutrition.effective_explanation(db, profile(db))

    @api.get('/calibration')
    def get_calibration():
        with connection() as db:
            return calibration(db)

    @api.get('/suggestions')
    def get_suggestions():
        with connection() as db:
            return {'items': [row for row in db.records('nutrition_suggestion', limit=20) if not row.get('privacy_invalidated')]}

    @api.post('/suggestions')
    def post_suggestion(body: Request):
        with connection() as db:
            return create_suggestion(db, body)

    @api.post('/suggestions/{key}/confirm')
    def post_confirm(key: str, body: Request):
        with connection() as db:
            return confirm_suggestion(db, key, body)

    return api
