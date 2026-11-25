"""Destructive source changes must not resurrect through derived AI artifacts."""
import copy
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone

import pytest
from fastapi import HTTPException
from test_app import module,client,PROFILE,isolate_records,workout_payload
from test_agent_health import final_message
from test_agent_health import tool_message
from services import privacy
from sqlalchemy import select,func

MARKER='PRIVATE_DELETED_SOURCE_SENTINEL'


def measurement():
    assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':True}).status_code==200
    value={'metric':'weight_kg','value':71,'unit':'kg','observed_at':datetime.now(timezone.utc).isoformat(),
        'provider':'manual','external_id':'privacy-observation','device':MARKER}
    response=client.post('/api/health-data/measurements',json=value)
    assert response.status_code==200,response.text
    return response.json()['id']


def test_deleted_health_source_cannot_return_in_history_run_or_export(monkeypatch):
    key=measurement()
    async def fake(*args,**kwargs):return final_message(MARKER)
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'privacy-old-reply','message':'请结合我的记录给出建议'}).json()
    assert result['status']=='completed'
    assert client.delete('/api/health-data/measurements/'+key).status_code==200
    for path in ('/api/coach/messages','/api/agent/runs/'+result['run_id'],'/api/me/export'):
        response=client.get(path)
        assert response.status_code==200
        assert MARKER not in response.text,(path,'deleted measurement leaked through derived content')


def test_review_cannot_commit_after_health_consent_changes_while_waiting(monkeypatch):
    measurement()
    saved=client.post('/api/workouts',json=workout_payload()).json()
    async def fake(messages,**kwargs):
        assert MARKER in json.dumps(messages)
        assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':False}).status_code==200
        return {'summary':MARKER,'strengths':['已记录训练'],'next_steps':['仅作建议']},'test-review'
    monkeypatch.setattr(module.ai_planner,'chat_json',fake)
    response=client.post('/api/workouts/'+saved['id']+'/review',json={'coach_id':'steady'})
    assert response.status_code==409,response.text
    assert client.get('/api/workouts').json()['items'][0]['ai_review'] is None


def test_reenable_cannot_restore_old_derived_answers(monkeypatch):
    measurement();sent=[]
    async def fake(messages,tools,**kwargs):
        sent.append(copy.deepcopy(messages))
        return final_message(MARKER if len(sent)==1 else '仅依据最新资料。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    first=client.post('/api/agent/runs',json={'request_id':'revoke-old-answer','message':'请结合我的记录给出建议'}).json()
    assert first['status']=='completed'
    assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':False}).status_code==200
    assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':True}).status_code==200
    # The original measurement remains stored because revocation is not deletion.
    assert len(client.get('/api/health-data/measurements').json()['items'])==1
    # Delete the actual source too: new prompts must not get its value via history.
    client.delete('/api/health-data/measurements')
    second=client.post('/api/agent/runs',json={'request_id':'revoke-new-answer','message':'请结合我的记录给出建议'}).json()
    assert second['status']=='completed'
    assert MARKER not in json.dumps(sent[-1])
    assert client.post('/api/agent/runs/'+first['run_id']+'/resume').status_code==409


def test_inflight_agent_cannot_rewrite_deleted_snapshot_in_failure_handler(monkeypatch):
    key=measurement()
    async def fake(messages,tools,**kwargs):
        assert MARKER in json.dumps(messages)
        assert client.delete('/api/health-data/measurements/'+key).status_code==200
        return final_message(MARKER)
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    response=client.post('/api/agent/runs',json={'request_id':'inflight-deletion','message':'请结合我的记录给出建议'})
    assert response.status_code==200,response.text
    assert response.json()['status']=='invalidated_privacy'
    assert MARKER not in response.text
    with module.connection() as db:
        run=db.read('agent_run',response.json()['run_id'])
        assert run['context']=={} and run['messages']==[] and run['steps']==[]
    assert MARKER not in client.get('/api/me/export').text


def test_correction_clears_completed_review_and_suggestion_without_changing_targets():
    key=measurement()
    with module.connection() as db:
        db.write('plan','confirmed-plan',{'name':'已确认计划','source':'user','version':1,
            'days':[{'name':'周一','exercises':[{'exercise_id':'bench','weight_kg':40,'sets':3,'reps':8,'rest_seconds':120}]}],
            'rationale':MARKER,'effective_profile':{'health_context':MARKER}})
        db.write('plan_draft','old-draft',{'rationale':MARKER})
        db.write('nutrition_suggestion','old-suggestion',{'assessment':{'source_snapshot':MARKER}})
    saved=client.post('/api/workouts',json=workout_payload()).json()
    with module.connection() as db:
        value=db.read('workout',saved['id']);value['ai_review']={'summary':MARKER}
        value['plan_snapshot']=db.read('plan','confirmed-plan')
        db.write('workout',saved['id'],value)
    original=client.get('/api/health-data/measurements').json()['items'][0]
    payload={k:v for k,v in original.items() if k in module.health_data.Observation.model_fields}
    payload.update(value=72,device='corrected-device',source_updated_at=datetime.now(timezone.utc).isoformat())
    assert client.post('/api/health-data/measurements',json=payload).status_code==200
    assert MARKER not in client.get('/api/me/export').text
    with module.connection() as db:
        plan=db.read('plan','confirmed-plan')
        assert plan['days'][0]['exercises'][0]['weight_kg']==40
        assert plan['days'][0]['exercises'][0]['sets']==3
        assert db.read('workout',saved['id'])['ai_review'] is None
        assert db.read('plan_draft','old-draft')['privacy_invalidated']
        assert db.read('nutrition_suggestion','old-suggestion')=={'privacy_invalidated':True,'status':'expired_privacy_changed'}


def test_privacy_invalidation_rolls_back_with_source_transaction():
    measurement()
    with module.connection() as db:
        before=privacy.revision(db)
        db.write('coach_turn','old',{'reply':MARKER,'user_message':'原问题'})
    with pytest.raises(RuntimeError):
        with module.connection() as db:
            privacy.invalidate(db,reason='synthetic_rollback',domains={'health'})
            raise RuntimeError('rollback')
    with module.connection() as db:
        assert privacy.revision(db)==before and db.read('coach_turn','old')['reply']==MARKER


def test_context_views_exclude_legacy_ai_snapshots_and_internal_export_metadata():
    from services import context
    plan={'name':'已确认计划','effective_profile':{'restrictions':MARKER},'rationale':MARKER,
        'days':[{'name':'力量日','session_goal':MARKER,'exercises':[{'exercise_id':'bench','sets':3,'reps':8,'weight_kg':40}]}]}
    view=context.compact({'current_plan':[plan],'training_memory':{'recent_sessions':[{'id':'one','ai_review':{'summary':MARKER}}]}})
    assert MARKER not in json.dumps(view)
    assert '已清除' not in json.dumps(view,ensure_ascii=False)
    assert view['current_plan'][0]['days'][0]['exercises'][0]['weight_kg']==40
    with module.connection() as db:
        privacy.remember_deleted(db,'meal','synthetic-export-id')
    response=client.get('/api/me/export')
    assert response.status_code==200
    assert 'privacy_meta' not in response.text and 'synthetic-export-id' not in response.text


def test_privacy_cleanup_preserves_progression_undo_identity():
    with module.connection() as db:
        db.write('plan_change','undo-event',{'status':'applied','undone_by':'confirmed-restored-plan',
            'from_plan_id':'before','to_plan_id':'after','summary':MARKER,'changes':[]})
        privacy.invalidate(db,reason='synthetic-source-change',domains={'health'})
    with module.connection() as db:
        event=db.read('plan_change','undo-event')
        assert event['undone_by']=='confirmed-restored-plan'
        assert event['from_plan_id']=='before' and event['to_plan_id']=='after'
        assert MARKER not in json.dumps(event)


def test_legacy_chat_checks_source_revision_before_sending_model_context(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    key=measurement()
    def changing_context(message):
        context=module.coach_context(message)
        assert client.delete('/api/health-data/measurements/'+key).status_code==200
        return context
    async def forbidden(*args):raise AssertionError('revoked context must not reach the model')
    monkeypatch.setattr(module.coach,'respond',forbidden)
    legacy=FastAPI();legacy.include_router(module.coach.router(module.connection,module.Profile,changing_context))
    response=TestClient(legacy).post('/api/coach/messages',json={'message':'请结合我的记录给出建议','request_id':'legacy-preflight-delete'})
    assert response.status_code==409,response.text


def test_progression_cannot_publish_after_source_delete_during_model_call(monkeypatch):
    from test_app import _progress_plan,_plan_workout
    key=measurement();plan=_progress_plan()
    _plan_workout(plan,'privacy-progression-prior',day=module.nutrition_today()-module.timedelta(days=7))
    workout=_plan_workout(plan,'privacy-progression-current')
    async def fake(*args,**kwargs):
        assert client.delete('/api/health-data/measurements/'+key).status_code==200
        return {'summary':MARKER,'changes':[]},'test'
    monkeypatch.setattr(module.ai_planner,'chat_json',fake)
    response=client.post('/api/workouts/'+workout['id']+'/progression')
    assert response.status_code==409,response.text
    assert MARKER not in client.get('/api/me/export').text
    with module.connection() as db:assert not db.records('plan_change')


def test_source_delete_does_not_invalidate_another_owner():
    key=measurement()
    with module.connection() as db:
        other=module.auth.new_user(db.conn,email='privacy-untouched@example.test')
    token=module.database.owner_context.set(other['id'])
    try:
        with module.connection() as db:
            before=privacy.revision(db)
            db.write('coach_turn','other-turn',{'reply':'独立用户内容'})
    finally:module.database.owner_context.reset(token)
    assert client.delete('/api/health-data/measurements/'+key).status_code==200
    token=module.database.owner_context.set(other['id'])
    try:
        with module.connection() as db:
            assert privacy.revision(db)==before
            assert db.read('coach_turn','other-turn')['reply']=='独立用户内容'
    finally:module.database.owner_context.reset(token)


def test_workout_delete_removes_legacy_mirrors_and_blocks_old_replay():
    payload=workout_payload();saved=client.post('/api/workouts',json=payload).json()
    assert client.get('/api/coach/profile').json()['training_memory']['session_count']==1
    assert client.delete('/api/workouts/'+saved['id']).status_code==200
    assert client.get('/api/workouts').json()['items']==[]
    assert client.get('/api/coach/profile').json()['training_memory']['session_count']==0
    with module.connection() as db:assert not db.records('training')
    assert client.post('/api/workouts',json=payload).status_code==409
    assert client.post('/api/workouts',json={**payload,'request_id':'explicit-new-workout'}).status_code==200


def test_deleted_meal_cannot_be_restored_by_automatic_old_request():
    payload={'food_id':'rice','grams':150,'meal_type':'lunch','portion_source':'weighed','request_id':'privacy-meal-source'}
    saved=client.post('/api/meals',json=payload).json()
    assert client.delete('/api/meals/'+saved['id']).status_code==200
    assert client.post('/api/meals',json=payload).status_code==409
    assert client.get('/api/meals').json()==[]


def test_account_tombstone_clears_measurements_and_other_owner_is_preserved():
    measurement();owner=module.database.owner()
    with module.connection() as db:
        other=module.auth.new_user(db.conn,email='privacy-other@example.test')
    token=module.database.owner_context.set(other['id'])
    try:
        with module.connection() as db:
            db.write('profile','other-profile',{'age':30})
    finally:module.database.owner_context.reset(token)
    assert client.delete('/api/me').status_code==200
    with module.connection() as db:
        assert db.conn.execute(select(func.count()).select_from(module.database.measurements).where(module.database.measurements.c.user_id==owner)).scalar()==0
        assert db.conn.execute(select(func.count()).select_from(module.database.records_table).where(module.database.records_table.c.user_id==owner)).scalar()==0
    token=module.database.owner_context.set(other['id'])
    try:
        with module.connection() as db:assert db.read('profile','other-profile')=={'age':30}
    finally:module.database.owner_context.reset(token)


def test_pending_action_race_cannot_recreate_payload_after_privacy_change(monkeypatch):
    key=measurement();count=0
    async def fake(*args,**kwargs):
        nonlocal count
        count+=1
        return tool_message('propose_meal',{'food_id':'rice','grams':150,'meal_type':'lunch','portion_source':'weighed'}) if count==1 else final_message()
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    run=client.post('/api/agent/runs',json={'request_id':'privacy-action-race','message':'今天午餐150克米饭，称重的'}).json()
    action=run['actions'][0]['id'];original=module.agent_service.handlers['save_meal']
    def racing_save(body):
        with ThreadPoolExecutor(max_workers=1) as pool:
            response=pool.submit(lambda:client.delete('/api/health-data/measurements/'+key)).result()
        assert response.status_code==200
        return original(body)
    monkeypatch.setitem(module.agent_service.handlers,'save_meal',racing_save)
    result=client.post('/api/agent/actions/'+action+'/decision',json={'approved':True})
    assert result.status_code==409,result.text
    assert client.get('/api/meals').json()==[]
    with module.connection() as db:
        saved=db.read('agent_action',action)
        assert saved['status']=='expired_privacy_changed' and saved['payload']=={}


def test_background_result_cannot_requeue_or_publish_after_deletion(monkeypatch):
    from scripts import agent_worker as worker
    key=measurement()
    owner=module.database.owner()
    with module.connection() as db:
        sid=db.conn.execute(select(module.database.sessions.c.id).where(module.database.sessions.c.user_id==owner)).scalar_one()
        db.write('agent_followup','queued',{'status':'queued','attempts':0,'workout_id':'synthetic','session_id':sid,
            'coach_id':'steady','privacy_revision':privacy.revision(db)})
    async def review(*args,**kwargs):
        assert client.delete('/api/health-data/measurements/'+key).status_code==200
        return {'ai_review':{'summary':MARKER}}
    async def forbidden(*args):raise AssertionError('cancelled followup must not progress')
    monkeypatch.setattr(worker,'app',module);monkeypatch.setattr(worker,'d',module.database)
    monkeypatch.setattr(worker,'auth',module.auth);monkeypatch.setattr(worker,'privacy',privacy)
    monkeypatch.setattr(module,'review_workout',review);monkeypatch.setattr(module,'progress_workout',forbidden)
    asyncio.run(worker.followup())
    with module.connection() as db:
        value=db.read('agent_followup','queued')
        assert value['status']=='cancelled_privacy_changed' and 'result' not in value
