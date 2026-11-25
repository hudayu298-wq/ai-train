"""Owner-scoped destructive-change barrier and derived AI retention policy.

Confirmed targets/actual records are independent facts. Source snapshots and AI
explanations are discarded conservatively; they cannot survive in checkpoints,
reviews, exports or a revoke/re-enable cycle. Everything commits with the source
change, and in-flight writers must prove the same monotonic privacy revision.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import hashlib
from uuid import uuid4

from fastapi import HTTPException

try:from .. import database as d
except ImportError:import database as d

LEGACY='legacy'
NOTICE='相关来源或授权已变化，此前AI说明已清除；已确认的目标和实际记录保留，请基于最新资料重新提问。'
EXPECTED=ContextVar('privacy_expected_revision',default=None)


def revision(db):
    return (db.read('privacy_meta','context_epoch') or {}).get('nonce',LEGACY)


def current(db,expected):
    return revision(db)==(expected or LEGACY)


def require(db,expected):
    if not current(db,expected):raise HTTPException(409,'来源数据或授权已变化，旧AI任务与草稿已失效，请重新操作')


def tombstone_key(kind,key):return 'deleted:'+hashlib.sha256((kind+'\0'+key).encode()).hexdigest()


def remember_deleted(db,kind,key):
    db.write('privacy_meta',tombstone_key(kind,key),{'kind':kind,'record_id':key,'deleted_at':d.now().isoformat()})


def require_not_deleted(db,kind,key):
    if db.read('privacy_meta',tombstone_key(kind,key)):
        raise HTTPException(409,'原记录已由用户删除；旧请求不能恢复该记录，请使用新的请求编号')


def check_guard(db):
    expected=EXPECTED.get()
    if expected is not None:require(db,expected)


@contextmanager
def guard(expected):
    token=EXPECTED.set(expected or LEGACY)
    try:yield
    finally:EXPECTED.reset(token)


def invalid_run(value):
    keep=('input','versions','created_at','coach_name','routing','release','profile_revision',
        'privacy_revision','usage_events','decision_attempted')
    clean={k:deepcopy(value[k]) for k in keep if k in value}
    clean.update(status='invalidated_privacy',reply=NOTICE,error=NOTICE,context={},messages=[],steps=[],
        citations=[],profile_changes=[],privacy_invalidated=True)
    return clean


def target_days(days,*,invalidated=True):
    """Keep confirmed scheduling/load identities; discard generated prose."""
    output=[]
    for day in days or []:
        value={k:deepcopy(day[k]) for k in ('name','weekday','start_time','duration_minutes','focus',
            'training_method','primary_exercise_id','execution_groups') if k in day}
        if 'session_goal' in day:
            value['session_goal']=('保留已确认训练目标；相关AI说明已清除，请复核。' if invalidated else '按已确认的负重、组次与余力目标完成训练。')
        value['exercises']=[]
        for exercise in day.get('exercises',[]):
            item={k:deepcopy(exercise[k]) for k in ('exercise_id','name','weight_kg','sets','reps','rest_seconds',
                'target_rir','weight_basis','load_basis','equipment_id','load_reference') if k in exercise}
            value['exercises'].append(item)
        output.append(value)
    return output


def plan_targets(plan,*,invalidated=True):
    if not isinstance(plan,dict):return plan
    keep=('id','name','source','version','base_plan_id','generation_id','cycle_id','cycle_week','cycle_weeks',
        'week_attempt','cycle_schedule_origin','cycle_policy_version','cycle_started_on','week_started_on',
        'cycle_reviewed_on','cycle_complete','effective_until','split_type','training_program_version',
        'created_at','created_on','previous_cycle_id')
    value={k:deepcopy(plan[k]) for k in keep if k in plan}
    value['days']=target_days(plan.get('days',[]),invalidated=invalidated)
    if 'cycle_baseline_days' in plan:value['cycle_baseline_days']=target_days(plan['cycle_baseline_days'],invalidated=invalidated)
    if 'cycle_schedule' in plan:
        value['cycle_schedule']=[{**{k:deepcopy(week[k]) for k in ('week','phase') if k in week},
            'purpose':'既有确认目标；相关AI说明已清除，请复核。' if invalidated else '按已确认周目标执行。',
            'days':target_days(week.get('days',[]),invalidated=invalidated)}
            for week in plan['cycle_schedule']]
    if invalidated:value.update(privacy_invalidated=True,privacy_note=NOTICE)
    return value


def change_targets(change):
    if not isinstance(change,dict):return change
    keys=('id','status','workout_id','from_plan_id','to_plan_id','undone_by','model','created_at','reverted_at',
        'knowledge_release_id','foundation_revision','prompt_version','policy_version')
    value={k:deepcopy(change[k]) for k in keys if k in change}
    value['changes']=[{**{k:deepcopy(row[k]) for k in ('exercise_id','name','before','after') if k in row},
        'reason':'相关AI说明已清除。'} for row in change.get('changes',[])]
    value.update(summary=NOTICE,privacy_invalidated=True)
    return value


def invalidate(db,*,reason,domains):
    """Call inside the locked source mutation transaction; rollback is atomic."""
    db.lock_user()
    stamp=d.now().isoformat()
    db.write('privacy_meta','context_epoch',{'nonce':uuid4().hex,'reason':reason,'updated_at':stamp})
    db.invalidate_private_cache()
    for row in db.records('agent_run'):
        value=invalid_run(row);value.pop('id',None)
        db.write('agent_run',row['id'],value)
    for row in db.records('coach_turn'):
        value={k:deepcopy(v) for k,v in row.items() if k not in ('id','reply','actions','citations','profile_changes','error')}
        value.update(reply=NOTICE,status='invalidated_privacy',actions=[],citations=[],profile_changes=[],privacy_invalidated=True)
        db.write('coach_turn',row['id'],value)
    for row in db.records('agent_action'):
        value={k:deepcopy(row[k]) for k in ('kind','run_id','expires_at','created_at','status','result') if k in row}
        value.update(payload={},preview={'title':'旧AI操作说明已清除','lines':[NOTICE]},privacy_invalidated=True)
        if isinstance(value.get('result'),dict):
            value['result']={k:value['result'][k] for k in ('record_id','saved','followup') if k in value['result']}
        if value.get('status') not in ('committed','cancelled'):value['status']='expired_privacy_changed'
        db.write('agent_action',row['id'],value)
    for row in db.records('agent_followup'):
        value={k:deepcopy(row[k]) for k in ('workout_id','coach_id','session_id','created_at','attempts') if k in row}
        value.update(status='cancelled_privacy_changed',privacy_revision=revision(db))
        db.write('agent_followup',row['id'],value)
    for row in db.records('plan_draft'):
        db.write('plan_draft',row['id'],{'privacy_invalidated':True,'status':'expired_privacy_changed'})
    for row in db.records('workout'):
        value={k:deepcopy(v) for k,v in row.items() if k!='id'}
        value['ai_review']=None
        if value.get('plan_snapshot'):value['plan_snapshot']=plan_targets(value['plan_snapshot'])
        if value.get('plan_progression'):value['plan_progression']=change_targets(value['plan_progression'])
        db.write('workout',row['id'],value)
    for row in db.records('plan'):db.write('plan',row['id'],plan_targets(row))
    for row in db.records('workout_execution'):
        value={k:deepcopy(v) for k,v in row.items() if k!='id'}
        if value.get('plan_snapshot'):value['plan_snapshot']=plan_targets(value['plan_snapshot'])
        db.write('workout_execution',row['id'],value)
    for row in db.records('plan_change'):db.write('plan_change',row['id'],change_targets(row))
    if set(domains)&{'health','nutrition'}:
        for row in db.records('nutrition_suggestion'):
            db.write('nutrition_suggestion',row['id'],{'privacy_invalidated':True,'status':'expired_privacy_changed'})
        db.remove('nutrition_active_target','current')
