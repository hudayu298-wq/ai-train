"""Owner-scoped private coach runs, pending actions, confirmation and recovery."""
import asyncio
import hashlib
import json
import os
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

try:
    from . import coach, coaches, database as d, health_data, workouts, exercise_selection, external_exercises, catalog_content, exercise_content
    from .services import agent_harness as harness, agent_routing as routing, context as context_service, research_store, model_gateway, prompt_registry, knowledge_store,privacy
except ImportError:
    import coach
    import coaches
    import database as d
    import health_data
    import workouts
    import exercise_selection
    import external_exercises
    import catalog_content, exercise_content
    from services import agent_harness as harness, agent_routing as routing, context as context_service, research_store, model_gateway, prompt_registry, knowledge_store,privacy


class Schedule(BaseModel):
    model_config = ConfigDict(extra='forbid')
    training_weekdays: list[int] | None = None
    session_minutes: int | None = Field(default=None, ge=15, le=180, strict=True)
    scope: Literal['current_profile', 'this_week']


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approved: bool


class Feedback(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: Literal['helpful', 'wrong_fact', 'tool_failure', 'too_long', 'missing_evidence', 'not_actionable']
    comment: str = Field(default='', max_length=500)
    share_for_improvement: bool = False


def action_view(record):
    return {k: record[k] for k in ('id', 'kind', 'status', 'preview', 'expires_at', 'result') if k in record}


class AgentService:
    def __init__(self, connection, context_provider, handlers, profile_model):
        self.connection = connection
        self.context_provider = context_provider
        self.handlers = handlers
        self.profile_model = profile_model

    def actions(self, db, run_id):
        return [action_view(r) for r in db.records('agent_action', limit=100) if r['run_id'] == run_id]

    def public(self, db, key, run):
        return {'run_id': key, 'request_id': run['input']['request_id'], 'user_message': run['input']['message'],
            'reply': run.get('reply') or run.get('error') or '任务处理中', 'profile_changes': run.get('profile_changes', []),
            'actions': self.actions(db, key), 'citations': run.get('citations', []), 'status': run['status'],
            'coach_id': run['input'].get('coach_id') or 'steady', 'coach_name': run.get('coach_name'),
            'model': run.get('model'), 'routing':routing.public(run['routing']) if run.get('routing') else None,
            'versions': run['versions']}

    def stage(self, run_id, kind, payload, lines):
        key = 'action-' + hashlib.sha256(json.dumps([run_id, kind, payload], sort_keys=True).encode()).hexdigest()[:40]
        with self.connection() as db:
            db.lock_user()
            run=db.read('agent_run',run_id)
            if run:privacy.require(db,run.get('privacy_revision'))
            prior = db.read('agent_action', key)
            if prior:
                return action_view({'id': key, **prior})
            value = {'kind': kind, 'run_id': run_id, 'payload': payload, 'status': 'pending','privacy_revision':privacy.revision(db),
                'preview': {'title': {'meal': '核对这餐饮食', 'plan': '确认训练计划', 'workout': '核对实际完成训练'}[kind], 'lines': lines},
                'expires_at': (d.now() + timedelta(hours=24)).isoformat(), 'created_at': d.now().isoformat()}
            db.write('agent_action', key, value)
            return action_view({'id': key, **value})

    async def tool(self, run_id, context, release, name, arguments, call_id, foundation=None):
        if name in ('search_knowledge', 'get_knowledge_item'):
            field='query' if name=='search_knowledge' else 'item_id'
            term=arguments.get(field)
            if not isinstance(term,str) or not term.strip() or len(term)>(400 if field=='query' else 80):
                raise ValueError('invalid knowledge query')
            def search():
                with self.connection() as db:
                    return knowledge_store.retrieve(db, arguments.get('query', ''), bundle=foundation,
                        item_id=arguments.get('item_id') if name == 'get_knowledge_item' else None, limit=5)
            return await asyncio.to_thread(search)
        if name == 'get_user_context':
            if arguments:
                raise ValueError('unexpected fields')
            return context
        if name=='get_exercise_details':
            key=arguments.get('exercise_id')
            if not isinstance(key,str) or not key or len(key)>80:raise ValueError('invalid exercise id')
            with self.connection() as db:
                entry=db.catalog_read('exercises',key)
                if not entry or not exercise_selection.visible(entry):raise HTTPException(404,'动作不存在或不在当前可选范围')
                return catalog_content.decorate(exercise_content.enrich(entry),'zh',catalog_content.published(db),catalog_content.fingerprint(entry))
        if name in ('search_exercises', 'search_foods'):
            query = arguments['query']
            if not isinstance(query, str) or len(query) > 100:
                raise ValueError('invalid query')
            kind = 'exercises' if name == 'search_exercises' else 'foods'
            with self.connection() as db:
                entries = db.catalog_read(kind)
                if kind == 'foods': entries += db.records('external_food')
                if kind == 'exercises':
                    translations = catalog_content.published(db)
                    entries = [catalog_content.decorate(exercise_content.enrich(r),'zh',translations,catalog_content.fingerprint(r)) for r in entries if exercise_selection.visible(r)]
                matched=[r for r in entries if query.lower() in json.dumps(r, ensure_ascii=False).lower()][:8]
                if kind=='exercises':
                    fields=('id','name','original_name','type','equipment','weight_basis','body_regions',
                        'movement_pattern','joint_actions','primary_muscles','secondary_muscles','rm_supported',
                        'realtime_supported','source_kind','source_label','review_status','classification','upstream_refs',
                        'content_version','translation_status')
                    return [{k:r[k] for k in fields if k in r} for r in matched]
                return matched
        if name == 'search_evidence':
            query = arguments['query']
            if not isinstance(query, str) or len(query) > 400:
                raise ValueError('invalid query')
            with self.connection() as db:
                return {'release_id': release['id'], 'items': research_store.retrieve(db, query, release=release)}
        if name == 'propose_meal':
            validated = self.handlers['meal_model'].model_validate({**arguments, 'day': context['today']})
            with self.connection() as db:
                food = db.catalog_read('foods', validated.food_id) or db.read('external_food', validated.food_id)
                if not food:
                    raise HTTPException(422, '食物不存在，请先查食物库并核对生熟状态')
            return self.stage(run_id, 'meal', validated.model_dump(mode='json'), [
                f"{food['name']} · {validated.grams:g} g · {food['state']}",
                '份量来源：' + validated.portion_source, '请确认食物、份量和餐次，确认后才写入当天饮食。'])
        if name == 'propose_workout':
            if arguments.get('plan_day'):
                plan = (context.get('current_plan') or [{}])[0]
                if not plan.get('id') or arguments['plan_day'] not in [day['name'] for day in plan['days']]:
                    raise HTTPException(422, '训练日未匹配当前计划，请先读取计划核对')
                arguments = {**arguments, 'plan_id': plan['id']}
            value = workouts.Workout.model_validate({**arguments, 'day': context['today'], 'request_id': 'agent-' + run_id[-40:]})
            lines = []
            with self.connection() as db:
                for e in value.exercises:
                    entry = db.catalog_read('exercises', e.exercise_id)
                    if not entry or entry['type'] != 'weighted':
                        raise HTTPException(422, '请选择有效负重动作')
                    for s in e.sets:
                        lines.append(f"{entry['name']} · {s.weight_kg:g} kg × {s.reps}次 · RPE {s.rpe:g}" + (' · 有不适' if s.pain else ''))
            return self.stage(run_id, 'workout', value.model_dump(mode='json'), lines)
        if name == 'propose_plan':
            schedule = Schedule.model_validate(arguments)
            if schedule.training_weekdays is not None:
                coach.ProfilePatch(training_weekdays=schedule.training_weekdays)
            with self.connection() as db:
                existing = next((a for a in db.records('agent_action', limit=100) if a['run_id'] == run_id and
                    a['kind'] == 'plan' and a.get('schedule') == schedule.model_dump() and a['status'] == 'pending'), None)
                if existing:
                    return action_view(existing)
            draft = await self.handlers['generate_plan'](schedule.model_dump(exclude_none=True))
            payload = {k: draft[k] for k in ('name', 'days', 'generation_id')}
            lines = [draft['name'], f"整体周期 {draft.get('cycle_weeks', 4)}周"]
            if draft.get('effective_until'):
                lines.append('临时周安排有效至 '+draft['effective_until']+'；到期后恢复最近的长期计划，长期画像不变。')
            for day in draft['days']:
                lines.append(day['name'] + f" · {day.get('duration_minutes') or '待定'}分钟")
                for e in day['exercises']:
                    lines.append(f"{e.get('name') or e['exercise_id']} · {e['weight_kg'] if e['weight_kg'] is not None else '待确认'} kg · {e['sets']}组×{e['reps']}次 · 休息{e['rest_seconds']}秒" +
                        (f" · {e['load_reference']['label']}，首训核对" if e.get('load_reference') else ''))
            lines.extend('风险提示：' + s for s in draft.get('risk_warnings', []))
            result = self.stage(run_id, 'plan', payload, lines)
            with self.connection() as db:
                action = db.read('agent_action', result['id'])
                db.write('agent_action', result['id'], {**action, 'schedule': schedule.model_dump()})
            return result
        raise ValueError('unregistered tool')

    async def start(self, request):
        key = 'agent-' + request.request_id
        with self.connection() as db:
            db.lock_user()
            cached = db.read('agent_run', key)
            if cached:
                if cached['input'] != request.model_dump():
                    raise HTTPException(409, '请求编号已用于其他Agent任务')
                return self.public(db, key, cached)
            release = research_store.active(db)
            foundation = knowledge_store.active(db)
            profile = {'facts':coach.facts(db)}
            selected = request.coach_id or 'steady'
            name = request.coach_name or coaches.require(selected)['name']
            revision = coach.fingerprint(db)
            private_revision=privacy.revision(db)
            history=coach.model_turns(db)[-8:]
        route=await routing.select(request.message,history)
        context = context_service.compact(await asyncio.to_thread(self.context_provider,request.message,
            sections=routing.context_keys(route)))
        # Foundation facts enter the Agent through its pinned, auditable tools.
        context.pop('foundation_knowledge', None)
        context['foundation_version'] = foundation['version']
        context['knowledge_release_id']=release['id']
        context=routing.context_view(context,route)
        messages = [{'role': 'system', 'content': harness.prompt(coaches.prompt(selected, coach.PROMPT), release['policy'])+routing.instruction(route)},
            {'role': 'system', 'content': json.dumps({'context': context, 'known_profile': routing.profile_view(profile['facts'],route)}, ensure_ascii=False)}]
        with self.connection() as db:
            db.lock_user()
            cached = db.read('agent_run', key)
            if cached:
                if cached['input'] != request.model_dump():
                    raise HTTPException(409, '请求编号已用于其他Agent任务')
                return self.public(db, key, cached)
            privacy.require(db,private_revision)
            history_routes=[]
            for turn in coach.model_turns(db)[-8:]:
                if not routing.compatible(turn,route):continue
                messages.extend([{'role': 'user', 'content': turn['user_message']}, {'role': 'assistant',
                    'content': json.dumps({'reply': turn['reply'], 'profile_updates': [], 'citations': []}, ensure_ascii=False)}])
                history_routes.append(turn.get('routing') or routing.public(routing.rules(turn['user_message'])))
            messages.append({'role': 'user', 'content': request.message})
            value = {'input': request.model_dump(), 'context': context, 'routing':route, 'history_routes':history_routes,'privacy_revision':private_revision,
                'release': release, 'foundation_bundle': foundation, 'messages': messages,
                'steps': [], 'usage_events': [], 'status': 'running', 'profile_revision': revision, 'created_at': d.now().isoformat(),
                'coach_name': name, 'versions': {'harness': harness.HARNESS_VERSION, 'prompt': coach.PROMPT_VERSION,
                    'runtime': prompt_registry.runtime_fingerprint(), 'prompt_assets': prompt_registry.VERSIONS,
                    'router':routing.VERSION, 'routing_policy':routing.fingerprint(),
                    'knowledge': release['id'], 'foundation': foundation['version'], 'foundation_hash': knowledge_store.fingerprint(foundation),
                    'policy': research_store.fingerprint(release['policy'])}}
            db.write('agent_run', key, value)
        return await self.execute(key, value)

    async def execute(self, key, value):
        def require_current_context():
            with self.connection() as db:
                privacy.require(db,value.get('privacy_revision'))
                if coach.fingerprint(db) != value['profile_revision']:
                    raise HTTPException(409, '画像、训练或授权状态已变化，请基于最新资料重新提问')
        async def preflight():
            await asyncio.to_thread(require_current_context)
        async def guarded_tool(name,args,cid):
            await preflight()
            if name not in routing.allowed_tools(value['routing']):
                raise HTTPException(403,'此工具不在当前领域，请先调用request_route扩展领域')
            if name=='request_route':
                route=routing.expand(value['routing'],args.get('domains'))
                context=context_service.compact(await asyncio.to_thread(self.context_provider,value['input']['message'],
                    sections=routing.context_keys(route)))
                await preflight()
                context.pop('foundation_knowledge',None)
                context.update(foundation_version=value['foundation_bundle']['version'],knowledge_release_id=value['release']['id'])
                context=routing.context_view(context,route)
                value.update(routing=route,context=context)
                selected=value['input'].get('coach_id') or 'steady'
                value['messages'][0]['content']=harness.prompt(coaches.prompt(selected,coach.PROMPT),value['release']['policy'])+routing.instruction(route)
                value['messages'][1]['content']=json.dumps({'context':context,'known_profile':context.get('known_profile',{})},ensure_ascii=False)
                return {'routing':routing.public(route),'context':context,'note':'领域已扩展，业务数据尚未修改。请读取新领域事实后使用相应工具。'}
            return await self.tool(key,value['context'],value['release'],name,args,cid,value.get('foundation_bundle'))
        def offered_tools():
            names=routing.allowed_tools(value['routing'])
            return [t for t in [*harness.TOOLS,harness.ROUTE_TOOL] if t['function']['name'] in names]
        def replace_route_context(route):
            # Refine only the already-authorized task snapshot.
            context=routing.context_view(value['context'],route)
            value.update(routing=route,context=context)
            selected=value['input'].get('coach_id') or 'steady'
            value['messages'][0]['content']=harness.prompt(coaches.prompt(selected,coach.PROMPT),value['release']['policy'])+routing.instruction(route)
            value['messages'][1]['content']=json.dumps({'context':context,'known_profile':context.get('known_profile',{})},ensure_ascii=False)
            # Provider refinement happens before generation. Prune unrelated
            # historical answers as well as the current context snapshot.
            past=value['messages'][2:-1]
            kept=[];kept_routes=[]
            for index,prior in enumerate(value.get('history_routes',[])):
                if route['scope']=='full' or set(prior['domains'])&set(route['domains']):
                    kept.extend(past[index*2:index*2+2]);kept_routes.append(prior)
            value['messages'][2:-1]=kept
            value['history_routes']=kept_routes
        def checkpoint(messages, steps):
            value.update(messages=messages, steps=steps, checkpoint_at=d.now().isoformat())
            with self.connection() as db:
                db.lock_user()
                privacy.require(db,value.get('privacy_revision'))
                db.write('agent_run', key, value)
        try:
            with model_gateway.budget(value.setdefault('usage_events', [])):
                async with asyncio.timeout(95):
                    if value['routing'].get('decision_pending'):
                        await preflight()
                        if value.get('decision_attempted'):
                            # An interrupted HTTP attempt may have been billed;
                            # recovery must not reset/repeat this attempt.
                            route={**value['routing'],'decision_pending':False}
                            route['stages'].append({'layer':'provider_decision','outcome':'interrupted_general'})
                        else:
                            value['decision_attempted']=True
                            checkpoint(value['messages'],value['steps'])
                            try:
                                result=await routing.decision_gateway.classify(value['input']['message'],routing.DECISION_QUESTIONS,
                                    on_attempt=lambda:checkpoint(value['messages'],value['steps']))
                                route=routing.apply_decision(value['routing'],result)
                            except routing.decision_gateway.DecisionUnavailable as exc:
                                route=await routing.select(value['input']['message'],allow_external=False)
                                route['stages'].append({'layer':'provider_decision','outcome':str(exc)})
                        await preflight()
                        replace_route_context(route)
                        checkpoint(value['messages'],value['steps'])
                    output, steps, model = await harness.drive(value['messages'],
                        guarded_tool,
                        steps=value['steps'], checkpoint=checkpoint, request_message=value['input']['message'],preflight=preflight,
                        tools=offered_tools)
            changes, evidence = coach.validate_updates(output, value['input']['message'])
            with self.connection() as db:
                db.lock_user()
                privacy.require(db,value.get('privacy_revision'))
                if coach.fingerprint(db) != value['profile_revision']:
                    raise HTTPException(409, '画像、训练或授权状态已变化，请基于最新资料重新提问')
                cited = {c['id']: c for s in steps if s['type'] == 'tool' and s.get('name') == 'search_evidence'
                    for c in s.get('result', {}).get('items', [])}
                cited.update({c['id']: c for s in steps if s['type']=='tool' and s.get('name') in ('search_knowledge','get_knowledge_item')
                    for c in s.get('result',{}).get('citations',[])
                    if knowledge_store.valid_citation(db,value.get('foundation_bundle') or knowledge_store.active(db),c['id'])})
                if any(c not in cited for c in output.citations):
                    raise HTTPException(502, 'Agent引用不在实际检索结果中')
                if changes:
                    coach.apply_profile(db, changes, self.profile_model, key)
                    # Plans generated before a simultaneous profile update require regeneration.
                    for action in db.records('agent_action', limit=100):
                        if action['run_id'] == key and action['kind'] == 'plan' and action['status'] == 'pending':
                            db.write('agent_action', action['id'], {**action, 'status': 'expired_profile_changed'})
                value.update(reply=output.reply, profile_changes=evidence, citations=[cited[c] for c in output.citations],
                    steps=steps, model=model, status='completed', completed_at=d.now().isoformat())
                db.write('agent_run', key, value)
                result = self.public(db, key, value)
                db.write('coach_turn', 'coach-turn-' + value['input']['request_id'], {**result,
                    'context_access':coach.context_access(db),
                    'model': model, 'created_at': d.now().isoformat(), 'prompt_version': coach.PROMPT_VERSION})
                return result
        except (HTTPException, TimeoutError, ValueError, TypeError) as exc:
            value.update(status='failed', error=exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else 'Agent任务未完成，已保留执行记录，可重试或查看操作草稿')
            with self.connection() as db:
                db.lock_user()
                if not privacy.current(db,value.get('privacy_revision')):
                    latest=db.read('agent_run',key)
                    safe=privacy.invalid_run(latest or value)
                    db.write('agent_run',key,safe)
                    return self.public(db,key,safe)
                db.write('agent_run', key, value)
                return self.public(db, key, value)

    async def decide(self, key, approved):
        with self.connection() as db:
            db.lock_user()
            action = db.read('agent_action', key)
            if not action:
                raise HTTPException(404, '操作草稿不存在')
            if action['status'] in ('committed', 'cancelled'):
                return action_view({'id': key, **action})
            if action['status'] == 'committing' and d.now().isoformat() < action.get('retry_after', ''):
                raise HTTPException(409, '操作正在保存，请稍后刷新')
            if action['status'] not in ('pending', 'committing') or action['expires_at'] < d.now().isoformat():
                raise HTTPException(409, '操作草稿已失效，请重新提出需求')
            privacy.require(db,action.get('privacy_revision'))
            if not approved:
                action['status'] = 'cancelled'
                db.write('agent_action', key, action)
                return action_view({'id': key, **action})
            action.update(status='committing', retry_after=(d.now() + timedelta(seconds=90)).isoformat())
            db.write('agent_action', key, action)
        try:
            payload = action['payload']
            with privacy.guard(action.get('privacy_revision')):
                if action['kind'] == 'meal':
                    result = self.handlers['save_meal'](self.handlers['meal_model'].model_validate({**payload, 'request_id': key}))
                elif action['kind'] == 'plan':
                    result = self.handlers['save_plan'](self.handlers['plan_model'].model_validate(payload))
                else:
                    result = self.handlers['save_workout'](workouts.Workout.model_validate({**payload, 'request_id': key}))
            with self.connection() as db:
                db.lock_user()
                privacy.require(db,action.get('privacy_revision'))
                action.update(status='committed', result={'record_id': result['id'], 'saved': True})
                if action['kind'] == 'workout':
                    db.write('agent_followup', result['id'], {'workout_id': result['id'], 'status': 'queued',
                        'coach_id': (db.read('agent_run', action['run_id']) or {}).get('input', {}).get('coach_id') or 'steady',
                        'session_id': d.session_context.get(), 'created_at': d.now().isoformat(), 'attempts': 0,
                        'privacy_revision':privacy.revision(db)})
                    action['result']['followup'] = 'queued'
                db.write('agent_action', key, action)
                return action_view({'id': key, **action})
        except (HTTPException, ValueError):
            with self.connection() as db:
                db.lock_user()
                if privacy.current(db,action.get('privacy_revision')):
                    action['status'] = 'pending'
                    db.write('agent_action', key, action)
            raise


def router(service):
    api = APIRouter(prefix='/api/agent')

    @api.get('/routing/status')
    def routing_status():
        return {'version':routing.VERSION,'mode':os.environ.get('AGENT_ROUTING_MODE','hybrid'),
            'domains':routing.LABELS,'decision_layer':routing.decision_gateway.status(),
            'local_encoder_present':routing.neural.assets_present('embedding')}

    @api.post('/runs')
    async def start(body: coach.MessageRequest):
        return await service.start(body)

    @api.get('/runs/{key}')
    def get_run(key: str):
        with service.connection() as db:
            value = db.read('agent_run', key)
            if not value:
                raise HTTPException(404, '任务不存在')
            return service.public(db, key, value)

    @api.post('/runs/{key}/resume')
    async def resume(key: str):
        with service.connection() as db:
            db.lock_user()
            value = db.read('agent_run', key)
            if not value:
                raise HTTPException(404, '任务不存在')
            if value['status'] == 'completed':
                return service.public(db, key, value)
            if value.get('privacy_invalidated') or 'privacy_revision' not in value:
                raise HTTPException(409,'旧任务来源或授权已失效，请发起新任务')
            privacy.require(db,value['privacy_revision'])
            if value['status'] == 'running' and value.get('created_at', '') > (d.now() - timedelta(minutes=3)).isoformat():
                raise HTTPException(409, '任务仍在运行，请稍后刷新')
            if coach.fingerprint(db) != value['profile_revision']:
                raise HTTPException(409, '任务资料已变化，请发起新任务')
            if not value.get('foundation_bundle'):
                raise HTTPException(409, '旧任务未保存基础知识快照，请发起新任务')
            if not value.get('routing') or value['versions'].get('router')!=routing.VERSION or value['versions'].get('routing_policy')!=routing.fingerprint() or value['versions'].get('harness')!=harness.HARNESS_VERSION:
                raise HTTPException(409,'任务路由版本已变化，请发起新任务')
            value.update(status='running', error=None)
            db.write('agent_run', key, value)
        return await service.execute(key, value)

    @api.post('/actions/{key}/decision')
    async def decide(key: str, body: Decision):
        return await service.decide(key, body.approved)

    @api.post('/runs/{key}/feedback')
    def feedback(key: str, body: Feedback):
        with service.connection() as db:
            if not db.read('agent_run', key):
                raise HTTPException(404, '任务不存在')
            db.write('agent_feedback', key, {**body.model_dump(), 'created_at': d.now().isoformat()})
        return {'saved': True}
    return api
