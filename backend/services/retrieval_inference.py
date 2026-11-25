"""Pinned local CPU encoders. Models are data, never remote executable code.

Only public reviewed knowledge passages are indexed. No user profile, training
history or raw health series is sent to another embedding vendor.
"""
import hashlib
import importlib.util
import json
import os
from functools import lru_cache
from pathlib import Path
from threading import RLock

ROOT=Path(__file__).resolve().parent.parent
MANIFEST=json.loads((ROOT/'data/knowledge_models_manifest.json').read_text(encoding='utf-8'))
LOCK=RLock()


def directory():
    default=ROOT.parent/'.tools/retrieval-models' if os.name=='nt' else Path('/var/lib/liftlab/models')
    return Path(os.environ.get('KNOWLEDGE_MODEL_DIR') or str(default)).resolve()


def model_hash(component='embedding'):
    return hashlib.sha256(json.dumps(MANIFEST[component],sort_keys=True).encode()).hexdigest()


def assets_present(component):
    spec=MANIFEST[component]
    return all((directory()/spec['id']/name).is_file() for name in spec['files'])


def status():
    return {'manifest':MANIFEST['version'],'embedding_model':MANIFEST['embedding']['id'],
        'reranker_model':MANIFEST['reranker']['id'],'embedding_hash':model_hash(),'reranker_hash':model_hash('reranker'),
        'assets_present':all(assets_present(c) for c in ('embedding','reranker')),
        'runtime_installed':importlib.util.find_spec('onnxruntime') is not None and importlib.util.find_spec('tokenizers') is not None,
        'execution':'local_cpu','global_sota_verified':False}


@lru_cache(maxsize=2)
def load(component):
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    spec=MANIFEST[component]
    folder=directory()/spec['id']
    for name,meta in spec['files'].items():
        digest=hashlib.sha256()
        with (folder/name).open('rb') as stream:
            for block in iter(lambda:stream.read(2*1024*1024),b''):
                digest.update(block)
        if digest.hexdigest()!=meta['sha256']:
            raise ValueError('Retrieval model asset failed integrity verification')
    options=ort.SessionOptions()
    options.intra_op_num_threads=max(1,min(2,int(os.environ.get('KNOWLEDGE_CPU_THREADS','1'))))
    options.inter_op_num_threads=1
    options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
    options.enable_cpu_mem_arena=False
    try:
        session=ort.InferenceSession(str(folder/'model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
    except Exception as exc:
        raise RuntimeError('Retrieval model runtime failed: '+type(exc).__name__) from None
    tokenizer=Tokenizer.from_file(str(folder/'tokenizer.json'))
    tokenizer.enable_truncation(max_length=512)
    tokenizer.enable_padding(pad_id=0 if component=='embedding' else 1)
    return session,tokenizer,np


def _run(component,texts):
    session,tokenizer,np=load(component)
    encoded=tokenizer.encode_batch(texts)
    mapping={'input_ids':np.asarray([e.ids for e in encoded],dtype=np.int64),
        'attention_mask':np.asarray([e.attention_mask for e in encoded],dtype=np.int64),
        'token_type_ids':np.asarray([e.type_ids for e in encoded],dtype=np.int64)}
    try:
        output=session.run(None,{i.name:mapping[i.name] for i in session.get_inputs()})[0]
    except Exception as exc:
        raise RuntimeError('Retrieval inference failed: '+type(exc).__name__) from None
    return output,np


def embed(texts,*,query=False):
    if not texts:
        return []
    result=[]
    with LOCK:
        for offset in range(0,len(texts),8):
            batch=texts[offset:offset+8]
            if query:
                batch=[MANIFEST['embedding']['query_prefix']+t for t in batch]
            output,np=_run('embedding',batch)
            vectors=output[:,0] if output.ndim==3 else output
            vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
            if vectors.shape[1]!=MANIFEST['embedding']['dimensions'] or not np.isfinite(vectors).all():
                raise ValueError('Invalid embedding shape or values')
            result.extend(vectors.astype(float).tolist())
    return result


def rerank(query,passages):
    scores=[0.0]*len(passages)
    # Group similar lengths to avoid padding every batch to a long card. Restore
    # the caller's order so candidate IDs always retain their actual model score.
    order=sorted(range(len(passages)),key=lambda i:len(passages[i]))
    with LOCK:
        for offset in range(0,len(passages),4):
            indices=order[offset:offset+4]
            output,np=_run('reranker',[(query,passages[i]) for i in indices])
            logits=output.reshape(-1)
            values=1/(1+np.exp(-np.clip(logits,-60,60)))
            if len(values)!=len(indices) or not np.isfinite(values).all():
                raise ValueError('Invalid reranker scores')
            for i,value in zip(indices,values,strict=True):
                scores[i]=float(value)
    return scores
