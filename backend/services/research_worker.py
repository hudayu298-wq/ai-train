"""Claim bounded research jobs; sources and optimizations remain candidates until review."""
import asyncio
import json
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select, or_
from fastapi import HTTPException

try:
    from .. import database as d, ai_planner, research
    from . import research_store as store, evaluation, model_gateway, knowledge_store, knowledge_evaluation, knowledge_retrieval, retrieval_benchmark
except ImportError:
    import database as d, ai_planner, research
    from services import research_store as store, evaluation, model_gateway, knowledge_store, knowledge_evaluation, knowledge_retrieval, retrieval_benchmark


def schedule_feed(connection):
    with connection() as db:
        store.lock_publication(db)
        feed = store.get(db, 'feed', 'daily')
        if not feed or not (feed.get('enabled') or feed.get('auto_optimize')):
            return
        actor = d.owner_context.set(feed['actor_id'])
        try:
            day = d.now().date().isoformat()
            if feed.get('enabled') and feed.get('last_scheduled_day') != day:
                store.enqueue(db, 'literature', {k: feed[k] for k in ('query', 'limit')})
                feed['last_scheduled_day'] = day
            if feed.get('auto_optimize') and feed.get('last_optimization_day') != day:
                since = feed.get('last_optimization_at', '')
                feedback = db.conn.execute(select(d.records_table.c.payload).where(d.records_table.c.kind == 'agent_feedback')
                    .order_by(d.records_table.c.seq.desc()).limit(10000)).scalars()
                new_count = sum(bool(p.get('share_for_improvement')) and p.get('created_at', '') > since for p in feedback)
                new_evidence = any(e.get('reviewed_at', '') > since and store.eligible(db, e) for e in store.listing(db, 'evidence', 'reviewed'))
                if new_count >= feed.get('feedback_threshold', 5) or new_evidence:
                    store.enqueue(db, 'optimization', {})
                    feed.update(last_optimization_day=day, last_optimization_at=d.now().isoformat())
            store.put(db, 'feed', 'daily', feed, 'enabled')
        except HTTPException as exc:
            if exc.status_code == 403:
                store.put(db, 'feed', 'daily', {**feed, 'enabled': False, 'auto_optimize': False, 'error': '订阅发起人的管理员权限已失效'}, 'disabled')
            elif exc.status_code == 429:
                store.put(db, 'feed', 'daily', feed, 'enabled')
            else:
                raise
        finally:
            d.owner_context.reset(actor)


def claim(connection):
    with connection() as db:
        rows = db.conn.execute(select(d.research_records).where(d.research_records.c.kind == 'job',
            d.research_records.c.status.in_(['queued', 'running'])).order_by(d.research_records.c.updated_at)
            .with_for_update(skip_locked=True).limit(50)).mappings()
        for row in rows:
            job = {'id': row['id'], 'status': row['status'], **row['payload']}
            if job['status'] == 'running' and job.get('lease_until', '') > d.now().isoformat():
                continue
            if job.get('attempts', 0) >= 2:
                store.put(db, 'job', job['id'], {**job, 'error': '任务中断次数达到上限，请检查后重新提交'}, 'failed')
                continue
            job.update(attempts=job.get('attempts', 0)+1, lease_until=(d.now()+timedelta(minutes=25)).isoformat())
            return store.put(db, 'job', job['id'], job, 'running')


async def optimize(connection, job):
    with connection() as db:
        release = store.active(db)
        # Only explicitly opted-in categorical feedback enters global improvement.
        counts = {}
        for payload in db.conn.execute(select(d.records_table.c.payload).where(d.records_table.c.kind == 'agent_feedback')
                .order_by(d.records_table.c.seq.desc()).limit(10000)).scalars():
            if payload.get('share_for_improvement'):
                category = payload['category']
                counts[category] = counts.get(category, 0)+1
        reviewed = [e['id'] for e in store.listing(db, 'evidence', 'reviewed') if store.eligible(db, e)]
    raw, model = await ai_planner.chat_json([
        {'role': 'system', 'content': '你是私教Agent策略改进器，只输出CandidatePolicy schema JSON。只能调整回答长度、检索条数与澄清问题数。'
            '不能修改提示词、权限、安全校验、用户事实、评测或程序代码。依据匿名分类计数与当前策略谨慎调整，不能夸大改进效果。'},
        {'role': 'user', 'content': json.dumps({'schema': research.CandidatePolicy.model_json_schema(),
            'current_policy': release['policy'], 'opt_in_feedback_counts': counts}, ensure_ascii=False)}], max_tokens=700)
    policy = research.CandidatePolicy.model_validate(raw)
    with connection() as db:
        store.require_admin(db)
        if store.active(db)['id'] != release['id']:
            raise ValueError('Release changed while optimizing')
        value = research.candidate_snapshot(db, research.CandidateRequest(name='自动改进候选 '+d.now().date().isoformat(),
            policy=policy, evidence_ids=reviewed[:50]))
        value.update(optimizer_model=model, feedback_counts=counts)
        value['fingerprint'] = store.fingerprint(value)
        candidate = store.put(db, 'candidate', str(uuid4()), value, 'draft')
        evaluation_job = store.enqueue(db, 'evaluation', {'candidate_id': candidate['id']})
        return {'candidate_id': candidate['id'], 'evaluation_job_id': evaluation_job['id']}


async def run_once(connection):
    schedule_feed(connection)
    job = claim(connection)
    if not job:
        return {'status': 'idle'}
    owner_token = d.owner_context.set(job['actor_id'])
    session_token = d.session_context.set(None)
    events = []
    try:
        with connection() as db:
            store.require_admin(db)
        if job['job_type'] in ('knowledge_evaluation','retrieval_evaluation','knowledge_index'):
            with connection() as db:
                version=job['input']['version']
                record=store.get(db,'kb_bundle',version)
                bundle=record['bundle'] if record else knowledge_store.bundled() if version==knowledge_store.bundled()['version'] else None
                if (not bundle or record and record['status'] not in ('reviewed','published')
                        or knowledge_store.fingerprint(bundle)!=job['input']['fingerprint']
                        or sorted(knowledge_store.blocked(db))!=job['input']['withdrawals']
                        or job['input'].get('pipeline_fingerprint')!=knowledge_retrieval.fingerprint()
                        or job['job_type']!='knowledge_index' and job['input'].get('retrieval_suite_hash')!=retrieval_benchmark.suite_hash()):
                    raise ValueError('Knowledge version or withdrawals changed')
            if job['job_type']=='knowledge_index':
                def create_index():
                    with connection() as db:
                        withdrawn=knowledge_store.blocked(db)
                        eligible_ids={item['id'] for item in bundle['items'] if knowledge_store.eligible(item,withdrawn)}
                        documents=[c for c in knowledge_retrieval.chunks(bundle) if c['item_id'] in eligible_ids]
                        rows,vector=knowledge_retrieval.index(db,bundle,documents)
                        return {'version':version,'fingerprint':knowledge_store.fingerprint(bundle),'chunks':len(rows),
                            'vector_backend':'pgvector_exact' if vector else 'exact_dense_json',
                            'pipeline_fingerprint':knowledge_retrieval.fingerprint()}
                result=await asyncio.to_thread(create_index)
            else:
                if job['job_type']=='knowledge_evaluation':
                    retrieval_id=job['input'].get('retrieval_evaluation_id')
                    if retrieval_id:
                        with connection() as db:
                            prior=store.get(db,'kb_retrieval_eval',retrieval_id)
                            if not prior or prior['status']!='passed' or not retrieval_benchmark.valid_report(prior,bundle,knowledge_store.blocked(db)):
                                raise ValueError('Existing retrieval report is no longer valid')
                        value=await knowledge_evaluation.evaluate(connection,bundle,retrieval_report=prior)
                    else:
                        value=await knowledge_evaluation.evaluate(connection,bundle)
                else:
                    value=await asyncio.to_thread(retrieval_benchmark.evaluate,connection,bundle)
                with connection() as db:
                    store.require_admin(db)
                    result=store.put(db,'kb_evaluation' if job['job_type']=='knowledge_evaluation' else 'kb_retrieval_eval',
                        str(uuid4()),value,'passed' if value['passed'] else 'failed')
                result={'evaluation_id':result['id'],'passed':value['passed']}
        elif job['job_type'] == 'evaluation':
            with connection() as db:
                candidate = store.get(db, 'candidate', job['input']['candidate_id'])
            value = await evaluation.evaluate(connection, candidate)
            with connection() as db:
                result = store.put(db, 'evaluation', str(uuid4()), value, 'passed' if value['passed'] else 'failed')
            result = {'evaluation_id': result['id'], 'passed': value['passed']}
        else:
            with model_gateway.budget(events, max_calls=5, max_tokens=25000):
                if job['job_type'] == 'literature':
                    result = await research.ingest(connection, **job['input'])
                elif job['job_type'] == 'optimization':
                    result = await optimize(connection, job)
                else:
                    raise ValueError('Unknown job type')
        with connection() as db:
            store.require_admin(db)
            store.put(db, 'job', job['id'], {**job, 'result': result, 'usage_events': events, 'completed_at': d.now().isoformat()}, 'completed')
        return {'job_id': job['id'], 'status': 'completed'}
    except Exception:
        with connection() as db:
            store.put(db, 'job', job['id'], {**job, 'error': '任务未完成：检查模型配置、来源服务与评测详情后重试',
                'usage_events': events, 'completed_at': d.now().isoformat()}, 'failed')
        return {'job_id': job['id'], 'status': 'failed'}
    finally:
        d.session_context.reset(session_token)
        d.owner_context.reset(owner_token)
