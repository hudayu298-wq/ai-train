"""Owner-scoped manual mobility pilot; never a camera angle or diagnostic service."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import delete

try:
    from . import database as d
    from .services import privacy
except ImportError:
    import database as d
    from services import privacy

PROTOCOL_ID = 'wblt-knee-wall-cm'
PROTOCOL_VERSION = '1'
REPEAT_SPREAD_CM = 0.5  # Product repeat prompt, NOT a study-derived MDC/diagnostic threshold.
SOURCE = {'id': 'konor-2012', 'title': 'Konor et al. 2012;7(3):279–287',
    'url': 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3362988/',
    'locator': 'Methods—Procedures; Table 3; Discussion', 'accessed_on': '2026-10-22'}
PROTOCOL = {
    'id': PROTOCOL_ID, 'version': PROTOCOL_VERSION, 'title': '负重膝触墙 · 手动尺测',
    'joint': 'ankle', 'movement': 'dorsiflexion', 'mode': 'active', 'loading': 'weight_bearing',
    'unit': 'cm', 'source_method': 'manual_tape', 'trial_count': 3, 'practice_trials_per_side': 3,
    'steps': [
        '准备稳定墙面、防滑平地和厘米尺；建议赤足。疼痛或近期下肢损伤未评估时先停止自测。',
        '面向墙，测量侧脚在前，大脚趾朝墙；膝沿第二脚趾方向触墙，脚跟全程贴地。可用每手两指轻扶墙保持平衡。',
        '逐渐调整脚与墙的距离，找到保持脚跟贴地且膝仍能轻触墙的最远可控位置；不要强压或弹震。',
        '每侧先练习3次，再正式测3次。每次记录大脚趾尖到墙的水平距离，读到0.1cm；使用同一把尺与同一测量者。',
        '出现任何疼痛立即停止，不继续凑齐3次；可保存停止记录及疼痛位置。',
        '比较时保持侧别、鞋袜、扶墙方式、场地、尺、测量者与热身条件一致。当天训练前后的值分开比较。',
    ],
    'research_basis': {'source': SOURCE, 'population': '20名健康成人；排除近6个月下肢损伤或手术者',
        'design': '经过培训的测量者；每侧3次取均值；10分钟间隔复测，属单次内可靠性研究',
        'boundary': 'App中的无人监督自测、长期趋势与产品质控尚未获该研究验证；不将研究样本均值或MDC设为合格线。'},
    'product_rules': {'max_trial_spread_cm': REPEAT_SPREAD_CM,
        'meaning': '3次极差超过0.5cm时提示复测，暂不纳入个人趋势；这是练伴产品质控约定，未经临床验证。',
        'baseline': '同侧同条件首条可比较记录为个人参考；也可手动指定。跨日期才展示变化值。'},
    'capabilities': {'manual_distance': 'available', 'camera_angle': 'unavailable_not_calibrated',
        'diagnosis': 'unavailable', 'model_estimate_in_manual_series': False},
    'limitations': ['距离cm不统一换算为角度；不表示孤立距小腿关节活动度。',
        '不提供正常/异常、伤病诊断、肌肉短缩判断或自动加重建议；不以10cm作为人人合格线。'],
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False, str_strip_whitespace=True)


class Settings(Strict):
    storage_enabled: bool = False
    ai_context_enabled: bool = False

    @model_validator(mode='after')
    def validate_consent(self):
        if self.ai_context_enabled and not self.storage_enabled:
            raise ValueError('允许AI使用摘要前，请先开启活动度记录保存')
        return self


class Trial(Strict):
    distance_cm: float = Field(ge=0, le=30, strict=True)
    heel_down: bool
    knee_touched_wall: bool
    knee_tracks_second_toe: bool

    @model_validator(mode='after')
    def validate_precision(self):
        if abs(self.distance_cm*10-round(self.distance_cm*10))>1e-8:
            raise ValueError('请按厘米尺读数记录到0.1cm，不添加虚假精度')
        return self


class Conditions(Strict):
    footwear: Literal['barefoot', 'shoes'] = 'barefoot'
    support: Literal['two_fingers_each_hand', 'hands_on_wall', 'none'] = 'two_fingers_each_hand'
    surface: str = Field(min_length=1, max_length=100)
    warmup: Literal['before_training', 'after_warmup', 'after_training'] = 'before_training'
    ruler: str = Field(min_length=1, max_length=100)
    assessor: str = Field(min_length=1, max_length=100)
    notes: str = Field(default='', max_length=300)


class Measurement(Strict):
    request_id: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    protocol_id: Literal['wblt-knee-wall-cm'] = PROTOCOL_ID
    protocol_version: Literal['1'] = PROTOCOL_VERSION
    side: Literal['left', 'right']
    observed_at: datetime
    mode: Literal['active'] = 'active'
    loading: Literal['weight_bearing'] = 'weight_bearing'
    source_method: Literal['manual_tape'] = 'manual_tape'
    unit: Literal['cm'] = 'cm'
    conditions: Conditions
    practice_completed: bool
    trials: list[Trial] = Field(default_factory=list, max_length=3)
    pain_score: int = Field(ge=0, le=10, strict=True)
    pain_location: str = Field(default='', max_length=150)
    stopped_due_to_pain: bool = False

    @model_validator(mode='after')
    def validate_session(self):
        if self.observed_at.tzinfo is None or self.observed_at > datetime.now(timezone.utc)+timedelta(minutes=5):
            raise ValueError('测量时间必须带时区且不能在未来')
        if self.pain_score:
            if not self.stopped_due_to_pain or not self.pain_location:
                raise ValueError('疼痛时必须停止测量并记录位置')
        elif self.stopped_due_to_pain:
            raise ValueError('停止原因与疼痛评分不一致')
        if not self.stopped_due_to_pain and len(self.trials)!=3:
            raise ValueError('未因疼痛停止的测量需要3次正式记录')
        return self


class Baseline(Strict):
    record_id: str = Field(min_length=8, max_length=80)


def settings(db):
    return {**Settings().model_dump(), **(db.read('mobility_settings', 'settings') or {})}


def signature(record):
    # Free text notes are also compared: changed conditions must never silently mix.
    content = {k:record[k] for k in ('protocol_id','protocol_version','side','mode','loading','source_method','unit','conditions')}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def decorate(record):
    distances=[v['distance_cm'] for v in record['trials']]
    spread=round(max(distances)-min(distances),3) if distances else None
    reasons=[]
    if record['pain_score'] or record['stopped_due_to_pain']:
        reasons.append('疼痛停止；不进入趋势')
    if not record['practice_completed']:
        reasons.append('未完成每侧3次练习')
    if len(distances)!=3:
        reasons.append('不足3次正式记录')
    if any(not (v['heel_down'] and v['knee_touched_wall'] and v['knee_tracks_second_toe']) for v in record['trials']):
        reasons.append('脚跟、触墙或膝脚方向条件未满足')
    if spread is not None and spread>REPEAT_SPREAD_CM:
        reasons.append('3次差异较大，请复测；0.5cm为产品质控约定')
    return {**record, 'mean_cm': round(sum(distances)/len(distances),2) if distances else None,
        'spread_cm':spread, 'comparable':not reasons, 'quality_notes':reasons,
        'source': SOURCE, 'verification':'user_reported_manual_not_clinically_verified',
        'comparison_signature':signature(record)}


def rows(db):
    return sorted((decorate(v) for v in db.records('mobility_measurement')),
        key=lambda v:(datetime.fromisoformat(v['observed_at']),v['id']), reverse=True)


def summarize(db):
    records=rows(db)
    result={}
    for side in ('left','right'):
        side_records=[v for v in records if v['side']==side]
        observation={'latest_observation':side_records[0] if side_records else None,
            'excluded_count':sum(not v['comparable'] for v in side_records)}
        valid=[v for v in side_records if v['comparable']]
        if not valid:
            result[side]={**observation, 'comparison_available':False,'count':0, 'note':'暂无满足同条件比较要求的记录'}
            continue
        latest=valid[0]
        comparable=[v for v in valid if v['comparison_signature']==latest['comparison_signature']]
        selected=db.read('mobility_baseline',side)
        baseline=next((v for v in comparable if selected and v['id']==selected['record_id']),None)
        baseline_mode='selected' if baseline else 'first_comparable'
        baseline=baseline or comparable[-1]
        cross_date=datetime.fromisoformat(latest['observed_at']).astimezone(timezone(timedelta(hours=8))).date()!=datetime.fromisoformat(baseline['observed_at']).astimezone(timezone(timedelta(hours=8))).date()
        available=baseline['id']!=latest['id'] and cross_date
        result[side]={**observation, 'latest':latest, 'baseline':baseline, 'baseline_mode':baseline_mode,
            'count':len(comparable), 'comparison_available':available,
            'change_cm':round(latest['mean_cm']-baseline['mean_cm'],2) if available else None,
            'selected_baseline_incompatible':bool(selected and baseline_mode!='selected'),
            'points':[{'id':v['id'],'observed_at':v['observed_at'],'mean_cm':v['mean_cm']} for v in reversed(comparable)],
            'note':'个人同条件墙距变化；不表示达到正常或临床改善。' if available else '积累同条件不同日期记录后展示变化；同日重复不计为长期变化。'}
    return {'protocol_id':PROTOCOL_ID, 'protocol_version':PROTOCOL_VERSION, 'sides':result,
        'note':'手动距离与模型估计分开；本试点未开放摄像头测角或诊断。'}


def revision(db):
    return hashlib.sha256(json.dumps({'settings':settings(db),'summary':summarize_for_ai(db)},
        sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def summarize_for_ai(db):
    consent=settings(db)
    if not (consent['storage_enabled'] and consent['ai_context_enabled']):
        return {'enabled':False}
    summary=summarize(db)
    sides={}
    for side,value in summary['sides'].items():
        latest=value.get('latest_observation')
        valid=value.get('latest')
        sides[side]={'count':value['count'], 'comparison_available':value['comparison_available'],
            'change_cm':value.get('change_cm'), 'note':value['note'],
            'latest_observation':({k:latest[k] for k in ('observed_at','mean_cm','comparable','pain_score','stopped_due_to_pain','quality_notes')} if latest else None),
            'latest_comparable':({k:valid[k] for k in ('observed_at','mean_cm')} if valid else None)}
    return {'enabled':True,'protocol_id':PROTOCOL_ID,'protocol_version':PROTOCOL_VERSION,
        'source_method':'manual_tape','unit':'cm','sides':sides,
        'limitations':PROTOCOL['limitations'], 'interpretation':summary['note']}


def router(connection):
    api=APIRouter(prefix='/api/mobility')

    @api.get('/protocol')
    def get_protocol():
        return PROTOCOL

    @api.get('/settings')
    def get_settings():
        with connection() as db:
            return settings(db)

    @api.put('/settings')
    def put_settings(value:Settings):
        with connection() as db:
            db.lock_user()
            old=settings(db)
            if (old['storage_enabled'] and not value.storage_enabled) or (old['ai_context_enabled'] and not value.ai_context_enabled):
                privacy.invalidate(db,reason='mobility_consent_revoked',domains={'mobility'})
            db.write('mobility_settings','settings',value.model_dump())
            return settings(db)

    @api.get('/measurements')
    def measurements():
        with connection() as db:
            return {'items':rows(db)}

    @api.post('/measurements')
    def create(value:Measurement):
        with connection() as db:
            db.lock_user()
            if not settings(db)['storage_enabled']:
                raise HTTPException(403,'请先开启活动度记录保存')
            payload=value.model_dump(mode='json')
            existing=db.read('mobility_measurement',value.request_id)
            if existing is not None and existing!=payload:
                raise HTTPException(409,'同一请求已保存不同内容，请使用新的请求ID')
            if existing is None:
                db.write('mobility_measurement',value.request_id,payload)
            return decorate({'id':value.request_id,**payload})

    @api.get('/summary')
    def summary():
        with connection() as db:
            return summarize(db)

    @api.put('/baseline/{side}')
    def set_baseline(side:Literal['left','right'], value:Baseline):
        with connection() as db:
            if not settings(db)['storage_enabled']:
                raise HTTPException(403,'请先开启活动度记录保存')
            record=db.read('mobility_measurement',value.record_id)
            if record is None or record['side']!=side:
                raise HTTPException(404,'未找到该侧记录')
            record=decorate({'id':value.record_id,**record})
            if not record['comparable']:
                raise HTTPException(422,'该记录需复测，不能设为个人参考')
            db.write('mobility_baseline',side,{'record_id':value.record_id})
            return summarize(db)

    @api.delete('/measurements/{record_id}')
    def delete_one(record_id:str):
        with connection() as db:
            if not db.remove('mobility_measurement',record_id):
                raise HTTPException(404,'记录不存在')
            privacy.invalidate(db,reason='mobility_source_deleted',domains={'mobility'})
            for side in ('left','right'):
                selected=db.read('mobility_baseline',side)
                if selected and selected['record_id']==record_id:
                    db.remove('mobility_baseline',side)
            return {'deleted':True}

    @api.delete('/measurements')
    def delete_all():
        with connection() as db:
            db.lock_user()
            privacy.invalidate(db,reason='mobility_sources_cleared',domains={'mobility'})
            db.conn.execute(delete(d.records_table).where(d.records_table.c.user_id==d.owner(),
                d.records_table.c.kind.in_(['mobility_measurement','mobility_baseline'])))
            return {'deleted':True}
    return api
