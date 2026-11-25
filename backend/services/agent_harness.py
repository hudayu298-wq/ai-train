"""A bounded, checkpointable tool loop shared by live coaching and isolated evals."""
import json
import re
from pathlib import Path
import time
from . import prompt_registry

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

try:
    from .. import ai_planner, coach
except ImportError:
    import ai_planner
    import coach


class AgentOutput(coach.CoachOutput):
    citations: list[str] = Field(default_factory=list, max_length=8)


HARNESS_VERSION = 'coach-harness-3-domain-funnel'
MAX_MODEL_CALLS = 5
MAX_TOOL_CALLS = 10


def spec(name, description, parameters):
    return {'type': 'function', 'function': {'name': name, 'description': description, 'parameters': parameters}}


def object_schema(properties=None, required=None):
    return {'type': 'object', 'properties': properties or {}, 'required': required or [], 'additionalProperties': False}


TOOLS = [
    spec('get_user_context', '读取当前领域的已确认资料和授权摘要。omitted_for_route为未加载；需要其他领域先request_route扩展。', object_schema()),
    spec('search_foods', '查找食物ID、每100克营养与生熟状态。', object_schema({'query': {'type': 'string', 'maxLength': 100}}, ['query'])),
    spec('search_exercises', '查找动作ID、器械、负重口径、关节动作与部位。', object_schema({'query': {'type': 'string', 'maxLength': 100}}, ['query'])),
    spec('get_exercise_details', '按已查到的动作ID读取完整教学、注意事项和资料来源；用于需要具体教学的问题。', object_schema({'exercise_id':{'type':'string','maxLength':80}},['exercise_id'])),
    spec('search_evidence', '检索本任务固定版本中已审核发布的研究证据；未命中时说明缺少依据。', object_schema({'query': {'type': 'string', 'maxLength': 400}}, ['query'])),
    spec('search_knowledge', '检索固定版本的基础知识，包括肌肉起止点、关节动作、训练和饮食原则。返回结构化事实、关系及来源；不等于临床验证。', object_schema({'query': {'type': 'string', 'maxLength': 400}}, ['query'])),
    spec('get_knowledge_item', '根据search_knowledge返回的节点ID读取肌肉、关节或动作知识及关联。不要猜ID。', object_schema({'item_id': {'type': 'string', 'maxLength': 80}}, ['item_id'])),
    spec('propose_meal', '创建待用户核对的饮食记录，确认前不写正式饮食。克重必须由用户提供或追问，不能猜测。', object_schema({
        'food_id': {'type': 'string'}, 'grams': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 3000},
        'meal_type': {'type': 'string', 'enum': ['breakfast', 'lunch', 'dinner', 'snack']},
        'portion_source': {'type': 'string', 'enum': ['estimated', 'weighed', 'label', 'unknown']}}, ['food_id', 'grams', 'meal_type', 'portion_source'])),
    spec('propose_plan', '根据当前画像生成真实AI计划草稿和差异供用户确认。可提供临时训练日与时长；不会自动改长期画像。', object_schema({
        'training_weekdays': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1, 'maximum': 7}, 'minItems': 1, 'maxItems': 7},
        'session_minutes': {'type': 'integer', 'minimum': 15, 'maximum': 180},
        'scope': {'type': 'string', 'enum': ['current_profile', 'this_week']}}, ['scope'])),
    spec('propose_workout', '将用户明确提供的实际训练整理为待核对记录。缺少重量、次数或RPE先追问，不猜测完成情况。', object_schema({
        'exercises': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': object_schema({
            'exercise_id': {'type': 'string'}, 'sets': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                'items': object_schema({'weight_kg': {'type': 'number', 'minimum': 0, 'maximum': 500},
                    'reps': {'type': 'integer', 'minimum': 1, 'maximum': 100}, 'rpe': {'type': 'number', 'minimum': 1, 'maximum': 10},
                    'pain': {'type': 'boolean'}}, ['weight_kg', 'reps', 'rpe', 'pain'])}}, ['exercise_id', 'sets'])},
        'notes': {'type': 'string', 'maxLength': 500},
        'plan_day': {'type': 'string', 'maxLength': 40},
        'completed_plan_day': {'type': 'boolean'},
        'readiness': {'type': 'string', 'enum': ['good', 'normal', 'poor']}}, ['exercises'])),
]

ROUTE_TOOL = spec('request_route', '当前问题需要其他领域资料/工具时扩展路由；不保存业务事实，不改变授权。扩展后再调用相关工具。',
    object_schema({'domains':{'type':'array','items':{'type':'string','enum':
        ['health','plan','nutrition','training','knowledge','profile','general']},'minItems':1,'maxItems':7}},['domains']))


def prompt(personality, policy):
    schema = AgentOutput.model_json_schema()
    schema['$defs']['ProfileUpdate']['properties']['field']['enum'] = list(coach.LABELS)
    return personality + '\n' + prompt_registry.text('agent.md') + '\n表达设置（不改变业务规则）：' + json.dumps(policy, ensure_ascii=False) + '\n输出Schema：' + json.dumps(schema, ensure_ascii=False) + '\n画像字段Schema：' + json.dumps(coach.ProfilePatch.model_json_schema(), ensure_ascii=False)


async def drive(messages, execute, *, steps=None, checkpoint=None, max_calls=MAX_MODEL_CALLS, request_message=None, preflight=None, tools=None):
    def offered():return tools() if callable(tools) else (tools if tools is not None else TOOLS)
    steps = steps if steps is not None else []
    deadline = time.monotonic() + 90
    calls = sum(s['type'] == 'model' for s in steps)
    tool_calls = sum(s['type'] == 'tool' for s in steps)
    seen = {s['call_id']: s for s in steps if s['type'] == 'tool'}
    original = request_message or next((m.get('content', '') for m in reversed(messages) if m['role'] == 'user'), '')
    needs_evidence = any(w in original for w in ('研究', '论文', '文献', '已发布')) and any(w in original for w in ('查', '依据', '证据', '参考'))
    needs_knowledge = any(w in original for w in ('起止点','起点','止点','跨关节','跨越哪些关节','股二头肌短头','比目鱼肌','教材活动度'))
    needs_workout = '帮我记录' in original and any(w in original for w in ('训练', '卧推', '深蹲', '硬拉')) and bool(re.search(r'RPE\s*\d', original, re.I)) and any(w in original for w in ('没有疼痛', '没有不适', '没有疼痛或不适', '无不适'))
    # A process may stop after one tool in a parallel batch. Finish that exact
    # assistant batch before asking the provider again (tool IDs remain paired).
    last_assistant = next((i for i in range(len(messages)-1, -1, -1) if messages[i]['role'] == 'assistant'), None)
    if last_assistant is not None and messages[last_assistant].get('tool_calls'):
        available=offered()
        last_model=next((s for s in reversed(steps) if s['type']=='model'),{})
        if 'tools' in last_model:
            available=[t for t in available if t['function']['name'] in last_model['tools']]
        supplied = {m['tool_call_id'] for m in messages[last_assistant+1:] if m['role'] == 'tool'}
        for call in messages[last_assistant]['tool_calls']:
            if call['id'] in supplied:
                continue
            name = call['function']['name']
            try:
                args = json.loads(call['function']['arguments'])
            except (ValueError, TypeError):
                args = {}
            schema = next((t['function']['parameters'] for t in available if t['function']['name'] == name), None)
            if not schema or not isinstance(args, dict) or set(args)-schema['properties'].keys() or set(schema['required'])-args.keys():
                value = {'error': '恢复的工具参数无效，请纠正'}
            elif tool_calls >= MAX_TOOL_CALLS:
                raise HTTPException(429, '工具预算已用完')
            else:
                try:
                    value = seen[call['id']]['result'] if call['id'] in seen else await execute(name, args, call['id'])
                except (ValueError, TypeError, KeyError, HTTPException):
                    value = {'error': '恢复工具失败，请纠正参数或向用户追问'}
            event = {'type': 'tool', 'call_id': call['id'], 'name': name, 'arguments': args,
                'result': value, 'status': 'completed' if 'error' not in value else 'rejected'}
            steps.append(event)
            seen[call['id']] = event
            tool_calls += 1
            messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': json.dumps(value, ensure_ascii=False)})
            if checkpoint:
                checkpoint(messages, steps)
    for _ in range(max_calls - calls):
        if time.monotonic() > deadline or sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) > 70000:
            raise HTTPException(429, '任务达到时长或上下文预算，请缩小问题范围')
        # Persist the attempt before network I/O, so retries do not reset the budget.
        available=offered()
        steps.append({'type': 'model', 'attempt': calls + 1, 'status': 'started',
            'tools':[t['function']['name'] for t in available]})
        if checkpoint:
            checkpoint(messages, steps)
        if preflight:
            await preflight()
        response = await ai_planner.tool_turn(messages, available, max_tokens=2200)
        steps[-1].update(status='completed', model=response['model'], usage=response.get('usage', {}), latency_ms=response.get('latency_ms'))
        calls += 1
        message = response['message']
        invoked = message.get('tool_calls') or []
        if not invoked:
            if needs_knowledge and not any(s['type']=='tool' and s.get('name') in ('search_knowledge','get_knowledge_item') and s['status']=='completed' for s in steps):
                messages.extend([message,{'role':'user','content':'本任务涉及结构化解剖事实。请先调用search_knowledge核对来源与适用范围；不能未检索就声称知识库没有覆盖。'}])
                if checkpoint:
                    checkpoint(messages,steps)
                continue
            if needs_workout and not any(s['type'] == 'tool' and s.get('name') == 'propose_workout' and s['status'] == 'completed' for s in steps):
                messages.extend([message, {'role': 'user', 'content': '本任务明确请求记录实际训练并已给出RPE及不适情况。请查动作ID后调用propose_workout整理待确认记录。参数若确实缺失须具体指出，不能只文字说已整理或已记录。'}])
                if checkpoint:
                    checkpoint(messages, steps)
                continue
            if needs_evidence and not any(s['type'] == 'tool' and s.get('name') == 'search_evidence' and s['status'] == 'completed' for s in steps):
                messages.extend([message, {'role': 'user', 'content': '本任务要求查证据，但你尚未调用search_evidence。请先检索已发布证据，再说明命中结果或缺少依据；不能未检索就声称没有。'}])
                if checkpoint:
                    checkpoint(messages, steps)
                continue
            try:
                result = AgentOutput.model_validate_json(message.get('content') or '')
            except ValueError:
                messages.extend([message, {'role': 'user', 'content': '最终输出不符合Schema。请只返回一个JSON对象，必须包含reply字符串、profile_updates数组、citations数组；无更新或引用用[]。只整理已有工具结果，不重复创建操作。不要输出Markdown或其他字段。'}])
                steps.append({'type': 'validation', 'status': 'rejected', 'reason': 'invalid_final_schema'})
                if checkpoint:
                    checkpoint(messages, steps)
                continue
            allowed_citations=set()
            for step in steps:
                if step['type']!='tool' or step.get('status')!='completed':
                    continue
                if step.get('name')=='search_evidence':
                    allowed_citations.update(c['id'] for c in step.get('result',{}).get('items',[]))
                elif step.get('name') in ('search_knowledge','get_knowledge_item'):
                    allowed_citations.update(c['id'] for c in step.get('result',{}).get('citations',[]))
            if not set(result.citations).issubset(allowed_citations):
                messages.extend([message,{'role':'user','content':'引用编号未匹配实际检索结果。请保留有依据的解释并纠正最终citations，只能从以下编号中选择：'+json.dumps(sorted(allowed_citations),ensure_ascii=False)+
                    '。不要使用source_id、节点item_id或自行编造编号；无需重复检索或创建操作。'}])
                steps.append({'type':'validation','status':'rejected','reason':'invalid_citation_ids'})
                if checkpoint:
                    checkpoint(messages,steps)
                continue
            if checkpoint:
                checkpoint(messages, steps)
            return result, steps, response['model']
        if len(invoked) > 4:
            raise HTTPException(429, '单步工具请求超出预算')
        messages.append(message)
        for call in invoked:
            tool_calls += 1
            if tool_calls > MAX_TOOL_CALLS:
                raise HTTPException(429, '工具执行次数达到上限')
            name = call.get('function', {}).get('name', '')
            call_id = call.get('id', '')
            if not call_id or len(call_id) > 150:
                raise HTTPException(502, '工具调用标识无效')
            try:
                arguments = json.loads(call['function']['arguments'])
                if not isinstance(arguments, dict) or len(json.dumps(arguments)) > 20000:
                    raise ValueError('invalid tool arguments')
                if name not in {t['function']['name'] for t in available}:
                    raise ValueError('unknown tool')
                allowed = next(t['function']['parameters'] for t in available if t['function']['name'] == name)
                if set(arguments) - allowed['properties'].keys() or set(allowed['required']) - arguments.keys():
                    raise ValueError('tool schema mismatch')
                previous = seen.get(call_id)
                if previous:
                    if previous['name'] != name or previous['arguments'] != arguments:
                        raise ValueError('reused tool call id')
                    value = previous['result']
                else:
                    value = await execute(name, arguments, call_id)
                event = {'type': 'tool', 'call_id': call_id, 'name': name, 'arguments': arguments, 'result': value, 'status': 'completed'}
            except (ValueError, KeyError, TypeError, HTTPException) as exc:
                value = {'error': exc.detail if isinstance(exc, HTTPException) and isinstance(exc.detail, str) else '工具字段无效或权限不允许；请纠正参数或向用户追问'}
                event = {'type': 'tool', 'call_id': call_id, 'name': name, 'arguments': {}, 'result': value, 'status': 'rejected'}
            seen[call_id] = event
            steps.append(event)
            messages.append({'role': 'tool', 'tool_call_id': call_id, 'content': json.dumps(value, ensure_ascii=False)})
            if checkpoint:
                checkpoint(messages, steps)
    if any(s.get('reason')=='invalid_citation_ids' for s in steps):
        raise HTTPException(502, 'Agent引用编号多次修正后仍未匹配实际检索结果，已保留任务记录')
    raise HTTPException(429, 'Agent模型调用次数达到上限，已保留任务记录')
