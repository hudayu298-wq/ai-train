"""Cache boundaries and transactions. Fake transport here; real Redis smoke is separate."""
import copy
import json
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import update
from test_app import module,client,isolate_records,PROFILE
from services import cache,knowledge_store as kb,knowledge_retrieval as retrieval,prompt_registry


class FakeRedis:
    def __init__(self):self.values={};self.sets={};self.broken=False
    def get(self,key):
        if self.broken:raise ConnectionError('unavailable')
        return self.values.get(key)
    def pipeline(self,**kwargs):return self
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def set(self,key,value,ex=None):self.values[key]=value
    def sadd(self,key,value):self.sets.setdefault(key,set()).add(value)
    def expire(self,*args):pass
    def execute(self):pass
    def smembers(self,key):
        if self.broken:raise ConnectionError('unavailable')
        return self.sets.get(key,set())
    def unlink(self,*keys):
        for key in keys:self.values.pop(key,None);self.sets.pop(key,None)
    def ping(self):return not self.broken


@pytest.fixture
def redis_cache(monkeypatch,isolate_records):
    server=FakeRedis()
    monkeypatch.setenv('REDIS_URL','redis://127.0.0.1:6379/15')
    monkeypatch.setenv('REDIS_CACHE_NAMESPACE','cache-test:'+uuid4().hex)
    monkeypatch.setattr(cache,'client',lambda:server)
    monkeypatch.setattr(cache,'_down_until',0)
    prompt_registry._asset.cache_clear()
    yield server
    prompt_registry._asset.cache_clear()


def workout(notes='PRIVATE_MEMORY_SENTINEL'):
    return {'day':module.workouts.today().isoformat(),'source':'manual','notes':notes,'created_at':'2026-10-29T00:00:00Z',
        'exercises':[{'exercise_id':'bench','name':'卧推','weight_basis':'总重',
            'sets':[{'weight_kg':40,'reps':8,'rpe':7,'pain':False}]}]}


def seed():
    with module.connection() as db:db.write('workout','one',workout())


def read_memory():
    with module.connection() as db:return module.workouts.memory(db)


def test_hit_is_encrypted_and_model_view_cannot_mutate_cached_facts(redis_cache,monkeypatch):
    seed();first=read_memory()
    assert first['session_count']==1
    assert redis_cache.values and all(b'PRIVATE_MEMORY_SENTINEL' not in v for v in redis_cache.values.values())
    original=module.workouts.history
    monkeypatch.setattr(module.workouts,'history',lambda db:(_ for _ in ()).throw(AssertionError('cache must avoid full history')))
    second=read_memory();second['recent_sessions'][0]['notes']='changed'
    assert read_memory()['recent_sessions'][0]['notes']=='PRIVATE_MEMORY_SENTINEL'
    monkeypatch.setattr(module.workouts,'history',original)
    with module.connection() as db:
        db.write('workout','one',{**workout(),'ai_review':{'summary':'suggestion'}})
    read_memory()
    with module.connection() as db:
        assert 'ai_review' not in module.workouts.model_memory(db)['recent_sessions'][0]
        assert module.workouts.memory(db)['recent_sessions'][0]['ai_review']=={'summary':'suggestion'}


def test_commit_invalidates_and_rollback_never_publishes_uncommitted_memory(redis_cache):
    seed();read_memory();old_keys=set(redis_cache.values)
    with pytest.raises(RuntimeError):
        with module.connection() as db:
            db.write('workout','two',workout('uncommitted'))
            assert module.workouts.memory(db)['session_count']==2
            raise RuntimeError('rollback')
    assert read_memory()['session_count']==1 and set(redis_cache.values)==old_keys
    with module.connection() as db:
        db.write('workout','two',workout('confirmed'))
        assert module.workouts.memory(db)['session_count']==2
    assert not old_keys & set(redis_cache.values)
    assert read_memory()['session_count']==2


def test_owner_isolation_access_recheck_and_account_deletion(redis_cache):
    seed();read_memory();first_owner=module.database.owner()
    with module.connection() as db:
        user=module.auth.new_user(db.conn,email='cache-other@example.test')
    token=module.database.owner_context.set(user['id'])
    try:
        assert read_memory()['session_count']==0
        assert read_memory()['session_count']==0
    finally:module.database.owner_context.reset(token)
    assert read_memory()['session_count']==1
    assert all(first_owner not in str(k) for k in redis_cache.values)
    assert not any(row['kind']=='cache_meta' for row in client.get('/api/me/export').json()['records'])
    assert client.delete('/api/me').status_code==200
    with pytest.raises(HTTPException):read_memory()


def test_redis_outage_cannot_block_writes_or_return_old_epoch(redis_cache):
    seed();read_memory();redis_cache.broken=True
    with module.connection() as db:db.write('workout','two',workout('new'))
    assert read_memory()['session_count']==2
    redis_cache.broken=False
    assert read_memory()['session_count']==2


def test_profile_change_and_consent_revoke_are_live_and_chat_checkpoints_keep_cache(redis_cache):
    assert client.put('/api/profile',json=PROFILE).status_code==200
    with module.connection() as db:assert module.coach.state(db)['facts']['weight_kg']==70
    keys=set(redis_cache.values)
    with module.connection() as db:db.write('agent_run','run',{'status':'running'})
    assert keys<=set(redis_cache.values)
    assert client.patch('/api/coach/profile',json={'weight_kg':72}).status_code==200
    with module.connection() as db:assert module.coach.state(db)['facts']['weight_kg']==72
    assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':True}).status_code==200
    with module.connection() as db:module.coach.state(db)
    assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':False}).status_code==200
    with module.connection() as db:
        assert module.coach.state(db)['health_context']['enabled'] is False


def test_knowledge_cache_checks_withdrawals_versions_and_bypasses_explicit_evaluation(redis_cache,monkeypatch):
    calls=[]
    def rank(db,bundle,allowed,query,**kwargs):
        calls.append(query)
        key='rectus_femoris' if 'rectus_femoris' in allowed else next(iter(allowed))
        return [{'id':key,'passages':[]}],{'effective_mode':'hybrid_rerank','latency_ms':123,'fallback_reason':None}
    monkeypatch.setattr(retrieval,'rank',rank)
    query='PRIVATE_QUERY_SENTINEL 股直肌'
    with module.connection() as db:first=kb.retrieve(db,query)
    with module.connection() as db:second=kb.retrieve(db,query)
    assert len(calls)==1 and second['retrieval']['cache_hit'] and second['retrieval']['origin_latency_ms']==123
    with module.connection() as db:kb.retrieve(db,query,mode='hybrid_rerank')
    assert len(calls)==2
    from services import research_store
    with module.connection() as db:research_store.put(db,'kb_withdrawal','one',{'target':'item:rectus_femoris'},'withdrawn')
    with module.connection() as db:third=kb.retrieve(db,query)
    assert len(calls)==3 and not any(i['id']=='rectus_femoris' for i in third['items'])
    assert all('PRIVATE_QUERY_SENTINEL' not in k for k in redis_cache.values)


def test_prompt_file_change_and_corrupt_cache_fall_back_to_source(redis_cache,monkeypatch,tmp_path):
    root=tmp_path/'backend';(root/'prompts').mkdir(parents=True);file=root/'prompts/plan.md';file.write_text('first',encoding='utf-8')
    monkeypatch.setattr(prompt_registry,'ROOT',root)
    assert prompt_registry.text('plan.md')=='first'
    for key in redis_cache.values:redis_cache.values[key]=b'corrupted'
    prompt_registry._asset.cache_clear()
    assert prompt_registry.text('plan.md')=='first'
    file.write_text('second',encoding='utf-8')
    assert prompt_registry.text('plan.md')=='second'
    with pytest.raises(ValueError):prompt_registry.text('../other.md')


def test_cache_status_is_admin_only_and_hides_connection_details(redis_cache):
    result=client.get('/api/cache/status')
    assert result.status_code==200 and result.json()['available'] is True
    assert 'redis://' not in result.text and 'REDIS_URL' not in result.text
    with module.connection() as db:
        db.conn.execute(update(module.database.users).where(module.database.users.c.id==module.database.owner()).values(role='user'))
    assert client.get('/api/cache/status').status_code==403
