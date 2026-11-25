import copy
from datetime import timedelta
import pytest
from sqlalchemy import delete,update
from test_app import module,client,isolate_records,PLAN,workout_payload

@pytest.fixture(autouse=True)
def clean_shared():
    with module.connection() as db:
        db.conn.execute(delete(module.database.research_records).where(module.database.research_records.c.kind.in_(['locale_proposal','exercise_locale','catalog_lock'])))
    yield
    with module.connection() as db:
        db.conn.execute(delete(module.database.research_records).where(module.database.research_records.c.kind.in_(['locale_proposal','exercise_locale','catalog_lock'])))

def plan_start():
    plan=client.post('/api/plans',json=PLAN).json()
    body={'request_id':'start-example-001','plan_id':plan['id'],'plan_day':'周一'}
    start=client.post('/api/workouts/start',json=body)
    assert start.status_code==200
    assert start.json()['plan_snapshot']['id']==plan['id']
    assert client.post('/api/workouts/start',json=body).json()==start.json()
    return plan,start.json()

def test_frozen_targets_persist_and_cannot_be_reused_or_cross_owner():
    plan,start=plan_start()
    assert 'coach_profile_snapshot' not in start['plan_snapshot']
    with module.connection() as db:
        changed=db.read('plan',plan['id']);changed['days'][0]['exercises'][0]['weight_kg']=90
        db.write('plan',plan['id'],changed)
    body=workout_payload('frozen-workout-01',plan_id=plan['id'],plan_day='周一',execution_id=start['id'])
    wrong_date=client.post('/api/workouts',json={**body,'day':(module.workouts.today()-timedelta(days=1)).isoformat()})
    assert wrong_date.status_code==409 and '日期' in wrong_date.json()['detail']
    saved=client.post('/api/workouts',json=body)
    assert saved.status_code==200
    comparison=saved.json()['summary']['target_comparison']
    assert comparison['basis']=='server_plan_at_start' and comparison['sets'][0]['target']['weight_kg']==75
    assert client.post('/api/workouts',json=body).json()['id']==saved.json()['id']
    assert client.post('/api/workouts',json={**body,'request_id':'another-frozen-02'}).status_code==409
    with module.connection() as db:
        other=module.auth.new_user(db.conn,name='other execution owner')
        tokens=module.auth.create_session(db.conn,other,'test')
    assert client.post('/api/workouts',headers={'Authorization':'Bearer '+tokens['access_token']},json=body).status_code==404

def test_frozen_plan_edit_holds_progression_without_model(monkeypatch):
    plan,start=plan_start()
    with module.connection() as db:
        changed=db.read('plan',plan['id']);changed['days'][0]['exercises'][0]['reps']=8;db.write('plan',plan['id'],changed)
    body=workout_payload('frozen-progress-01',plan_id=plan['id'],plan_day='周一',execution_id=start['id'])
    record=client.post('/api/workouts',json=body).json()
    async def forbidden(*args,**kwargs):raise AssertionError('model must not run')
    monkeypatch.setattr(module.ai_planner,'chat_json',forbidden)
    result=client.post('/api/workouts/'+record['id']+'/progression',json={})
    assert result.status_code==200 and result.json()['status']=='held'
    assert '开练后' in result.json()['summary']

@pytest.mark.parametrize('group',[['bench'],['bench','bench'],['bench','not-present']])
def test_bad_alternating_groups_rejected(group):
    body=workout_payload(execution_groups=[group])
    assert client.post('/api/workouts',json=body).status_code==422

def test_valid_alternating_groups_and_trends():
    body=workout_payload(execution_groups=[['bench','squat']])
    body['exercises'].append({**copy.deepcopy(body['exercises'][0]),'exercise_id':'squat'})
    saved=client.post('/api/workouts',json=body)
    assert saved.status_code==200 and saved.json()['execution_groups']==[['bench','squat']]
    trends=client.get('/api/training-trends?days=28').json()
    assert sum(w['working_sets'] for w in trends['weeks'])==4
    assert sum(c['sessions'] for c in trends['cycles'])==1
    assert trends['muscles'] and '不能相加' in trends['note']

@pytest.mark.parametrize('setting',[{'rpe_ceiling':9},{'max_weight_increase_fraction':.1},{'min_sessions':1},{'max_rep_change':2}])
def test_progression_cannot_relax_limits(setting):
    assert client.put('/api/training-settings',json=setting).status_code==422

def test_disabled_progression_and_owner_settings(monkeypatch):
    assert client.put('/api/training-settings',json={'enabled':False}).status_code==200
    saved=client.post('/api/workouts',json=workout_payload()).json()
    async def forbidden(*args,**kwargs):raise AssertionError('model must not run')
    monkeypatch.setattr(module.ai_planner,'chat_json',forbidden)
    held=client.post('/api/workouts/'+saved['id']+'/progression',json={}).json()
    assert held['status']=='held' and '关闭' in held['summary']
    with module.connection() as db:
        other=module.auth.new_user(db.conn,name='other settings owner');tokens=module.auth.create_session(db.conn,other,'test')
    assert client.get('/api/training-settings',headers={'Authorization':'Bearer '+tokens['access_token']}).json()['enabled'] is True

def proposal():
    response=client.post('/api/catalog-content',json={'exercise_id':'bench','language':'zh','name':'杠铃平板卧推',
        'description':'控制动作并保留余力','source_note':'基于原条目作中文编辑','share_publicly':True})
    assert response.status_code==200
    return response.json()

def test_translation_review_publish_withdraw_and_no_knowledge_activation():
    with module.connection() as db:
        before_pointer=db.conn.execute(module.database.research_records.select().where(module.database.research_records.c.kind=='pointer')).mappings().all()
    item=proposal()
    assert client.get('/api/library/exercises/bench').json()['name']=='平板杠铃卧推'
    assert client.post('/api/catalog-content/'+item['id']+'/review',json={'approved':True,'notes':'已核对原文及动作身份'}).status_code==200
    assert client.get('/api/library/exercises/bench').json()['name']=='杠铃平板卧推'
    assert client.get('/api/library/exercises/bench?language=en').json()['original_name']
    assert client.post('/api/catalog-content/'+item['id']+'/withdraw',json={}).status_code==200
    assert client.get('/api/library/exercises/bench').json()['name']=='平板杠铃卧推'
    with module.connection() as db:
        assert db.conn.execute(module.database.research_records.select().where(module.database.research_records.c.kind=='pointer')).mappings().all()==before_pointer

def test_translation_permission_and_stale_source():
    item=proposal()
    uid=module.database.owner()
    with module.connection() as db:db.conn.execute(update(module.database.users).where(module.database.users.c.id==uid).values(role='user'))
    assert client.post('/api/catalog-content/'+item['id']+'/review',json={'approved':True,'notes':'已经核对来源文本'}).status_code==403
    with module.connection() as db:
        db.conn.execute(update(module.database.users).where(module.database.users.c.id==uid).values(role='admin'))
        entry=db.catalog_read('exercises','bench');db.catalog_update('exercises','bench',payload={**entry,'summary':'changed'})
    assert client.post('/api/catalog-content/'+item['id']+'/review',json={'approved':True,'notes':'已经核对来源文本'}).status_code==409

PRODUCT={'code':'12345678','product_name_zh':'测试包装食品','nutrition_data_per':'100g',
    'nutriments':{'energy-kcal_100g':200,'proteins_100g':10,'fat_100g':4,'carbohydrates_100g':30}}

def test_external_food_requires_confirmation_owner_isolation_and_deterministic_meal(monkeypatch):
    async def fetch(code):return {'status':'success','product':copy.deepcopy(PRODUCT)}
    monkeypatch.setattr(module.external_foods,'fetch',fetch)
    candidate=client.get('/api/external-foods/12345678')
    assert candidate.status_code==200 and candidate.json()['requires_confirmation']
    assert client.get('/api/library/foods/off_12345678').status_code==404
    assert client.post('/api/external-foods/12345678/confirm',json={'confirmed':True}).status_code==200
    assert client.get('/api/meals').json()==[]
    meal=client.post('/api/meals',json={'food_id':'off_12345678','grams':50})
    assert meal.status_code==200 and meal.json()['nutrients']['kcal']==100
    with module.connection() as db:
        other=module.auth.new_user(db.conn,name='other food owner');tokens=module.auth.create_session(db.conn,other,'test')
    header={'Authorization':'Bearer '+tokens['access_token']}
    assert client.get('/api/library/foods/off_12345678',headers=header).status_code==404
    assert client.post('/api/external-foods/12345678/confirm',headers=header,json={'confirmed':True}).status_code==409

@pytest.mark.parametrize('patch',[{'nutrition_data_per':'serving'},{'nutriments':{'energy-kcal_100g':200}},{'code':'99999999'}])
def test_external_food_rejects_ambiguous_basis_missing_values_and_wrong_code(monkeypatch,patch):
    async def fetch(code):return {'status':'success','product':{**copy.deepcopy(PRODUCT),**patch}}
    monkeypatch.setattr(module.external_foods,'fetch',fetch)
    assert client.get('/api/external-foods/12345678').status_code in (422,502)
    assert client.post('/api/external-foods/12345678/confirm',json={'confirmed':True}).status_code==409


def test_start_rejects_historical_date_and_binds_minimal_identity():
    plan,start=plan_start()
    assert start['plan_snapshot']['id']==plan['id']
    assert set(start['plan_snapshot']) <= {'id','name','version','cycle_id','cycle_week','cycle_weeks','week_attempt','days','source'}
    response=client.post('/api/workouts/start',json={'request_id':'historical-start-01','plan_id':plan['id'],'plan_day':'周一',
        'day':(module.workouts.today()-timedelta(days=1)).isoformat()})
    assert response.status_code==422


def test_off_v36_nested_nutrition_accepts_label_values_and_rejects_estimates(monkeypatch):
    facts={key:{'value':value,'unit':'kcal' if key=='energy-kcal' else 'g',
        'source':'manufacturer','source_per':'100g'} for key,value in [('energy-kcal',200),('proteins',10),('fat',4),('carbohydrates',30)]}
    product={**copy.deepcopy(PRODUCT),'nutriments':{},'nutrition':{'aggregated_set':{'nutrients':facts}}}
    food=module.external_foods.normalize(product,'12345678')
    assert food['kcal']==200
    facts['fat']['source']='estimate'
    from fastapi import HTTPException
    with pytest.raises(HTTPException):module.external_foods.normalize(product,'12345678')
