"""Frozen labels, actual pipeline diagnostics and publication/worker contracts."""
import asyncio
import copy
from collections import Counter

import pytest

from test_app import module, client, isolate_records
from test_knowledge import clear_knowledge, new_bundle, report_for, retrieval_report_for
from services import (knowledge_store as kb, knowledge_retrieval as retrieval,
    retrieval_benchmark as benchmark, research_store as store, research_worker)


def test_frozen_retrieval_dataset_covers_real_nodes_and_distinct_holdout():
    frozen=benchmark.dataset()
    assert Counter(c['split'] for c in frozen['cases'])=={'dev':20,'test':60}
    ids={i['id'] for i in kb.latest()['items']}
    assert all(set(c['relevance'])<=ids for c in frozen['cases'])
    assert all(not c.get('expected') and not c.get('answer') for c in frozen['cases'])
    assert len({c['query'] for c in frozen['cases']})==80
    assert sum(c.get('expected_abstain',False) for c in frozen['cases'] if c['split']=='test')==3


def test_retrieval_metrics_reject_duplicates_missing_required_and_withdrawals():
    case={'id':'pair','split':'test','category':'comparison','relevance':{'a':2,'b':1},
        'required_ids':['a','b'],'critical':True}
    result=benchmark.grade(case,['x','a','a'])
    assert result['recall_at_5']==.5 and result['mrr']==.5
    assert not result['required_complete']
    assert 0<result['ndcg_at_5']<1
    result=benchmark.grade(case,['a','b'],withdrawn_ids=['b'])
    assert result['recall_at_5']==1 and result['withdrawn_label_ids']==['b']
    assert result['withdrawn_result_ids']==['b'] and not result['required_complete']
    unsupported={**case,'relevance':{},'required_ids':[],'expected_abstain':True}
    assert benchmark.grade(unsupported,[])['abstention_correct']
    assert not benchmark.grade(unsupported,['a'])['abstention_correct']


def test_neural_fallback_cannot_pass_as_actual_requested_pipeline():
    models=retrieval.neural.MANIFEST
    row={'effective_mode':'hybrid_rerank','pipeline_fingerprint':retrieval.fingerprint(),
        'embedding_model':models['embedding']['id'],'reranker_model':models['reranker']['id'],
        'vector_backend':'exact_dense_json','fallback_reason':None}
    assert benchmark._actual_mode(row,'hybrid_rerank',models,retrieval.fingerprint())
    for mutation in ({'effective_mode':'bm25'},{'fallback_reason':'RuntimeError'},
            {'reranker_model':None},{'embedding_model':'other'},{'pipeline_fingerprint':'stale'},
            {'error':'RuntimeError'},{'vector_backend':None}):
        assert not benchmark._actual_mode({**row,**mutation},'hybrid_rerank',models,retrieval.fingerprint())


@pytest.mark.parametrize('field,value',[
    ('pipeline_fingerprint','stale'),('suite_hash','stale'),('dataset_hash','stale'),
    ('model_versions',{}),('fingerprint','stale'),('version','stale'),
    ('gate_policy',{}),('withdrawals',['item:soleus']),('primary_split','dev'),
    ('gates',{}),('passed',False),
])
def test_retrieval_report_is_bound_to_policy_models_corpus_dataset_and_withdrawals(field,value):
    bundle=kb.latest()
    report=retrieval_report_for(bundle)
    assert benchmark.valid_report(report,bundle,[])
    assert not benchmark.valid_report({**report,field:value},bundle,[])


def test_builtin_candidate_is_frozen_reviewed_before_benchmark_and_never_auto_activated():
    baseline=client.get('/api/knowledge').json()['version']
    response=client.post('/api/knowledge/builtin-candidate',json={})
    assert response.status_code==200
    version=response.json()['bundle']['version']
    assert version!=baseline and client.get('/api/knowledge').json()['version']==baseline
    assert client.post(f'/api/knowledge/bundles/{version}/retrieval-evaluate',json={}).status_code==409
    assert client.post(f'/api/knowledge/bundles/{version}/review',json={'notes':'按来源检查知识适用范围，需实际检索和回答评测通过才发布。'}).status_code==200
    queued=client.post(f'/api/knowledge/bundles/{version}/retrieval-evaluate',json={})
    assert queued.status_code==200 and queued.json()['job_type']=='retrieval_evaluation'
    assert queued.json()['input']['pipeline_fingerprint']==retrieval.fingerprint()
    assert client.get('/api/knowledge').json()['version']==baseline


@pytest.mark.parametrize('invalid_retrieval',[None,{'passed':True}])
def test_qa_pass_without_bound_retrieval_report_cannot_publish(invalid_retrieval):
    bundle=new_bundle(); version=bundle['version']
    assert client.post('/api/knowledge/bundles',json=bundle).status_code==200
    client.post(f'/api/knowledge/bundles/{version}/review',json={'notes':'人工来源审查通过，但检索报告缺失不得发布。'})
    report=report_for(bundle);report['retrieval_evaluation']=invalid_retrieval
    with module.connection() as db: store.put(db,'kb_evaluation','qa-only',report,'passed')
    assert client.post(f'/api/knowledge/bundles/{version}/activate',json={'evaluation_id':'qa-only'}).status_code==409


def test_retrieval_jobs_share_daily_full_evaluation_budget():
    version=kb.bundled()['version']
    assert client.post(f'/api/knowledge/bundles/{version}/retrieval-evaluate',json={}).status_code==200
    assert client.post(f'/api/knowledge/bundles/{version}/evaluate',json={}).status_code==200
    assert client.post(f'/api/knowledge/bundles/{version}/retrieval-evaluate',json={}).status_code==429


def test_qa_can_select_only_a_still_bound_passed_retrieval_report():
    bundle=new_bundle();version=bundle['version']
    assert client.post('/api/knowledge/bundles',json=bundle).status_code==200
    assert client.post(f'/api/knowledge/bundles/{version}/review',json={'notes':'来源与适用范围已核对，复用检索必须保持全部原绑定。'}).status_code==200
    with module.connection() as db:
        store.put(db,'kb_retrieval_eval','prior-real-pipeline',report_for(bundle)['retrieval_evaluation'],'passed')
    path=f'/api/knowledge/bundles/{version}/evaluate?retrieval_evaluation_id=prior-real-pipeline'
    queued=client.post(path,json={})
    assert queued.status_code==200 and queued.json()['input']['retrieval_evaluation_id']=='prior-real-pipeline'
    with module.connection() as db:
        prior=store.get(db,'kb_retrieval_eval','prior-real-pipeline')
        store.put(db,'kb_retrieval_eval','prior-real-pipeline',{**prior,'pipeline_fingerprint':'stale'},'passed')
    assert client.post(path,json={}).status_code==409


def test_qa_reuse_rejects_stale_report_before_any_model_request(monkeypatch):
    from services import knowledge_evaluation
    bundle=kb.latest();report=retrieval_report_for(bundle)
    report['withdrawals']=['item:withdrawn']
    async def forbidden(*args,**kwargs):raise AssertionError('must reject before model call')
    monkeypatch.setattr(module.ai_planner,'chat_json',forbidden)
    with pytest.raises(ValueError):
        asyncio.run(knowledge_evaluation.evaluate(module.connection,bundle,retrieval_report=report))


def test_retrieval_worker_persists_failed_report_without_publishing(monkeypatch):
    version=kb.bundled()['version']
    def fake(connection,bundle):
        return {**retrieval_report_for(bundle),'passed':False,'gates':{'not_worse_than_bm25':False}}
    monkeypatch.setattr(benchmark,'evaluate',fake)
    queued=client.post(f'/api/knowledge/bundles/{version}/retrieval-evaluate',json={}).json()
    assert asyncio.run(research_worker.run_once(module.connection))['status']=='completed'
    with module.connection() as db:
        job=store.get(db,'job',queued['id'])
        report=store.get(db,'kb_retrieval_eval',job['result']['evaluation_id'])
        assert report['status']=='failed' and job['result']['passed'] is False
        assert kb.active(db)['version']==version


def test_index_worker_filters_withdrawn_nodes_and_reports_real_backend(monkeypatch):
    captured=[]
    def fake(db,bundle,documents):
        captured.extend(documents)
        return documents,False
    monkeypatch.setattr(retrieval,'index',fake)
    client.post('/api/knowledge/withdrawals',json={'target_type':'item','target_id':'soleus',
        'notes':'测试撤回的节点不得重新写入索引。'})
    queued=client.post('/api/knowledge/index',json={}).json()
    assert asyncio.run(research_worker.run_once(module.connection))['status']=='completed'
    assert captured and not any(c['item_id']=='soleus' for c in captured)
    with module.connection() as db:
        result=store.get(db,'job',queued['id'])['result']
        assert result['vector_backend']=='exact_dense_json' and result['chunks']==len(captured)


def test_worker_rejects_stale_model_or_policy_before_inference(monkeypatch):
    called=[]
    monkeypatch.setattr(retrieval,'index',lambda *args:called.append(args))
    queued=client.post('/api/knowledge/index',json={}).json()
    with module.connection() as db:
        job=store.get(db,'job',queued['id']);job['input']['pipeline_fingerprint']='stale'
        store.put(db,'job',job['id'],job,'queued')
    assert asyncio.run(research_worker.run_once(module.connection))['status']=='failed'
    assert not called


def test_admin_list_reports_keep_metrics_and_details_are_separately_authorized():
    value={**retrieval_report_for(kb.latest()),'variants':{'hybrid_rerank':{
        'test':{'recall_at_5':.9,'latency_ms':{'p50':12}},
        'cases':[{'case_id':'full-audit-row','returned_ids':['soleus']}]}},
        'paired_regressions':{'hybrid_rerank':[{'regression':True}]}}
    with module.connection() as db:
        store.put(db,'kb_retrieval_eval','report-details',value,'passed')
    listed=client.get('/api/knowledge/admin').json()['retrieval_evaluations'][0]
    assert 'cases' not in listed['variants']['hybrid_rerank']
    assert listed['variants']['hybrid_rerank']['test']['recall_at_5']==.9
    assert listed['paired_regression_counts']['hybrid_rerank']==1
    assert client.get('/api/knowledge/retrieval-evaluations/report-details').json()['variants']['hybrid_rerank']['cases']
    with module.connection() as db:
        user=module.auth.new_user(db.conn,email='retrieval-reader@example.com')
        token=module.auth.create_session(db.conn,user,'test')['access_token']
    original=client.headers['Authorization'];client.headers['Authorization']='Bearer '+token
    try:
        assert client.get('/api/knowledge/retrieval-evaluations/report-details').status_code==403
        assert client.get('/api/knowledge/evaluations/report-details').status_code==403
    finally:
        client.headers['Authorization']=original
