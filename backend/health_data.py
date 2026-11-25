"""Source-aware observations and optional AI summaries; no device estimates become RM."""
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete, select

try:
    from . import database as d
    from .services import privacy
except ImportError:
    import database as d
    from services import privacy

TZ = timezone(timedelta(hours=8))
METRICS = {
    'weight_kg': ('kg', 20, 350), 'body_fat_percent': ('%', 1, 70),
    'waist_cm': ('cm', 30, 250), 'steps': ('count', 0, 150000),
    'sleep_hours': ('h', 0, 24), 'resting_hr_bpm': ('bpm', 25, 220),
    'hrv_rmssd_ms': ('ms', 1, 500), 'active_minutes': ('min', 0, 1440),
    'active_energy_kcal': ('kcal', 0, 20000),
}


def today():
    return datetime.now(TZ).date()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Observation(Strict):
    metric: Literal['weight_kg', 'body_fat_percent', 'waist_cm', 'steps', 'sleep_hours',
        'resting_hr_bpm', 'hrv_rmssd_ms', 'active_minutes', 'active_energy_kcal']
    value: float
    unit: str = Field(max_length=12)
    observed_at: datetime
    end_at: datetime | None = None
    source_updated_at: datetime | None = None
    provider: Literal['manual', 'health_connect', 'honor_health', 'huawei_health', 'withings', 'file_import'] = 'manual'
    external_id: str = Field(min_length=8, max_length=120, pattern=r'^[a-zA-Z0-9._:-]+$')
    device: str = Field(default='', max_length=100)
    source_app: str = Field(default='', max_length=100)
    method: Literal['self_report', 'scale', 'bia', 'wearable', 'tape', 'unknown'] = 'self_report'
    estimated: bool = False
    conditions: str = Field(default='', max_length=300)
    timezone: Literal['Asia/Shanghai'] = 'Asia/Shanghai'

    @model_validator(mode='after')
    def validate_observation(self):
        unit, low, high = METRICS[self.metric]
        if self.unit != unit or not low <= self.value <= high:
            raise ValueError('单位或数值范围不符合指标')
        times = [v for v in (self.observed_at, self.end_at, self.source_updated_at) if v]
        if any(t.tzinfo is None or t > datetime.now(timezone.utc) + timedelta(minutes=5) for t in times):
            raise ValueError('时间必须带时区且不能在未来')
        if self.end_at and self.end_at <= self.observed_at:
            raise ValueError('结束时间必须晚于开始时间')
        if self.metric in ('steps', 'sleep_hours', 'active_minutes', 'active_energy_kcal') and not self.end_at:
            raise ValueError('汇总指标必须提供时间区间')
        if self.end_at and self.end_at - self.observed_at > timedelta(days=1, minutes=1):
            raise ValueError('每条区间记录不能跨越超过一天')
        if self.metric == 'steps' and not self.value.is_integer():
            raise ValueError('步数必须为整数')
        if self.metric in ('body_fat_percent', 'active_energy_kcal') or self.method == 'bia':
            self.estimated = True
        return self


class ImportBatch(Strict):
    records: list[Observation] = Field(min_length=1, max_length=100)


class HealthSettings(Strict):
    storage_enabled: bool = False
    ai_context_enabled: bool = False


class Checkin(Strict):
    day: date = Field(default_factory=today)
    sleep_quality: Literal['good', 'normal', 'poor', 'unknown'] = 'unknown'
    energy: Literal['good', 'normal', 'poor', 'unknown'] = 'unknown'
    fatigue: int | None = Field(default=None, ge=0, le=10)
    discomfort_area: str = Field(default='', max_length=150)
    discomfort_trend: Literal['none', 'better', 'same', 'worse', 'unknown'] = 'unknown'
    temporary_constraints: str = Field(default='', max_length=500)
    notes: str = Field(default='', max_length=500)


def settings(db):
    return db.read('health_settings', 'settings') or HealthSettings().model_dump()


def rows(db, days=28):
    start = datetime.combine(today() - timedelta(days=days - 1), datetime.min.time(), TZ)
    records = db.conn.execute(select(d.measurements).where(d.measurements.c.user_id == d.owner(),
        d.measurements.c.observed_at >= start).order_by(d.measurements.c.observed_at.desc()).limit(2000)).mappings()
    return [{'id': r['id'], **r['payload']} for r in records]


def store(db, item):
    db.lock_user()
    if not settings(db)['storage_enabled']:
        raise HTTPException(403, '请先授权保存健康测量；用于AI摘要可单独选择')
    prior = db.conn.execute(select(d.measurements).where(d.measurements.c.user_id == d.owner(),
        d.measurements.c.provider == item.provider, d.measurements.c.external_id == item.external_id)).mappings().first()
    data = item.model_dump(mode='json')
    data['ingest_channel'] = 'manual' if item.provider == 'manual' else 'user_authorized_import'
    data['verification'] = 'user_supplied_not_vendor_verified'
    if prior:
        if prior['payload'] == data:
            return {'id': prior['id'], **data}
        if not item.source_updated_at or item.source_updated_at <= d.aware(prior['source_updated_at']):
            raise HTTPException(409, '记录已存在；更新需要较新的来源更新时间')
        if prior['metric'] != item.metric:
            raise HTTPException(409, '同一来源记录不能改变指标类型')
        privacy.invalidate(db,reason='health_source_corrected',domains={'health'})
        if item.metric == 'weight_kg':
            # A correction can invalidate the history used by a confirmed target.
            # New daily observations do not silently replace that target.
            db.remove('nutrition_active_target','current')
    key = prior['id'] if prior else str(uuid4())
    values = dict(id=key, user_id=d.owner(), metric=item.metric, provider=item.provider,
        external_id=item.external_id, observed_at=item.observed_at,
        source_updated_at=item.source_updated_at or item.observed_at, payload=data)
    stmt = d.dialect_insert(db.conn, d.measurements).values(**values)
    stmt = stmt.on_conflict_do_update(index_elements=['id'], set_={k: v for k, v in values.items() if k not in ('id', 'user_id')})
    db.conn.execute(stmt)
    return {'id': key, **data}


def summarize(db, *, for_ai=False):
    config = settings(db)
    if for_ai and not (config['storage_enabled'] and config['ai_context_enabled']):
        return {'enabled': False, 'note': '用户未授权健康测量进入AI上下文；不要推断设备数据'}
    observations = rows(db)
    result = {}
    for metric in METRICS:
        values = [v for v in observations if v['metric'] == metric]
        if not values:
            continue
        # A single comparable source per metric; overlapping devices are never added.
        latest = values[0]
        signature = tuple(latest.get(k) for k in ('provider', 'device', 'method', 'conditions', 'source_app'))
        comparable = [v for v in values if tuple(v.get(k) for k in ('provider', 'device', 'method', 'conditions', 'source_app')) == signature]
        daily = {}
        for value in comparable:
            stamp = datetime.fromisoformat(value.get('end_at') or value['observed_at']).astimezone(TZ).date()
            daily.setdefault(stamp.isoformat(), value)
        recent = [v['value'] for day, v in daily.items() if date.fromisoformat(day) >= today() - timedelta(days=6)]
        previous = [v['value'] for day, v in daily.items() if today() - timedelta(days=13) <= date.fromisoformat(day) <= today() - timedelta(days=7)]
        entry = {'latest': latest['value'], 'unit': latest['unit'], 'observed_at': latest['observed_at'],
            'provider': latest['provider'], 'device': latest['device'], 'estimated': latest['estimated'],
            'days_last_7': len(recent), 'mean_last_7': round(sum(recent) / len(recent), 2) if recent else None,
            'mean_previous_7': round(sum(previous) / len(previous), 2) if previous else None,
            'comparison_available': len(recent) >= 3 and len(previous) >= 3,
            'source_record_ids': [v['id'] for v in comparable[:14]],
            'quality': ['单一来源按日取最新记录，未合并重叠设备', '缺失不视为0']}
        if entry['comparison_available']:
            entry['change'] = round(entry['mean_last_7'] - entry['mean_previous_7'], 2)
        result[metric] = entry
    checkins = [r for r in db.records('wellness_checkin', limit=28) if r['day'] >= (today() - timedelta(days=27)).isoformat()]
    return {'enabled': config['storage_enabled'], 'metrics': result, 'recent_checkins': checkins[:7],
        'version': 'health-summary-1', 'note': '设备估算仅作辅助；不据单次体脂、HRV、睡眠或热量自动修改RM、计划或热量目标。'}


def revision(db):
    return hashlib.sha256(json.dumps({'settings': settings(db), 'summary': summarize(db, for_ai=True)},
        sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def router(connection):
    api = APIRouter(prefix='/api/health-data')

    @api.get('/settings')
    def get_settings():
        with connection() as db:
            return {**settings(db), 'connectors': [
                {'id': 'manual', 'status': 'available'}, {'id': 'file_import', 'status': 'available'},
                *[{'id': p, 'status': 'requires_native_or_vendor_integration'} for p in ('health_connect', 'honor_health', 'huawei_health', 'withings')]]}

    @api.put('/settings')
    def put_settings(body: HealthSettings):
        if body.ai_context_enabled and not body.storage_enabled:
            raise HTTPException(422, '启用AI摘要需要先授权保存测量')
        with connection() as db:
            db.lock_user()
            old=settings(db)
            if (old['storage_enabled'] and not body.storage_enabled) or (old['ai_context_enabled'] and not body.ai_context_enabled):
                privacy.invalidate(db,reason='health_consent_revoked',domains={'health'})
            db.write('health_settings', 'settings', body.model_dump())
            if not body.storage_enabled:
                db.remove('nutrition_active_target','current')
        return body

    @api.get('/measurements')
    def list_measurements(days: int = Query(default=28, ge=1, le=366)):
        with connection() as db:
            return {'items': rows(db, days), 'metrics': {k: {'unit': v[0], 'min': v[1], 'max': v[2]} for k, v in METRICS.items()}}

    @api.post('/measurements')
    def add_measurement(body: Observation):
        with connection() as db:
            return store(db, body)

    @api.post('/import')
    def import_measurements(body: ImportBatch):
        with connection() as db:
            return {'items': [store(db, item) for item in body.records], 'count': len(body.records)}

    @api.delete('/measurements/{key}')
    def remove_measurement(key: str):
        with connection() as db:
            db.lock_user()
            removed = db.conn.execute(delete(d.measurements).where(d.measurements.c.user_id == d.owner(), d.measurements.c.id == key)).rowcount
            if not removed:
                raise HTTPException(404, '测量记录不存在')
            privacy.invalidate(db,reason='health_source_deleted',domains={'health'})
            db.remove('nutrition_active_target','current')
        return {'deleted': True}

    @api.delete('/measurements')
    def clear_measurements():
        with connection() as db:
            db.lock_user()
            db.conn.execute(delete(d.measurements).where(d.measurements.c.user_id == d.owner()))
            privacy.invalidate(db,reason='health_sources_cleared',domains={'health'})
            db.remove('nutrition_active_target','current')
            for row in db.records('wellness_checkin'):
                db.remove('wellness_checkin', row['id'])
        return {'deleted': True}

    @api.put('/checkin')
    def save_checkin(body: Checkin):
        if body.day > today():
            raise HTTPException(422, '恢复反馈不能记录未来日期')
        with connection() as db:
            db.lock_user()
            if not settings(db)['storage_enabled']:
                raise HTTPException(403, '请先授权保存健康测量与恢复反馈')
            existing=db.read('wellness_checkin',body.day.isoformat())
            if existing is not None and existing!=body.model_dump(mode='json'):
                privacy.invalidate(db,reason='wellness_source_corrected',domains={'health'})
            db.write('wellness_checkin', body.day.isoformat(), body.model_dump(mode='json'))
        return body

    @api.get('/summary')
    def get_summary():
        with connection() as db:
            return summarize(db)
    return api
