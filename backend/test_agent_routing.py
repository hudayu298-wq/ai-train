"""Routing accuracy boundaries, scoped tools/context, recovery and native APIs."""
import asyncio
import copy
import json
import math
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException

from test_app import module,client,isolate_records,PROFILE
from test_agent_health import tool_message,final_message
from services import agent_routing as routing,decision_gateway,model_gateway
from services import agent_harness as harness


@pytest.mark.parametrize('message,expected',[
    ('今天午餐150克米饭，帮我记录',{'nutrition'}),
    ('重新安排三分化训练计划',{'plan'}),
    ('我昨晚睡眠很差，手表HRV下降',{'health'}),
    ('帮我记录卧推50公斤三组，RPE7，没有疼痛或不适',{'training'}),
    ('查股二头肌短头的起止点',{'knowledge'}),
    ('我的年龄28岁，身高175厘米',{'profile'}),
    ('膝盖疼，训练计划怎么改，晚饭吃什么',{'health','plan','nutrition'}),
    ('每天饭后撑得难受，怎么搭配',{'health','nutrition'}),
    ('这周只能去两趟健身房，帮我重新编排日程',{'plan'}),
])
def test_explicit_routes_preserve_all_domains(message,expected):
    result=routing.rules(message)
    assert expected<=set(result['domains'])
    if '没有疼痛' in message:assert 'health_caution' not in result['risk_flags']


def test_followup_uses_authorized_user_turn_and_explicit_topic_switch_wins():
    prior={'user_message':'今天午餐怎么吃','routing':routing.public(routing.rules('今天午餐怎么吃'))}
    assert routing.rules('那晚上呢？',[prior])['domains']==['nutrition']
    assert routing.rules('重新制定训练计划',[prior])['domains']==['plan']
    assert routing.rules('请结合我的记录给出建议')['scope']=='full'


def test_negated_plan_and_profile_actions_do_not_pollute_workout_route():
    result=routing.rules('帮我记录卧推40公斤8次RPE7，没有疼痛或不适。不关联计划，不修改画像。')
    assert result['domains']==['training'] and not result['risk_flags']
    assert 'plan' in routing.rules('不要修改计划，解释当前训练计划为什么这样安排')['domains']


def test_exercise_search_is_compact_and_details_remain_available():
    result=asyncio.run(module.agent_service.tool('synthetic',{}, {},'search_exercises',{'query':'卧推'},'compact'))
    assert any(row['id']=='bench' for row in result)
    assert all('weight_basis' in row and 'assets' not in row and 'technique' not in row for row in result)
    details=asyncio.run(module.agent_service.tool('synthetic',{}, {},'get_exercise_details',{'exercise_id':'bench'},'detail'))
    assert details['id']=='bench' and details['weight_basis']
    assert len(json.dumps(result,ensure_ascii=False))<len(json.dumps([details]*len(result),ensure_ascii=False))


def test_semantic_layer_accepts_score_and_abstains_on_ambiguity_failure_or_absent_assets(monkeypatch):
    monkeypatch.setenv('AGENT_ROUTING_MODE','hybrid')
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','local')
    monkeypatch.setattr(routing.neural,'assets_present',lambda _:True)
    monkeypatch.setattr(routing,'semantic_scores',lambda _: [('plan',.84),('training',.6)])
    assert asyncio.run(routing.select('下个月想换一套方案'))['domains']==['plan']
    monkeypatch.setattr(routing,'semantic_scores',lambda _: [('plan',.68),('training',.66)])
    assert asyncio.run(routing.select('下个月想换一套方案'))['scope']=='full'
    def fail(_):raise RuntimeError('local unavailable')
    monkeypatch.setattr(routing,'semantic_scores',fail)
    assert asyncio.run(routing.select('下个月想换一套方案'))['scope']=='full'
    monkeypatch.setattr(routing.neural,'assets_present',lambda _:False)
    assert asyncio.run(routing.select('下个月想换一套方案'))['stages'][-1]['outcome']=='semantic_assets_unavailable'


def test_semantic_timeout_is_bounded_and_long_input_is_not_silently_truncated(monkeypatch):
    monkeypatch.setenv('AGENT_ROUTING_MODE','hybrid')
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','local')
    monkeypatch.setattr(routing.neural,'assets_present',lambda _:True)
    monkeypatch.setattr(routing,'semantic_scores',lambda _: (_ for _ in ()).throw(TimeoutError()))
    assert asyncio.run(routing.select('整个人感觉有点蔫'))['scope']=='full'
    assert asyncio.run(routing.select('蔫'*501))['stages'][-1]['outcome']=='long_message_general'


def test_nutrition_source_and_provider_payload_exclude_unrelated_plan_rm_catalog(monkeypatch):
    client.put('/api/profile',json={**PROFILE,'restrictions':'历史膝部伤病'})
    for key in ('get_plans','get_rm','exercise_entries'):
        monkeypatch.setattr(module,key,lambda:(_ for _ in ()).throw(AssertionError('unrelated source loaded')))
    seen=[]
    async def fake(messages,tools,**kwargs):
        seen.append(copy.deepcopy(messages))
        names={t['function']['name'] for t in tools}
        assert 'propose_meal' in names and 'propose_plan' not in names and 'propose_workout' not in names
        return final_message('请核对食物和实际克重。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'nutrition-scope-001','message':'今天晚餐怎么吃'}).json()
    assert result['status']=='completed' and result['routing']['domains']==['nutrition']
    context=json.loads(seen[0][1]['content'])['context']
    assert 'nutrition' in context and not {'current_plan','rm','exercise_catalog','training_memory'}&context.keys()
    assert context['health_context']=={'enabled':False,'omitted_for_route':True}
    assert context['known_profile']['restrictions']=='历史膝部伤病'


def test_out_of_domain_tool_is_rejected_before_business_handler(monkeypatch):
    count=0
    async def fake(messages,tools,**kwargs):
        nonlocal count
        count+=1
        return tool_message('propose_plan',{'scope':'current_profile'}) if count==1 else final_message('本轮只讨论饮食。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'routing-tool-block','message':'今天早餐怎么吃'}).json()
    assert result['status']=='completed' and result['actions']==[]
    with module.connection() as db:run=db.read('agent_run',result['run_id'])
    assert any(s['type']=='tool' and s['status']=='rejected' and s['name']=='propose_plan' for s in run['steps'])
    assert module.records('plan_draft')==[] and module.records('plan')==[]


def test_cross_domain_expansion_changes_context_and_tools_but_only_stages_actions(monkeypatch):
    count=0
    async def fake(messages,tools,**kwargs):
        nonlocal count
        count+=1
        names={t['function']['name'] for t in tools}
        if count==1:
            assert 'propose_meal' not in names
            return tool_message('request_route',{'domains':['nutrition']},'expand')
        assert 'propose_meal' in names
        if count==2:
            context=json.loads(messages[1]['content'])['context']
            assert 'nutrition' in context and 'health_context' in context
            return tool_message('propose_meal',{'food_id':'rice','grams':150,'meal_type':'lunch','portion_source':'weighed'},'meal')
        return final_message()
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'cross-domain-scope','message':'昨天睡眠如何'}).json()
    assert result['status']=='completed',result
    assert set(result['routing']['domains'])=={'health','nutrition'}
    assert result['actions'][0]['status']=='pending' and client.get('/api/meals').json()==[]
    assert result['routing']['expansions']==1
    route=routing.rules('膝盖疼，怎么改计划')
    route=routing.expand(route,['nutrition'])
    assert 'health_caution' in route['risk_flags']
    route=routing.expand(route,['profile'])
    with pytest.raises(ValueError):routing.expand(route,['general'])


def test_expanded_route_survives_resume_and_changed_policy_refuses_old_checkpoint(monkeypatch):
    count=0
    async def fake(messages,tools,**kwargs):
        nonlocal count
        count+=1
        if count==1:return tool_message('request_route',{'domains':['plan']},'expand-plan')
        assert 'propose_plan' in {t['function']['name'] for t in tools}
        if count==2:raise HTTPException(504,'provider timeout')
        return final_message('请补齐力量资料后再制定草稿。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'expanded-route-resume','message':'昨晚失眠'}).json()
    assert result['status']=='failed'
    assert client.post('/api/agent/runs/'+result['run_id']+'/resume').json()['status']=='completed'
    count=0
    result=client.post('/api/agent/runs',json={'request_id':'changed-route-policy','message':'昨晚失眠'}).json()
    assert result['status']=='failed'
    monkeypatch.setattr(routing,'fingerprint',lambda:'changed')
    assert client.post('/api/agent/runs/'+result['run_id']+'/resume').status_code==409


def native_response(provider,*,health=.02,plan=.02,nutrition=.97,**extra):
    values={name:.02 for name in routing.DOMAINS}
    values.update(health=health,plan=plan,nutrition=nutrition,**extra)
    answers=([{'type':'predicate','name':name,'probability':value} for name,value in values.items()] if provider=='openai'
        else {name:{'type':'noul','noul':value} for name,value in values.items()})
    return {'model':'gpt-6-luna' if provider=='openai' else 'jev-1.14.0','answers':answers,
        'usage':{'input_tokens':120,'output_tokens':5}}


@pytest.mark.parametrize('provider,key_name',[('openai','OPENAI_API_KEY'),('jev','TYPESAFE_API_KEY')])
def test_native_provider_request_and_response_shapes_and_shared_budget(provider,key_name,monkeypatch):
    monkeypatch.setenv('AGENT_DECISION_PROVIDER',provider)
    monkeypatch.setenv(key_name,'synthetic-test-key')
    decision_gateway._unavailable_until.clear()
    requests=[]
    def handle(request):
        requests.append(request)
        body=json.loads(request.content)
        assert str(request.url)==decision_gateway.ENDPOINTS[provider]
        assert '/chat/completions' not in str(request.url)
        if provider=='openai':assert isinstance(body['questions'],list) and body['input']=='synthetic question'
        else:assert isinstance(body['questions'],dict) and body['state']=='synthetic question'
        return httpx.Response(200,json=native_response(provider))
    original=httpx.AsyncClient
    monkeypatch.setattr(decision_gateway.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    events=[]
    with model_gateway.budget(events,max_calls=1):
        result=asyncio.run(decision_gateway.classify('synthetic question',routing.DECISION_QUESTIONS))
        with pytest.raises(HTTPException):asyncio.run(decision_gateway.classify('synthetic question',routing.DECISION_QUESTIONS))
    assert len(requests)==1 and events[0]['kind']=='decision' and events[0]['usage']['total_tokens']==125
    route=routing.apply_decision(routing.rules('一碗面配什么'),result)
    assert route['domains']==['nutrition']


@pytest.mark.parametrize('bad',[float('nan'),float('inf'),-.1,1.01,True,'0.9'])
def test_invalid_probability_is_never_a_route(bad):
    response=native_response('openai')
    response['answers'][0]['probability']=bad
    with pytest.raises(decision_gateway.DecisionUnavailable):decision_gateway.probabilities('openai',response,routing.DOMAINS)


def test_refusal_partial_response_and_uncertainty_keep_general_route():
    for provider in ('openai','jev'):
        response=native_response(provider)
        if provider=='openai':response['answers'][0]['type']='refusal'
        else:response['answers']['health']['type']='refusal'
        with pytest.raises(decision_gateway.DecisionUnavailable):decision_gateway.probabilities(provider,response,routing.DOMAINS)
    result={'provider':'openai','model':'gpt-6-luna','latency_ms':10,
        'probabilities':{name:.5 for name in routing.DOMAINS}}
    assert routing.apply_decision(routing.rules('蔫了'),result)['scope']=='full'


def test_missing_dedicated_key_never_reuses_chat_key_or_calls_provider(monkeypatch):
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','openai')
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.setenv('AI_API_KEY','synthetic-other-provider-key')
    assert not decision_gateway.settings()['configured']
    with pytest.raises(decision_gateway.DecisionUnavailable):
        asyncio.run(decision_gateway.classify('synthetic',routing.DECISION_QUESTIONS))
    status=client.get('/api/agent/routing/status')
    assert status.status_code==200 and 'synthetic-other-provider-key' not in status.text


def test_provider_decision_is_audited_once_and_only_current_question_is_sent(monkeypatch):
    monkeypatch.setenv('AGENT_ROUTING_MODE','hybrid')
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','openai')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-decision-key')
    decision_gateway._unavailable_until.clear()
    requests=[]
    def handle(request):
        body=json.loads(request.content);requests.append(body)
        assert body['input']=='一碗面配什么比较好'
        assert 'known_profile' not in body and 'context' not in body
        return httpx.Response(200,json=native_response('openai'))
    original=httpx.AsyncClient
    monkeypatch.setattr(decision_gateway.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    async def final(messages,tools,**kwargs):
        if '睡眠' in messages[-1]['content']:return final_message('HEALTH_PRIVATE_SENTINEL')
        assert 'propose_plan' not in {t['function']['name'] for t in tools}
        assert 'HEALTH_PRIVATE_SENTINEL' not in json.dumps(messages)
        return final_message('请告诉我实际份量。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',final)
    assert client.post('/api/agent/runs',json={'request_id':'prior-health-context','message':'我的睡眠怎么样'}).json()['status']=='completed'
    body={'request_id':'external-route-once','message':'一碗面配什么比较好'}
    result=client.post('/api/agent/runs',json=body).json()
    assert result['status']=='completed' and result['routing']['method']=='decision',result
    assert client.post('/api/agent/runs',json=body).json()['run_id']==result['run_id'] and len(requests)==1
    with module.connection() as db:run=db.read('agent_run',result['run_id'])
    assert run['usage_events'][0]['kind']=='decision' and run['decision_attempted']


def test_external_failure_uses_local_fallback_without_repeating_on_resume(monkeypatch):
    monkeypatch.setenv('AGENT_ROUTING_MODE','hybrid')
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','openai')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-key')
    monkeypatch.setattr(routing.neural,'assets_present',lambda _:False)
    decision_gateway._unavailable_until.clear()
    requests=[]
    def handle(request):requests.append(request);return httpx.Response(403,json={'error':'access unavailable'})
    original=httpx.AsyncClient
    monkeypatch.setattr(decision_gateway.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    count=0
    async def fake(*args,**kwargs):
        nonlocal count
        count+=1
        if count==1:raise HTTPException(504,'temporary generation failure')
        return final_message('请说明想讨论哪个方面。')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    result=client.post('/api/agent/runs',json={'request_id':'external-failed-once','message':'整个人蔫了'}).json()
    assert result['status']=='failed' and result['routing']['scope']=='full'
    assert client.post('/api/agent/runs/'+result['run_id']+'/resume').json()['status']=='completed'
    assert len(requests)==1


def test_interrupted_tool_batch_cannot_smuggle_new_tool_after_route_expansion(monkeypatch):
    route=routing.rules('今天午餐怎么吃')
    calls=[]
    def offered():return [t for t in [*harness.TOOLS,harness.ROUTE_TOOL] if t['function']['name'] in routing.allowed_tools(route)]
    first=tool_message('request_route',{'domains':['plan']},'expand-first')
    first['message']['tool_calls'].append(tool_message('propose_plan',{'scope':'current_profile'},'smuggled')['message']['tool_calls'][0])
    count=0
    async def fake(*args,**kwargs):
        nonlocal count
        count+=1
        return first if count==1 else final_message('需要在下一轮使用新增工具。')
    async def execute(name,args,cid):
        nonlocal route
        calls.append(name)
        assert name=='request_route','unadvertised plan tool must not execute'
        route=routing.expand(route,args['domains'])
        return {'routing':routing.public(route)}
    def interrupt(messages,steps):
        if any(s['type']=='tool' for s in steps):raise HTTPException(504,'simulated process interruption')
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    messages=[{'role':'user','content':'今天午餐怎么吃'}];steps=[]
    with pytest.raises(HTTPException):
        asyncio.run(harness.drive(messages,execute,steps=steps,checkpoint=interrupt,tools=offered))
    asyncio.run(harness.drive(messages,execute,steps=steps,tools=offered))
    assert calls==['request_route']
    assert any(s.get('call_id')=='smuggled' and s['status']=='rejected' for s in steps)


def test_native_http_timeout_is_not_a_successful_decision_and_usage_is_preserved(monkeypatch):
    monkeypatch.setenv('AGENT_DECISION_PROVIDER','openai')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-key')
    decision_gateway._unavailable_until.clear()
    def handle(request):raise httpx.ReadTimeout('synthetic timeout',request=request)
    original=httpx.AsyncClient
    monkeypatch.setattr(decision_gateway.httpx,'AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))
    events=[]
    with model_gateway.budget(events):
        with pytest.raises(decision_gateway.DecisionUnavailable,match='provider_timeout'):
            asyncio.run(decision_gateway.classify('synthetic',routing.DECISION_QUESTIONS))
    assert events[0]['status']=='failed' and 'usage' not in events[0]


def test_route_metadata_is_owner_scoped(monkeypatch):
    async def final(*args,**kwargs):return final_message('你好')
    monkeypatch.setattr(module.ai_planner,'tool_turn',final)
    result=client.post('/api/agent/runs',json={'request_id':'private-route-owner','message':'你好'}).json()
    with module.connection() as db:
        other=module.auth.new_user(db.conn,email='other-routing@example.test')
        token=module.auth.create_session(db.conn,other,'test')['access_token']
    original=client.headers['Authorization'];client.headers['Authorization']='Bearer '+token
    try:assert client.get('/api/agent/runs/'+result['run_id']).status_code==404
    finally:client.headers['Authorization']=original
