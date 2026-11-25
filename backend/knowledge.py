"""Foundation knowledge browsing and administrator review/evaluation/publication."""
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
try:
    from . import ai_planner, database as d
    from .knowledge_models import Bundle, Kind
    from .services import knowledge_store as kb, research_store as store, prompt_registry, knowledge_retrieval, retrieval_benchmark
except ImportError:
    import ai_planner, database as d
    from knowledge_models import Bundle, Kind
    from services import knowledge_store as kb, research_store as store, prompt_registry, knowledge_retrieval, retrieval_benchmark


class Review(BaseModel):
    model_config=ConfigDict(extra='forbid')
    notes:str=Field(min_length=10,max_length=1500)


class Publish(BaseModel):
    model_config=ConfigDict(extra='forbid')
    evaluation_id:str=Field(max_length=100)


class Withdrawal(Review):
    target_type:Literal['item','source']
    target_id:str=Field(pattern=r'^[a-z0-9_-]{2,80}$')


def report_summary(value):
    """Keep mobile listings bounded; complete trial rows have an audit endpoint."""
    result={k:v for k,v in value.items() if k not in ('variants','paired_regressions','retrieval_evaluation')}
    result['variants']={mode:{k:v for k,v in variant.items() if k not in ('cases','results')}
        for mode,variant in value.get('variants',{}).items()}
    if 'paired_regressions' in value:
        result['paired_regression_counts']={mode:sum(bool(row['regression']) for row in rows)
            for mode,rows in value['paired_regressions'].items()}
    if isinstance(value.get('retrieval_evaluation'),dict):
        result['retrieval_evaluation']=report_summary(value['retrieval_evaluation'])
    result['detail_rows_omitted']=True
    return result


def router(connection):
    router=APIRouter(prefix='/api/knowledge',tags=['foundation knowledge'])
    @router.get('')
    def info():
        with connection() as db:
            return kb.inventory(db)

    @router.get('/search')
    def search(q:str=Query(default='',max_length=400),kind:Kind|None=None,exercise_id:str|None=Query(default=None,max_length=80)):
        with connection() as db:
            return kb.retrieve(db,q,kind=kind,exercise_id=exercise_id,limit=300)

    @router.get('/items/{key}')
    def detail(key:str):
        with connection() as db:
            result=kb.retrieve(db,item_id=key)
            if not result['items']:
                raise HTTPException(404,'知识不存在或已撤回')
            return result

    @router.get('/export')
    def export():
        with connection() as db:
            store.require_admin(db)
            return kb.active(db)

    @router.get('/admin')
    def admin():
        with connection() as db:
            store.require_admin(db)
            return {'bundles':[{k:v for k,v in b.items() if k!='bundle'} for b in store.listing(db,'kb_bundle')],
                'evaluations':[report_summary(value) for value in store.listing(db,'kb_evaluation',limit=20)],
                'jobs':[j for j in store.listing(db,'job',limit=100) if j['job_type'] in ('knowledge_evaluation','retrieval_evaluation','knowledge_index')],
                'available_builtin':{'version':kb.latest()['version'],'registered':bool(store.get(db,'kb_bundle',kb.latest()['version']))},
                'retrieval':{'policy':knowledge_retrieval.POLICY,**knowledge_retrieval.neural.status()},
                'retrieval_evaluations':[report_summary(value) for value in store.listing(db,'kb_retrieval_eval',limit=10)]}

    @router.get('/evaluations/{key}')
    def evaluation_detail(key:str):
        with connection() as db:
            store.require_admin(db)
            value=store.get(db,'kb_evaluation',key)
            if not value:
                raise HTTPException(404,'评测报告不存在')
            return value

    @router.get('/retrieval-evaluations/{key}')
    def retrieval_evaluation_detail(key:str):
        with connection() as db:
            store.require_admin(db)
            value=store.get(db,'kb_retrieval_eval',key)
            if not value:
                raise HTTPException(404,'检索评测报告不存在')
            return value

    @router.post('/builtin-candidate')
    def builtin_candidate():
        with connection() as db:
            store.require_admin(db)
            return kb.import_bundle(db,kb.latest())

    @router.post('/index')
    def index_current():
        with connection() as db:
            store.require_admin(db)
            bundle=kb.active(db)
            return store.enqueue(db,'knowledge_index',{'version':bundle['version'],'fingerprint':kb.fingerprint(bundle),
                'withdrawals':sorted(kb.blocked(db)),'pipeline_fingerprint':knowledge_retrieval.fingerprint()})

    @router.post('/bundles')
    def add(body:Bundle):
        with connection() as db:
            return kb.import_bundle(db,body.model_dump())

    @router.post('/bundles/{key}/review')
    def review(key:str,body:Review):
        with connection() as db:
            store.require_admin(db)
            store.lock_publication(db)
            value=store.get(db,'kb_bundle',key)
            if not value or value['status']!='draft':
                raise HTTPException(409,'只能审核新的草稿版本')
            return store.put(db,'kb_bundle',key,{**value,'review_notes':body.notes,'reviewed_by':d.owner(),
                'reviewed_at':d.now().isoformat()},'reviewed')

    @router.post('/bundles/{key}/evaluate')
    def evaluate(key:str,retrieval_evaluation_id:str|None=Query(default=None,max_length=100)):
        with connection() as db:
            store.require_admin(db)
            value=store.get(db,'kb_bundle',key) if key!=kb.bundled()['version'] else {'bundle':kb.bundled(),'status':'reviewed'}
            if not value or value['status'] not in ('reviewed','published'):
                raise HTTPException(409,'需先审核知识包')
            if retrieval_evaluation_id:
                retrieval=store.get(db,'kb_retrieval_eval',retrieval_evaluation_id)
                if not retrieval or retrieval['status']!='passed' or not retrieval_benchmark.valid_report(retrieval,value['bundle'],kb.blocked(db)):
                    raise HTTPException(409,'检索报告缺失或已失效，请重新执行检索评测')
            return store.enqueue(db,'knowledge_evaluation',{'version':key,'fingerprint':kb.fingerprint(value['bundle']),
                'withdrawals':sorted(kb.blocked(db)),'pipeline_fingerprint':knowledge_retrieval.fingerprint(),
                'retrieval_suite_hash':retrieval_benchmark.suite_hash(),
                **({'retrieval_evaluation_id':retrieval_evaluation_id} if retrieval_evaluation_id else {})})

    @router.post('/bundles/{key}/retrieval-evaluate')
    def retrieval_evaluate(key:str):
        with connection() as db:
            store.require_admin(db)
            value=store.get(db,'kb_bundle',key) if key!=kb.bundled()['version'] else {'bundle':kb.bundled(),'status':'reviewed'}
            if not value or value['status'] not in ('reviewed','published'):
                raise HTTPException(409,'需先审核知识包')
            return store.enqueue(db,'retrieval_evaluation',{'version':key,'fingerprint':kb.fingerprint(value['bundle']),
                'withdrawals':sorted(kb.blocked(db)),'pipeline_fingerprint':knowledge_retrieval.fingerprint(),
                'retrieval_suite_hash':retrieval_benchmark.suite_hash()})

    @router.post('/bundles/{key}/activate')
    def activate(key:str,body:Publish):
        try:
            from .services import knowledge_evaluation as evaluation
        except ImportError:
            from services import knowledge_evaluation as evaluation
        with connection() as db:
            store.require_admin(db)
            store.lock_publication(db)
            value=store.get(db,'kb_bundle',key)
            report=store.get(db,'kb_evaluation',body.evaluation_id)
            if not value or value['status']!='reviewed' or not report or report['status']!='passed':
                raise HTTPException(409,'需要已审核的知识包及通过的专项评测')
            valid=(report['version']==key and report['fingerprint']==value['fingerprint']
                and report.get('passed') is True
                and report.get('runtime_fingerprint')==prompt_registry.runtime_fingerprint()
                and report.get('configured_model')==ai_planner.settings()['AI_MODEL']
                and report.get('suite_hash')==evaluation.suite_hash()
                and report.get('withdrawals')==sorted(kb.blocked(db))
                and retrieval_benchmark.valid_report(report.get('retrieval_evaluation'),value['bundle'],kb.blocked(db))
                and value['base_version']==kb.active(db)['version'])
            if not valid:
                raise HTTPException(409,'评测、来源状态、模型或基础版本已变化，请重新导入或评测')
            prior=kb.active(db)['version']
            release=store.put(db,'kb_bundle',key,{**value,'previous_version':prior,'evaluation_id':body.evaluation_id,
                'published_by':d.owner(),'published_at':d.now().isoformat()},'published')
            store.put(db,'kb_pointer','active',{'version':key},'active')
            return {k:v for k,v in release.items() if k!='bundle'}

    @router.post('/bundles/{key}/rollback')
    def rollback(key:str):
        with connection() as db:
            store.require_admin(db)
            store.lock_publication(db)
            value=store.get(db,'kb_bundle',key)
            if kb.active(db)['version']!=key or not value or not value.get('previous_version'):
                raise HTTPException(409,'只能回滚当前发布版本')
            store.put(db,'kb_pointer','active',{'version':value['previous_version']},'active')
            return {'version':value['previous_version']}

    @router.post('/withdrawals')
    def withdraw(body:Withdrawal):
        with connection() as db:
            store.require_admin(db)
            store.lock_publication(db)
            bundles=[kb.bundled(),*[b['bundle'] for b in store.listing(db,'kb_bundle',limit=1000)]]
            if not any(any(i['id']==body.target_id for i in b['sources' if body.target_type=='source' else 'items']) for b in bundles):
                raise HTTPException(404,'知识或来源不存在')
            target=body.target_type+':'+body.target_id
            return store.put(db,'kb_withdrawal',target,{'target':target,'notes':body.notes,
                'actor_id':d.owner(),'created_at':d.now().isoformat()},'withdrawn')
    return router
