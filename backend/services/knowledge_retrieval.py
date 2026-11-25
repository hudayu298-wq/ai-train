"""Evidence-scoped BM25 + dense retrieval, reciprocal rank fusion and reranking.

Ranking is independently testable. Relevance scores are retrieval heuristics,
never fitness safety thresholds or measures of scientific truth.
"""
import hashlib
import json
import math
import os
import re
import time
from pathlib import Path
from collections import Counter
from threading import RLock
from sqlalchemy import select,text
try:
    from .. import database as d
    from . import research_store as store,retrieval_inference as neural
except ImportError:
    import database as d
    from services import research_store as store,retrieval_inference as neural

POLICY={'version':'hybrid-retrieval-20261028-v3','candidate_items':16,'rrf_k':60,'min_rerank_score':0.08,
    'rerank_fusion':'equal_rrf_query_relevance_gate',
    'question_facets':{'max_parts':3,'minimum_chars':6,'dense_evidence_per_part':2},
    'max_chunk_chars':400,'query_max_chars':400,'default_mode':'hybrid_rerank'}
_INDEX_LOCK=RLock()


def fingerprint():
    paths=[Path(__file__),Path(neural.__file__),Path(__file__).with_name('knowledge_store.py')]
    return store.fingerprint({'policy':POLICY,'models':neural.MANIFEST,
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})


def terms(value):
    result=re.findall(r'[a-zA-Z0-9_]{2,}',value.lower())
    for run in re.findall(r'[\u4e00-\u9fff]+',value):
        result.extend(c for c in run if c not in '的是了与和在于为将把及或')
        result.extend(run[i:i+2] for i in range(len(run)-1))
    return result


LABELS={'origin':'起点 近端附着','insertion':'止点 远端附着','joint_ids':'跨越关节','action_ids':'关节作用',
    'primary_muscle_ids':'主要训练肌肉','assisting_muscle_ids':'协同肌肉','stabilizer_muscle_ids':'稳定肌肉',
    'joint_id':'关节','recommendations':'建议与条件','principle':'原则','camera_views':'拍摄机位',
    'not_observable':'不能从录像判断','phase_notes':'动作阶段说明','landmark_ids':'骨性标志'}


def chunks(bundle):
    nodes={i['id']:i for i in bundle['items']}
    result=[]
    for item in bundle['items']:
        header=item['title']+' '+' '.join(item['aliases'])
        sections=[('summary',item['summary']),('scope','适用人群：'+'；'.join(item['population'])+'。局限：'+'；'.join(item['limitations']))]
        for key,value in item['facts'].items():
            if key in ('governing_service','exercise_id'):
                continue
            values=value if isinstance(value,list) else [str(value)]
            rendered='；'.join(nodes.get(v,{}).get('title',str(v)) for v in values)
            sections.append((key,LABELS.get(key,key)+'：'+rendered))
        # Small complete cards stay together; longer cards retain fact boundaries.
        content=header+'\n'+'\n'.join(v for _,v in sections)
        groups=[('card',content)] if len(content)<=750 else [(key,header+'\n'+value) for key,value in sections]
        for key,value in groups:
            for offset in range(0,len(value),POLICY['max_chunk_chars']):
                passage=value[offset:offset+POLICY['max_chunk_chars']]
                if offset:
                    passage=header+'\n'+passage
                chunk_key=item['id']+':'+key+':'+str(offset)
                content_hash=hashlib.sha256(passage.encode()).hexdigest()
                result.append({'chunk_key':chunk_key,'item_id':item['id'],'content':passage,
                    'content_hash':content_hash,'references':item['references'],'kind':item['kind']})
    return result


def bm25(query,documents):
    query_counts=Counter(terms(query))
    docs=[Counter(terms(c['content'])) for c in documents]
    lengths=[sum(c.values()) for c in docs]
    avg=sum(lengths)/max(len(lengths),1)
    df=Counter(term for doc in docs for term in doc)
    scores=[]
    for i,doc in enumerate(docs):
        value=0.0
        for term,qf in query_counts.items():
            tf=doc.get(term,0)
            if not tf:
                continue
            idf=math.log(1+(len(docs)-df[term]+.5)/(df[term]+.5))
            value+=idf*tf*2.2/(tf+1.2*(.25+.75*lengths[i]/max(avg,1)))*min(qf,2)
        scores.append(value)
    return scores


def _vector_column(db):
    return db.conn.dialect.name=='postgresql' and bool(db.conn.execute(text(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='knowledge_chunks' AND column_name='embedding_vector')")).scalar())


def index(db,bundle,documents):
    bundle_hash=store.fingerprint(bundle)
    model_hash=neural.model_hash()
    query=select(d.knowledge_chunks).where(d.knowledge_chunks.c.bundle_hash==bundle_hash,d.knowledge_chunks.c.model_hash==model_hash)
    with _INDEX_LOCK:
        rows={r['chunk_key']:dict(r) for r in db.conn.execute(query).mappings()}
        missing=[c for c in documents if c['chunk_key'] not in rows or rows[c['chunk_key']]['content_hash']!=c['content_hash']]
        vectors=neural.embed([c['content'] for c in missing])
        has_vector=_vector_column(db)
        for c,vector in zip(missing,vectors,strict=True):
            key=store.fingerprint([bundle_hash,model_hash,c['chunk_key'],c['content_hash']])
            row={'id':key,'bundle_hash':bundle_hash,'model_hash':model_hash,'item_id':c['item_id'],'chunk_key':c['chunk_key'],
                'content':c['content'],'content_hash':c['content_hash'],'embedding':vector,'payload':{'references':c['references'],'kind':c['kind']}}
            stmt=d.dialect_insert(db.conn,d.knowledge_chunks).values(**row)
            db.conn.execute(stmt.on_conflict_do_nothing(index_elements=['id']))
            rows[c['chunk_key']]=row
        if has_vector:
            db.conn.execute(text('UPDATE knowledge_chunks SET embedding_vector=CAST(embedding::text AS vector) '
                'WHERE bundle_hash=:bundle AND model_hash=:model AND embedding_vector IS NULL'),{'bundle':bundle_hash,'model':model_hash})
    return [rows[c['chunk_key']] for c in documents],has_vector


def dense_scores(db,query,documents,bundle):
    rows,has_vector=index(db,bundle,documents)
    vector=neural.embed([query],query=True)[0]
    if has_vector:
        # Scope by immutable corpus/model and eligible IDs BEFORE nearest-neighbour scoring.
        values=db.conn.execute(text('SELECT id,1-(embedding_vector <=> CAST(:query AS vector)) AS score FROM knowledge_chunks '
            'WHERE bundle_hash=:bundle AND model_hash=:model AND id=ANY(:ids)'),
            {'query':json.dumps(vector),'bundle':store.fingerprint(bundle),'model':neural.model_hash(),'ids':[r['id'] for r in rows]}).mappings()
        scores={r['id']:float(r['score']) for r in values}
        return [scores.get(r['id'],-1) for r in rows],'pgvector_exact'
    import numpy as np
    matrix=np.asarray([r['embedding'] for r in rows],dtype=np.float32)
    return (matrix@np.asarray(vector,dtype=np.float32)).tolist(),'exact_dense_json'


def fuse_rerank(candidates, relevance, exact):
    """Retain secondary evidence for compound questions without label-aware boosts.

    A cross encoder scores an entire question, so a card answering only one clause
    may have a low absolute score despite strong lexical/semantic recall. Use its
    rank alongside the original retrieval rank. The relevance gate applies to the
    question as a whole; uniformly unsupported candidates still produce no result.
    """
    if not relevance or max(relevance) < POLICY['min_rerank_score'] and not exact:
        return []
    reranked = sorted(range(len(candidates)), key=lambda i:(-relevance[i], candidates[i]['id']))
    positions = {i:rank for rank,i in enumerate(reranked,1)}
    for i,(entry,value) in enumerate(zip(candidates,relevance,strict=True)):
        entry['rerank_score'] = value
        entry['score'] = 1/(POLICY['rrf_k']+i+1) + 1/(POLICY['rrf_k']+positions[i])
    return candidates


def question_parts(query):
    """Independent sentences only; do not split entity lists or read domain IDs."""
    parts=[s.strip() for s in re.split(r'[。！？!?；;\n]+',query) if len(s.strip())>=POLICY['question_facets']['minimum_chars']]
    return list(dict.fromkeys(parts))[:POLICY['question_facets']['max_parts']] if len(parts)>1 else []


def dense_evidence(documents, values, count):
    """Distinct eligible parent evidence, never benchmark IDs or graph guesses."""
    ids=[]
    for i in sorted(range(len(documents)),key=lambda i:(-values[i],documents[i]['chunk_key'])):
        key=documents[i]['item_id']
        if values[i]>.3 and key not in ids:
            ids.append(key)
            if len(ids)>=count:break
    return ids


def rank(db,bundle,allowed,query,*,mode=None,limit=6):
    started=time.perf_counter()
    mode=mode or os.environ.get('KNOWLEDGE_RETRIEVAL_MODE',POLICY['default_mode'])
    if mode not in ('legacy','bm25','dense','hybrid','hybrid_rerank'):
        raise ValueError('Unknown retrieval mode')
    documents=[c for c in chunks(bundle) if c['item_id'] in allowed]
    diagnostic={'requested_mode':mode,'effective_mode':mode,'pipeline_fingerprint':fingerprint(),'version':POLICY['version'],
        'embedding_model':None,'reranker_model':None,'vector_backend':None,'fallback_reason':None}
    if not documents:
        return [],diagnostic
    sparse=bm25(query,documents)
    dense=None
    facets=question_parts(query) if mode in ('hybrid','hybrid_rerank') else []
    facet_scores=[]
    facet_evidence=[]
    if mode in ('dense','hybrid','hybrid_rerank'):
        try:
            dense,backend=dense_scores(db,query,documents,bundle)
            diagnostic.update(embedding_model=neural.MANIFEST['embedding']['id'],vector_backend=backend)
            for part in facets:
                part_dense,_=dense_scores(db,part,documents,bundle)
                facet_scores.append((bm25(part,documents),part_dense))
                facet_evidence.extend(dense_evidence(documents,part_dense,
                    min(POLICY['question_facets']['dense_evidence_per_part'],max(1,limit//len(facets)))))
        except (ImportError,OSError,ValueError,RuntimeError) as exc:
            diagnostic.update(effective_mode='bm25',fallback_reason=type(exc).__name__)
            mode='bm25'
    sparse_order=sorted(range(len(documents)),key=lambda i:(-sparse[i],documents[i]['chunk_key']))
    dense_order=sorted(range(len(documents)),key=lambda i:(-dense[i],documents[i]['chunk_key'])) if dense is not None else []
    fused=Counter()
    recall_lists=[(sparse_order,sparse),(dense_order,dense)]
    for part_sparse,part_dense in facet_scores:
        recall_lists.extend((sorted(range(len(documents)),key=lambda i:(-values[i],documents[i]['chunk_key'])),values)
            for values in (part_sparse,part_dense))
    for order,values in recall_lists:
        for rank_idx,i in enumerate(order[:80],1):
            is_sparse=values is sparse or any(values is part_sparse for part_sparse,_ in facet_scores)
            if values is not None and (values[i]>0 if is_sparse else values[i]>.3):
                fused[i]+=1/(POLICY['rrf_k']+rank_idx)
    if mode=='bm25':
        scores={i:sparse[i] for i in sparse_order if sparse[i]>0}
    elif mode=='dense':
        scores={i:dense[i] for i in dense_order}
    else:
        scores=dict(fused)
    parents={}
    for i,score in sorted(scores.items(),key=lambda v:(-v[1],documents[v[0]]['chunk_key'])):
        item_id=documents[i]['item_id']
        entry=parents.setdefault(item_id,{'id':item_id,'score':score,'passages':[]})
        if len(entry['passages'])<2:
            entry['passages'].append(documents[i])
    exact={i for i,item in allowed.items() if any(len(a)>1 and a.lower() in query.lower() for a in [item['title'],*item['aliases']])}
    for key in exact:
        if key in parents:
            parents[key]['score']+=.04 if mode in ('hybrid','hybrid_rerank') else 2
    candidates=sorted(parents.values(),key=lambda p:(-p['score'],p['id']))[:POLICY['candidate_items']]
    if mode=='hybrid_rerank' and facet_evidence:
        reserved=set(facet_evidence)
        # Give each independent question access to its semantic evidence before
        # the shared reranker sees the bounded candidate pool.
        candidates=[parents[key] for key in dict.fromkeys(facet_evidence) if key in parents]+[
            e for e in candidates if e['id'] not in reserved]
        candidates=candidates[:POLICY['candidate_items']]
        candidates=sorted(candidates,key=lambda p:(-p['score'],p['id']))
    if mode=='hybrid_rerank' and candidates:
        try:
            passages=['\n'.join(p['content'] for p in e['passages'])[:1800] for e in candidates]
            relevance=neural.rerank(query,passages)
            for part in facets:
                relevance=[max(a,b) for a,b in zip(relevance,neural.rerank(part,passages),strict=True)]
            candidates=fuse_rerank(candidates,relevance,exact)
            diagnostic['reranker_model']=neural.MANIFEST['reranker']['id']
        except (ImportError,OSError,ValueError,RuntimeError) as exc:
            diagnostic.update(effective_mode='hybrid',fallback_reason='reranker_'+type(exc).__name__)
    ordered=sorted(candidates,key=lambda p:(-p['score'],p['id']))
    if mode=='hybrid_rerank' and diagnostic['reranker_model'] and facet_evidence:
        # Balanced question coverage: reserve only genuinely reranker-supported
        # semantic hits, then fill with the overall fused ranking.
        reserved=set(facet_evidence)
        selected=[e for e in ordered if e['id'] in reserved and (e['rerank_score']>=POLICY['min_rerank_score'] or e['id'] in exact)][:limit]
        selected_ids={e['id'] for e in selected}
        selected += [e for e in ordered if e['id'] not in selected_ids][:max(0,limit-len(selected))]
        selected=sorted(selected,key=lambda p:(-p['score'],p['id']))
    else:
        selected=ordered[:limit]
    diagnostic.update(latency_ms=round((time.perf_counter()-started)*1000,2),candidate_items=len(parents),
        corpus_chunks=len(documents),returned_items=len(selected),question_parts=len(facets))
    return selected,diagnostic
