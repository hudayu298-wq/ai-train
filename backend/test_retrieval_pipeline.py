"""Index isolation, withdrawal and explicit failure contracts; no model API calls."""
import copy

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from test_app import module, isolate_records
from services import knowledge_store as kb, knowledge_retrieval as retrieval, research_store as store


def test_rerank_fusion_retains_secondary_evidence_and_rejects_uniformly_unsupported():
    candidates=[{'id':str(i),'score':1/(60+i)} for i in range(8)]
    scores=[.9,.02,.03,.01,.5,.4,.3,.2]
    ranked=sorted(retrieval.fuse_rerank(copy.deepcopy(candidates),scores,set()),key=lambda p:-p['score'])[:5]
    assert '1' in [p['id'] for p in ranked]
    assert retrieval.fuse_rerank(copy.deepcopy(candidates),[.001]*8,set())==[]
    assert retrieval.fuse_rerank(copy.deepcopy(candidates),[.001]*8,{'0'})


def test_question_facets_keep_entity_lists_and_bound_independent_sentences():
    assert retrieval.question_parts('动作甲、动作乙的作用有什么区别？')==[]
    assert retrieval.question_parts('先说明前一个动作的作用？再说明测量记录的限制是什么？')==['先说明前一个动作的作用','再说明测量记录的限制是什么']
    assert len(retrieval.question_parts('一个完整的问题；另一个完整的问题；第三个完整的问题；第四个完整的问题'))==3
    docs=[{'item_id':'a','chunk_key':'a:1'},{'item_id':'a','chunk_key':'a:2'},
        {'item_id':'b','chunk_key':'b:1'},{'item_id':'c','chunk_key':'c:1'}]
    assert retrieval.dense_evidence(docs,[.9,.8,.7,.2],2)==['a','b']


def test_reranker_length_batches_restore_original_score_order(monkeypatch):
    import numpy as np
    passages=['x'*n for n in [10,1,9,2,8,3]]
    seen=[]
    def fake(component,pairs):
        seen.extend(len(p) for _,p in pairs)
        return np.array([[len(p)/10] for _,p in pairs]),np
    monkeypatch.setattr(retrieval.neural,'_run',fake)
    scores=retrieval.neural.rerank('query',passages)
    assert seen==sorted(map(len,passages))
    assert np.allclose(scores,[1/(1+np.exp(-len(p)/10)) for p in passages])


@pytest.fixture
def public_index(isolate_records):
    with module.connection() as db:
        db.conn.execute(delete(module.database.knowledge_chunks))
        db.conn.execute(delete(module.database.research_records))
    yield
    with module.connection() as db:
        db.conn.execute(delete(module.database.knowledge_chunks))
        db.conn.execute(delete(module.database.research_records))


def test_index_reuses_vectors_and_scopes_corpus_version(public_index, monkeypatch):
    calls=[]
    def embed(texts, **kwargs):
        calls.extend(texts)
        return [[1.0, 0.0] for _ in texts]
    monkeypatch.setattr(retrieval.neural, 'embed', embed)
    bundle=copy.deepcopy(kb.bundled())
    documents=retrieval.chunks(bundle)[:2]
    with module.connection() as db:
        first,_=retrieval.index(db,bundle,documents)
        again,_=retrieval.index(db,bundle,documents)
        assert [r['id'] for r in first]==[r['id'] for r in again]
        assert len(calls)==2
        bundle['version']='independent-corpus-v2'
        changed,_=retrieval.index(db,bundle,documents)
        assert set(r['id'] for r in first).isdisjoint(r['id'] for r in changed)
        assert db.conn.execute(select(module.database.knowledge_chunks.c.id)).all().__len__()==4


def test_withdrawal_precedes_neural_scoring(public_index, monkeypatch):
    captured=[]
    def dense(db, query, documents, bundle):
        captured.extend(c['item_id'] for c in documents)
        return [0.7]*len(documents), 'test_exact'
    monkeypatch.setattr(retrieval,'dense_scores',dense)
    monkeypatch.setattr(retrieval.neural,'rerank',lambda query, passages:[0.8]*len(passages))
    with module.connection() as db:
        store.put(db,'kb_withdrawal','test-source',{'target':'source:uams-lower'},'withdrawn')
        result=kb.retrieve(db,'股直肌起点',mode='hybrid_rerank')
    assert captured and 'rectus_femoris' not in captured
    assert not any(i['id']=='rectus_femoris' for i in result['items'])
    assert not any(r['target']=='rectus_femoris' or r['source']=='rectus_femoris' for r in result['relations'])


def test_fallback_is_explicit_and_database_failure_is_not_swallowed(public_index, monkeypatch):
    def unavailable(*args, **kwargs):
        raise RuntimeError('private runtime details must not be returned')
    monkeypatch.setattr(retrieval,'dense_scores',unavailable)
    with module.connection() as db:
        result=kb.retrieve(db,'比目鱼肌',mode='hybrid_rerank')
    assert result['retrieval']['effective_mode']=='bm25'
    assert result['retrieval']['fallback_reason']=='RuntimeError'
    assert result['retrieval']['embedding_model'] is None
    assert 'private runtime' not in str(result)
    def db_failure(*args, **kwargs):
        raise OperationalError('sql',{},Exception('database error'))
    monkeypatch.setattr(retrieval,'dense_scores',db_failure)
    with module.connection() as db, pytest.raises(OperationalError):
        kb.retrieve(db,'比目鱼肌',mode='hybrid_rerank')
