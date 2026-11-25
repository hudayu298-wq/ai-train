"""Knowledge provenance, immutable publication gates and live native-tool contracts."""
import asyncio
import copy
import json
from uuid import uuid4
import pytest
from sqlalchemy import delete
from pydantic import ValidationError

from test_app import module, client, isolate_records
from services import knowledge_store as kb, knowledge_evaluation as evaluation, research_store as store, prompt_registry, retrieval_benchmark, knowledge_retrieval
from knowledge_models import Bundle


@pytest.fixture(autouse=True)
def clear_knowledge(isolate_records):
    with module.connection() as db:
        db.conn.execute(delete(module.database.research_records))
    yield
    with module.connection() as db:
        db.conn.execute(delete(module.database.research_records))


def new_bundle():
    bundle=copy.deepcopy(kb.bundled())
    bundle['version']='foundation-test-v2'
    return bundle


def test_evaluation_prompt_preserves_facts_scope_and_actual_citations_without_graph_duplicates():
    with module.connection() as db:
        retrieved=kb.retrieve(db,'股直肌',mode='bm25',limit=5)
    compact=evaluation.evidence_for_prompt(retrieved)
    assert [i['facts'] for i in compact['items']]==[i['facts'] for i in retrieved['items']]
    assert [i['population'] for i in compact['items']]==[i['population'] for i in retrieved['items']]
    assert [i['limitations'] for i in compact['items']]==[i['limitations'] for i in retrieved['items']]
    assert [c['id'] for c in compact['citations']]==[c['id'] for c in retrieved['citations']]
    assert len(json.dumps(compact,ensure_ascii=False))<len(json.dumps(retrieved,ensure_ascii=False))
    assert 'relations' not in compact and 'related_items' not in compact


def test_answer_transport_metadata_never_normalizes_answers_or_unknown_fields():
    item={'case_id':'example','selected':['b'],'abstain':False,'citations':['kb:example:actual']}
    parsed,changed=evaluation.parse_answers({'type':'json_object','items':[item]})
    assert changed and parsed.items[0].model_dump()==item
    assert not evaluation.parse_answers({'items':[item]})[1]
    for raw in [{'type':'other','items':[item]}, {'type':'json_object','items':[item],'extra':True},
                {'items':[{**item,'abstain':'false'}]}, {'items':[{**item,'extra':True}]}]:
        with pytest.raises(ValidationError):evaluation.parse_answers(raw)


def test_qa_reuses_only_valid_retrieval_and_still_runs_both_model_conditions(monkeypatch):
    case={'id':'one','query':'股直肌','question':'股直肌的附着信息？','options':{'a':'示例事实'},
        'expected':['a'],'abstain':False,'support_ids':['rectus_femoris'],'category':'unit','critical':True}
    bundle=kb.latest();prior=retrieval_report_for(bundle);calls=[]
    unknown={'id':'unknown','query':'未知个体测量','question':'未提供的个人测量是多少？','options':{'a':'任意数值'},
        'expected':[],'abstain':True,'support_ids':[],'category':'unit','critical':True}
    monkeypatch.setattr(evaluation,'cases',lambda:[case,unknown])
    def forbidden(*args,**kwargs):raise AssertionError('valid unchanged retrieval must not be replayed')
    monkeypatch.setattr(retrieval_benchmark,'evaluate',forbidden)
    async def fake(messages,**kwargs):
        assert 'json' in messages[0]['content'].lower() # Provider JSON-mode contract.
        data=json.loads(messages[-1]['content']);calls.append('knowledge' in data)
        cited=[]
        if 'knowledge' in data:
            cited=[next(c['id'] for c in data['knowledge']['one']['citations'] if c['item_id']=='rectus_femoris')]
        return {'items':[{'case_id':'one','selected':['a'],'abstain':False,'citations':cited},
            {'case_id':'unknown','selected':[],'abstain':True,'citations':[]}]},'unit-model'
    monkeypatch.setattr(module.ai_planner,'chat_json',fake)
    result=asyncio.run(evaluation.evaluate(module.connection,bundle,retrieval_report=prior))
    assert calls==[False,True] and result['retrieval_evaluation_reused']
    assert result['retrieval_evaluation'] is prior and result['variants']['with_knowledge']['correct']==2


def test_seed_source_graph_and_precise_anatomy():
    bundle=Bundle.model_validate(kb.bundled())
    assert len(bundle.items)==53
    nodes={i.id:i for i in bundle.items}
    assert nodes['rectus_femoris'].facts['joint_ids']==['hip','knee']
    assert '髂前下棘' in nodes['rectus_femoris'].facts['origin'][0]
    assert nodes['biceps_femoris_short'].facts['joint_ids']==['knee']
    assert nodes['soleus'].facts['joint_ids']==['ankle']
    assert nodes['guide_deadlift'].facts['exercise_id']=='deadlift'
    assert nodes['guide_romanian_deadlift'].facts['exercise_id']=='romanian_deadlift'
    for mutate in (
        lambda b: b['relations'].pop(),
        lambda b: b['items'][0]['facts'].update(joint_id='absent'),
        lambda b: b['items'][0]['facts'].update(joint_id=True),
        lambda b: b['items'][0]['references'][0].update(source_id='absent'),
    ):
        bad=copy.deepcopy(kb.bundled());mutate(bad)
        with pytest.raises(ValidationError): Bundle.model_validate(bad)


def test_retrieval_entity_disambiguation_and_relation_navigation():
    response=client.get('/api/knowledge').json()
    assert sum(response['counts'].values())==53
    for text,key in [('股二头肌短头','biceps_femoris_short'),('比目鱼肌','soleus'),('罗马尼亚硬拉','guide_romanian_deadlift')]:
        result=client.get('/api/knowledge/search',params={'q':text}).json()
        assert result['items'][0]['id']==key
    result=client.get('/api/knowledge/items/rectus_femoris').json()
    assert {'hip','knee'}.issubset({i['id'] for i in result['related_items']})
    assert result['citations'][0]['sources'][0]['locator']=='rectus femoris'
    guides=client.get('/api/knowledge/search',params={'exercise_id':'bench'}).json()['items']
    assert [g['id'] for g in guides]==['guide_bench']


def test_import_immutable_and_authorization():
    bundle=new_bundle()
    assert client.post('/api/knowledge/bundles',json=bundle).status_code==200
    assert client.post('/api/knowledge/bundles',json=bundle).status_code==409
    bad=new_bundle();bad['version']='bad-exercise-v1'
    next(i for i in bad['items'] if i['id']=='guide_bench')['exercise_ids']=['not_a_catalog_id']
    assert client.post('/api/knowledge/bundles',json=bad).status_code==422
    with module.connection() as db:
        user=module.auth.new_user(db.conn,email='reader-knowledge@example.com')
        token=module.auth.create_session(db.conn,user,'test')['access_token']
    original=client.headers['Authorization']
    client.headers['Authorization']='Bearer '+token
    try:
        assert client.get('/api/knowledge').status_code==200
        assert client.get('/api/knowledge/admin').status_code==403
        assert client.post('/api/knowledge/bundles',json=new_bundle()).status_code==403
        assert client.post('/api/knowledge/withdrawals',json={'target_type':'source','target_id':'uams-lower','notes':'未经授权不能停用公共知识来源'}).status_code==403
    finally: client.headers['Authorization']=original


def test_withdrawal_filters_graph_and_pinned_retrieval():
    with module.connection() as db:
        pinned=kb.active(db)
        before=kb.revision(db)
    response=client.post('/api/knowledge/withdrawals',json={'target_type':'source','target_id':'uams-lower','notes':'测试来源存在疑问，需要停用所有相关知识'} )
    assert response.status_code==200
    assert client.get('/api/knowledge/items/rectus_femoris').status_code==404
    with module.connection() as db:
        assert not kb.valid_citation(db,pinned,'kb:'+pinned['version']+':rectus_femoris')
        result=kb.retrieve(db,'股直肌',bundle=pinned)
        assert not any(i['id']=='rectus_femoris' for i in result['items'])
        assert not any(r['target']=='rectus_femoris' or r['source']=='rectus_femoris' for r in result['relations'])
        assert kb.revision(db)!=before


def report_for(bundle):
    bundle=Bundle.model_validate(bundle).model_dump()
    return {'version':bundle['version'],'fingerprint':kb.fingerprint(bundle),'suite_hash':evaluation.suite_hash(),
        'runtime_fingerprint':prompt_registry.runtime_fingerprint(),'configured_model':module.ai_planner.settings()['AI_MODEL'],
        'withdrawals':[],'passed':True,'retrieval_evaluation':retrieval_report_for(bundle)}


def retrieval_report_for(bundle):
    """Synthetic trusted-worker report for publication binding unit tests only."""
    return {'version':bundle['version'],'fingerprint':kb.fingerprint(bundle),
        'suite_hash':retrieval_benchmark.suite_hash(),'dataset_hash':retrieval_benchmark.suite_hash(),
        'pipeline_fingerprint':knowledge_retrieval.fingerprint(),'model_versions':copy.deepcopy(knowledge_retrieval.neural.MANIFEST),
        'gate_policy':copy.deepcopy(retrieval_benchmark.GATE_POLICY),'primary_split':'test','withdrawals':[],
        'gates':dict.fromkeys(retrieval_benchmark.GATE_NAMES,True),'passed':True}


def test_publication_requires_review_matching_eval_and_supports_rollback():
    bundle=new_bundle();version=bundle['version']
    client.post('/api/knowledge/bundles',json=bundle)
    assert client.post(f'/api/knowledge/bundles/{version}/activate',json={'evaluation_id':'invented'}).status_code==409
    assert client.post(f'/api/knowledge/bundles/{version}/review',json={'notes':'已按标注来源核对结构、适用范围和关联关系'}).status_code==200
    with module.connection() as db:
        report=report_for(bundle)
        store.put(db,'kb_evaluation','test-report',report,'passed')
    assert client.post(f'/api/knowledge/bundles/{version}/activate',json={'evaluation_id':'test-report'}).status_code==200
    assert client.get('/api/knowledge').json()['version']==version
    assert client.post(f'/api/knowledge/bundles/{version}/rollback',json={}).status_code==200
    assert client.get('/api/knowledge').json()['version']==kb.bundled()['version']
    assert client.post(f'/api/knowledge/bundles/{version}/rollback',json={}).status_code==409


@pytest.mark.parametrize('field,value',[('suite_hash','stale'),('runtime_fingerprint','stale'),('configured_model','different'),('withdrawals',['source:uams-lower'])])
def test_stale_evaluations_cannot_publish(field,value):
    bundle=new_bundle();version=bundle['version']
    client.post('/api/knowledge/bundles',json=bundle)
    client.post(f'/api/knowledge/bundles/{version}/review',json={'notes':'已人工核对来源与范围，用于验证发布校验'} )
    with module.connection() as db:
        report=report_for(bundle);report[field]=value
        store.put(db,'kb_evaluation','stale-report',report,'passed')
    assert client.post(f'/api/knowledge/bundles/{version}/activate',json={'evaluation_id':'stale-report'}).status_code==409


def test_native_agent_reads_pinned_knowledge_and_rejects_fabricated_citation(monkeypatch):
    calls=[]
    async def fake(messages,tools,max_tokens):
        names={t['function']['name'] for t in tools}
        assert {'search_knowledge','get_knowledge_item'}.issubset(names)
        tool_result=next((m for m in reversed(messages) if m['role']=='tool'),None)
        calls.append(messages)
        if not tool_result:
            return {'model':'test','message':{'role':'assistant','content':None,'tool_calls':[{'id':'knowledge-call',
                'type':'function','function':{'name':'search_knowledge','arguments':json.dumps({'query':'股直肌 起点'})}}]}}
        result=json.loads(tool_result['content']);citation=result['citations'][0]['id']
        return {'model':'test','message':{'role':'assistant','content':json.dumps({'reply':'股直肌主要起于髂前下棘等；这是简化解剖资料。','profile_updates':[],
            'citations':[citation if len(calls)<4 else 'kb:fake:invented']})}}
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    body={'request_id':'knowledge-agent-0001','message':'股直肌起点在哪？'}
    response=client.post('/api/agent/runs',json=body).json()
    assert response['status']=='completed' and response['citations'][0]['item_id']=='rectus_femoris'
    assert response['versions']['foundation']==kb.bundled()['version']
    second=client.post('/api/agent/runs',json={**body,'request_id':'knowledge-agent-0002'}).json()
    assert second['status']=='failed'


def test_frozen_benchmark_has_no_prompt_labels_and_compares_same_questions(monkeypatch):
    monkeypatch.setenv('KNOWLEDGE_RETRIEVAL_MODE','bm25')
    monkeypatch.setattr(retrieval_benchmark,'evaluate',lambda connection,bundle:retrieval_report_for(bundle))
    seen=[]
    labels={c['id']:c for c in evaluation.cases()}
    async def fake(messages,max_tokens):
        payload=json.loads(messages[-1]['content'])
        seen.append(payload)
        assert not any('expected' in q or 'support_ids' in q or 'critical' in q for q in payload['questions'])
        answers=[]
        for question in payload['questions']:
            case=labels[question['id']]
            retrieved=payload.get('knowledge',{}).get(case['id'],{})
            citations=[c['id'] for c in retrieved.get('citations',[]) if c['item_id'] in case['support_ids']][:1]
            answers.append({'case_id':case['id'],'selected':case['expected'],'abstain':case['abstain'],'citations':citations})
        return {'items':answers},'test-model'
    monkeypatch.setattr(module.ai_planner,'chat_json',fake)
    report=asyncio.run(evaluation.evaluate(module.connection,kb.latest()))
    count=len(evaluation.cases())
    assert report['passed'] and report['variants']['with_knowledge']['correct']==count
    assert report['variants']['model_only']['correct']==count and report['improvements']==[]
    assert len(seen)==2*((count+5)//6)
    for i in range(0,len(seen),2): assert seen[i]['questions']==seen[i+1]['questions']
    case=labels['soleus-knee']
    with module.connection() as db: result=kb.retrieve(db,'比目鱼肌')
    wrong={'case_id':case['id'],'selected':['b'],'abstain':False,'citations':['kb:fake:soleus']}
    assert evaluation.grade(case,wrong,result,True)['citation_valid'] is False


def test_agent_repairs_citation_without_repeating_tools_or_writing(monkeypatch):
    attempts=[]
    async def fake(messages,tools,max_tokens):
        attempts.append(len(messages))
        if len(attempts)==1:
            return {'model':'test','message':{'role':'assistant','content':None,'tool_calls':[{'id':'repair-knowledge-call',
                'type':'function','function':{'name':'search_knowledge','arguments':json.dumps({'query':'股直肌'})}}]}}
        cite='uams-lower' if len(attempts)==2 else 'kb:'+kb.bundled()['version']+':rectus_femoris'
        return {'model':'test','message':{'role':'assistant','content':json.dumps({'reply':'股直肌起于髂前下棘等。','profile_updates':[],'citations':[cite]})}}
    monkeypatch.setattr(module.ai_planner,'tool_turn',fake)
    response=client.post('/api/agent/runs',json={'request_id':'knowledge-repair-0001','message':'股直肌起点？'}).json()
    assert response['status']=='completed' and len(attempts)==3
    with module.connection() as db:
        run=db.read('agent_run',response['run_id'])
        assert sum(s['type']=='tool' for s in run['steps'])==1
        assert any(s.get('reason')=='invalid_citation_ids' for s in run['steps'])
        assert db.records('agent_action')==[]


def test_knowledge_jobs_share_evaluation_budget():
    version=kb.bundled()['version']
    assert client.post(f'/api/knowledge/bundles/{version}/evaluate',json={}).status_code==200
    assert client.post(f'/api/knowledge/bundles/{version}/evaluate',json={}).status_code==200
    assert client.post(f'/api/knowledge/bundles/{version}/evaluate',json={}).status_code==429
