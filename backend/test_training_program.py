"""Profile preferences, actual split/method structure, preservation and old-plan compatibility."""
from copy import deepcopy
import pytest
from fastapi import HTTPException
from test_app import module, client, PROFILE, isolate_records, ai_result, complete_strength_profile

@pytest.mark.parametrize('split,focuses', [(k,v[1]) for k,v in module.training_program.SPLITS.items()])
@pytest.mark.parametrize('method', ['straight_sets','five_by_five','strength_hypertrophy'])
def test_formats_validate_actual_focus_and_sets_not_just_labels(split, focuses, method):
    choices={'full_body':'bench','upper':'bench','lower':'squat','push':'bench','pull':'barbell_row','legs':'squat','chest':'bench','back':'barbell_row','shoulders':'seated_dumbbell_press','shoulders_arms':'dumbbell_curl','arms':'dumbbell_curl'}
    plan={'split_type':split,'days':[]}
    for focus in focuses:
        eid=choices[focus]
        main={'exercise_id':eid,'sets':5 if method=='five_by_five' else 3,'reps':5 if method!='straight_sets' else 8}
        actions=[main]
        if method=='strength_hypertrophy':
            extra='leg_curl' if focus in ('legs','lower') else 'dumbbell_lateral_raise' if focus=='shoulders' else eid
            actions.append({'exercise_id':extra,'sets':2,'reps':10})
        plan['days'].append({'name':focus,'focus':focus,'session_goal':'按目标余力完成主项','training_method':method,'primary_exercise_id':eid,'exercises':actions})
    module.training_program.validate(plan,{'training_split':split,'training_method':method})
    if method=='five_by_five':
        plan['days'][0]['exercises'][0]['reps']=6
        with pytest.raises(ValueError):module.training_program.validate(plan,{})
    if len(focuses)>1:
        plan['days'].pop()
        with pytest.raises(ValueError):module.training_program.validate(plan,{})

def test_profile_enums_roundtrip_and_schedule_conflict_before_model(monkeypatch):
    assert client.patch('/api/coach/profile',json={'training_split':'bodypart_five','training_method':'five_by_five'}).status_code==200
    assert client.get('/api/coach/profile').json()['facts']['training_split']=='bodypart_five'
    assert client.patch('/api/coach/profile',json={'training_split':'invented'}).status_code==422
    assert client.patch('/api/coach/profile',json={'training_method':'invented'}).status_code==422
    complete_strength_profile();client.put('/api/profile',json=PROFILE)
    async def forbidden(*args):raise AssertionError('schedule conflict must not call model')
    monkeypatch.setattr(module.ai_planner,'generate',forbidden)
    response=client.post('/api/plans/generate');assert response.status_code==422 and '至少需要5' in response.json()['detail']

@pytest.mark.parametrize('failure',['missing_goal','missing_method','wrong_focus','wrong_method','false_5x5'])
def test_generation_rejects_missing_or_mislabelled_details(monkeypatch,failure):
    complete_strength_profile();client.put('/api/profile',json=PROFILE);raw=ai_result()
    if failure=='missing_goal':raw['days'][0].pop('session_goal')
    if failure=='missing_method':raw['days'][0].pop('training_method')
    if failure=='wrong_focus':raw['days'][0]['focus']='legs'
    if failure=='wrong_method':
        client.patch('/api/coach/profile',json={'training_method':'five_by_five'})
    if failure=='false_5x5':raw['days'][0]['training_method']='five_by_five'
    async def fake(*args):return deepcopy(raw),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    assert client.post('/api/plans/generate').status_code==502
    assert module.records('plan_draft')==[]

def test_old_client_confirmation_preserves_day_details_and_future_metadata(monkeypatch):
    complete_strength_profile();client.put('/api/profile',json=PROFILE)
    async def fake(*args):return ai_result(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    draft=client.post('/api/plans/generate').json()
    days=deepcopy(draft['days'])
    for day in days:
        for key in module.training_program.DAY_FIELDS:day.pop(key)
    response=client.post('/api/plans',json={'name':draft['name'],'generation_id':draft['generation_id'],'days':days})
    assert response.status_code==200,response.text
    saved=response.json()
    assert saved['split_type']=='full_body'
    assert all(d['session_goal'] and d['training_method']=='straight_sets' and d['primary_exercise_id']=='bench' for w in saved['cycle_schedule'] for d in w['days'])
    edited=deepcopy(saved['days']);edited[0]['session_goal']='用户修改的训练目标'
    result=client.post('/api/plans',json={'name':saved['name'],'base_plan_id':saved['id'],'days':edited})
    assert result.status_code==200,result.text
    assert result.json()['cycle_schedule'][0]['days'][0]['session_goal']=='用户修改的训练目标'
    assert result.json()['cycle_schedule'][1]['days'][0]['session_goal']==saved['days'][0]['session_goal']

def test_method_constraint_survives_progression_and_recovery_switch():
    raw=ai_result();raw.update(training_program_version=module.training_program.VERSION,cycle_weeks=2)
    for day in raw['days']:
        day['training_method']='five_by_five';day['exercises'][0].update(sets=5,reps=5)
    value=module.periodization.normalized(raw)
    value['days'][0]['exercises'][0]['reps']=6
    with pytest.raises(HTTPException):module.periodization.activation_guard(value,{}, {'items':[]})
    value['days'][0]['exercises'][0]['reps']=5
    for day in value['days']:day['exercises'][0]['sets']=2
    value['cycle_schedule'][0]['phase']='deload'
    module.periodization.activation_guard(value,{}, {'items':[]})

def test_pull_accessories_overlap_without_allowing_unrelated_leg_actions():
    plan=ai_result();plan['split_type']='push_pull_legs'
    plan['days']=[{**plan['days'][0], 'focus':focus, 'primary_exercise_id':eid,
        'exercises':[{'exercise_id':eid,'sets':3,'reps':8}]} for focus,eid in [('push','bench'),('pull','cable_face_pull'),('legs','squat')]]
    module.training_program.validate(plan,{})
    plan['days'][1]['primary_exercise_id']='leg_press';plan['days'][1]['exercises'][0]['exercise_id']='leg_press'
    with pytest.raises(ValueError):module.training_program.validate(plan,{})

def test_old_unactivated_draft_requires_new_details_without_rewriting_saved_history(monkeypatch):
    complete_strength_profile();client.put('/api/profile',json=PROFILE)
    async def fake(*args):return ai_result(),'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    draft=client.post('/api/plans/generate').json()
    with module.connection() as db:
        stored=db.read('plan_draft',draft['id']);stored.pop('training_program_version');db.write('plan_draft',draft['id'],stored)
    result=client.post('/api/plans',json={k:draft[k] for k in ('name','days','generation_id')})
    assert result.status_code==409 and '每日目标' in result.json()['detail']
    assert module.records('plan')==[]

def test_generation_checks_future_day_details_too(monkeypatch):
    complete_strength_profile();client.put('/api/profile',json=PROFILE)
    raw=ai_result();raw['cycle_weeks']=2
    raw['cycle_schedule']=[{'week':i,'phase':'foundation','purpose':'固定目标','days':deepcopy(raw['days'])} for i in [1,2]]
    raw['cycle_schedule'][1]['days'][0]['session_goal']=None
    async def fake(*args):return raw,'test'
    monkeypatch.setattr(module.ai_planner,'generate',fake)
    assert client.post('/api/plans/generate').status_code==502
    assert module.records('plan_draft')==[]
