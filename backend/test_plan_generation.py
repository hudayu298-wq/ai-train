"""One bounded, fully revalidated repair; no fallback, stale context or private logging."""
from copy import deepcopy
import asyncio
import logging
import pytest
from fastapi import HTTPException
from test_app import module, client, PROFILE, isolate_records, ai_result, complete_strength_profile

def setup_profile():
    complete_strength_profile()
    assert client.put('/api/profile',json=PROFILE).status_code==200

def mixed_failure():
    raw=ai_result()
    raw['days'][0]['training_method']='strength_hypertrophy'
    raw['days'][0]['exercises'][0]['reps']=5
    raw['days'][0]['exercises'].append({'exercise_id':'barbell_row','weight_kg':30,'sets':3,'reps':6,'rest_seconds':120})
    return raw

def test_invalid_mixed_day_is_corrected_once_without_changing_user_facts(monkeypatch):
    setup_profile();calls=[];bad=mixed_failure()
    async def fake(profile,rms,schema):
        calls.append(deepcopy(profile))
        assert 'bodypart_five' not in schema['properties']['split_type']['enum']
        assert schema['$defs']['PlanDay']['properties']['primary_exercise_id']['type']=='string'
        if len(calls)==1:return deepcopy(bad),'test'
        feedback=profile['generation_feedback']
        assert feedback['validation_stage']=='program' and '混合训练法' in feedback['validation_error']
        assert feedback['rejected_proposal']==bad
        assert profile['regional_strength']==calls[0]['regional_strength']
        return ai_result(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    response=client.post('/api/plans/generate')
    assert response.status_code==200,response.text
    assert len(calls)==2 and len(module.records('plan_draft'))==1
    assert client.get('/api/rm').json()==[] and module.records('workout')==[]
    assert client.get('/api/profile').json()['weight_kg']==PROFILE['weight_kg']

@pytest.mark.parametrize('failure',['missing_goal','blank_weight','invalid_action','day_count','future_details'])
def test_failed_repair_remains_rejected_and_has_specific_safe_reason(monkeypatch,caplog,failure):
    setup_profile();raw=ai_result();calls=[]
    if failure=='missing_goal':raw['days'][0].pop('session_goal')
    if failure=='blank_weight':raw['days'][0]['exercises'][0]['weight_kg']=None
    if failure=='invalid_action':raw['days'][0]['exercises'][0]['exercise_id']='not_a_catalog_action'
    if failure=='day_count':raw['days'].pop()
    if failure=='future_details':
        raw['cycle_weeks']=2
        raw['cycle_schedule']=[{'week':i,'phase':'foundation','purpose':'固定目标','days':deepcopy(raw['days'])} for i in [1,2]]
        raw['cycle_schedule'][1]['days'][0]['session_goal']=None
    raw['rationale']='PRIVATE_CANDIDATE_SENTINEL'
    async def fake(*args):calls.append(1);return deepcopy(raw),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    with caplog.at_level(logging.WARNING,logger='lianban.plan_generation'):
        response=client.post('/api/plans/generate')
    assert response.status_code==502 and len(calls)==2
    assert 'AI计划校验未通过' in response.json()['detail'] and '诊断编号' in response.json()['detail']
    assert module.records('plan_draft')==[] and module.records('plan')==[]
    assert 'PRIVATE_CANDIDATE_SENTINEL' not in response.text and 'PRIVATE_CANDIDATE_SENTINEL' not in caplog.text
    assert 'plan_validation' in caplog.text and 'stage=' in caplog.text

@pytest.mark.parametrize('change',['profile','health_consent'])
def test_input_or_consent_change_prevents_second_provider_call(monkeypatch,change):
    setup_profile();calls=[]
    if change=='health_consent':
        assert client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':True}).status_code==200
    async def fake(*args):
        calls.append(1)
        if change=='profile':client.put('/api/profile',json={**PROFILE,'weight_kg':80})
        else:client.put('/api/health-data/settings',json={'storage_enabled':True,'ai_context_enabled':False})
        return mixed_failure(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    response=client.post('/api/plans/generate')
    assert response.status_code==409 and len(calls)==1
    assert module.records('plan_draft')==[]

def test_first_valid_response_does_not_call_model_again(monkeypatch):
    setup_profile();calls=[]
    async def fake(profile,*args):
        calls.append(1);assert 'generation_feedback' not in profile
        return ai_result(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    assert client.post('/api/plans/generate').status_code==200 and len(calls)==1

@pytest.mark.parametrize('provider_error',[HTTPException(503,'模型未配置'),asyncio.TimeoutError()])
def test_provider_failure_or_timeout_is_not_blindly_replayed(monkeypatch,provider_error):
    setup_profile();calls=[]
    async def fake(*args):calls.append(1);raise provider_error
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    response=client.post('/api/plans/generate')
    assert response.status_code in (503,504) and len(calls)==1
    assert module.records('plan_draft')==[]

def test_repair_cannot_bypass_same_action_rm_limit(monkeypatch):
    setup_profile();calls=[]
    assert client.post('/api/rm',json={'exercise_id':'bench','weight_kg':50,'reps':1,'confirmed_maximum':True,'measured_on':module.nutrition_today().isoformat()}).status_code==200
    async def fake(*args):
        calls.append(1)
        return mixed_failure() if len(calls)==1 else ai_result(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    response=client.post('/api/plans/generate')
    assert response.status_code==502 and len(calls)==2 and 'RM参考' in response.json()['detail']
    assert module.records('plan_draft')==[]

def test_request_contract_never_advertises_unavailable_actions():
    contract=module.training_program.contract({'days':4,'training_split':'auto'},['bench','barbell_row','squat'])
    assert 'bodypart_five' not in contract['splits']
    assert all(set(ids)<={'bench','barbell_row','squat'} for ids in contract['focus_exercise_ids'].values())
    assert 'bodypart_four' not in contract['splits'] # No shoulder/arm action for that required group.
