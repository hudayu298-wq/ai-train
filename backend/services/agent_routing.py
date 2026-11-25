"""Bounded domain funnel. Routing narrows data/tools, never grants authorization.

The optional semantic layer uses existing pinned LOCAL encoders on the current
message only. Private messages/vectors never enter Redis or the public index.
Low scores, missing assets, errors and timeouts all retain the general harness.
"""
import asyncio
import copy
import hashlib
import json
import os
import re
import time
from functools import lru_cache
from pathlib import Path
from threading import Lock

from . import retrieval_inference as neural, decision_gateway

VERSION = 'domain-funnel-1'
DOMAINS = ('health', 'plan', 'nutrition', 'training', 'knowledge', 'profile', 'general')
LABELS = dict(zip(DOMAINS, ('健康与恢复', '训练计划', '饮食营养', '训练记录与动作', '知识与研究', '个人画像', '综合私教')))
POLICY = {'semantic_min_score': .60, 'semantic_min_margin': .04,
    'semantic_timeout_seconds': 1.5, 'semantic_max_chars': 500, 'max_expansions': 2,
    'decision_yes':.8,'decision_uncertain':.3}
DECISION_QUESTIONS={
    'health':'用户的健康、疼痛、伤病、睡眠、恢复、健康设备测量或活动度问题，而不是给用户诊断。',
    'plan':'制定、更改、查看训练计划或训练日程、分化、周期及训练法。',
    'nutrition':'饮食、食物、份量、营养目标、热量、进食记录或食谱。',
    'training':'实际完成训练的记录、训练进展、动作教学或训练复盘；单纯编排计划不算。',
    'knowledge':'查证公开知识、科研文献、解剖事实、依据或一般训练营养原理。',
    'profile':'录入、更正或询问个人基本资料和长期训练/饮食偏好。',
    'general':'仅寒暄、询问软件功能或与健身无关，没有其他六个领域的实际请求。',
}
RULES = {
    'health': r'健康|睡眠|睡了|失眠|心率|体脂|血压|血糖|手表|h[rR][vV]|恢复|伤病|受伤|膝触墙|活动度|康复|疼|痛|不适|难受|过敏',
    'plan': r'计划|安排.{0,8}(训练|练)|(?:编排|安排).{0,8}(?:课程|日程)|分化|减量周|周期|训练法|训练日|每周.{0,6}(练|训练)|二分|三分|四分|五分',
    'nutrition': r'饮食|营养|吃|喝|餐|饭|食物|食品|米饭|鸡蛋|蛋白|碳水|脂肪|热量|卡路里|千卡|kcal|克重|食谱|补剂',
    'training': r'训练|卧推|深蹲|硬拉|划船|引体|哑铃|杠铃|器械|动作|负重|加重|组数|次数|复盘|(?<![a-z])(?:rpe|rir|rm|kg)(?![a-z])|公斤|健身',
    'knowledge': r'知识|解剖|肌肉|股四头|股二头|比目鱼|股直肌|起止点|起点|止点|关节|原理|研究|论文|文献|证据|教材|指南',
    'profile': r'画像|个人资料|我的资料|身高|体重|年龄|我.{0,5}岁|训练经验|训练偏好|性别|训练目标|每周.{0,5}哪几天',
}
PROTOTYPES = {
    'health': ['这两天总是没精神还睡不踏实，该怎么考虑休息？', '下肢僵硬，蹲下时膝盖不舒服，先考虑身体状况。', '可穿戴设备的身体恢复指标变化意味着什么？'],
    'plan': ['下个月怎么练，请制定每星期的运动安排。', '想把增肌课程改成上肢下肢交替，设计一套方案。', '这周只能去两趟健身房，请重新编排日程。'],
    'nutrition': ['晚上饿得慌，怎么搭配一顿均衡的饭？', '一碗面条和牛肉能提供多少能量？', '减脂期间该怎么选外卖和分配三大营养素？'],
    'training': ['刚在健身房完成推胸，请帮我记下来。', '高位下拉怎么做，肩胛应该怎样移动？', '看一下最近的运动表现，下次要不要多做一组？'],
    'knowledge': ['大腿前侧这块组织从哪里连到哪里，依据是什么？', '解释一下渐进超负荷的理论基础。', '有没有经过审核的学术资料支持这个说法？'],
    'profile': ['我现在身高一米八，想把个人信息改一下。', '我偏好晚上去健身房，通常一周去三次。', '我是谁，我之前填写的基础资料有哪些？'],
    'general': ['你好，你能提供什么帮助？', '天气怎样，帮我写一首诗。', '我不知道该问什么，先聊一聊吧。'],
}
BASE_KEYS = {'today', 'coach_persona', 'video_evidence_available', 'knowledge_release_id', 'foundation_version'}
CONTEXT_KEYS = {
    'health': {'known_profile', 'health_context', 'mobility_context', 'training_memory'},
    'plan': {'known_profile', 'strength_profile', 'current_plan', 'rm', 'training_memory',
        'health_context', 'mobility_context', 'related_exercise_details', 'reminder_settings'},
    'nutrition': {'known_profile', 'nutrition'},
    'training': {'known_profile', 'strength_profile', 'current_plan', 'rm', 'training_memory',
        'health_context', 'mobility_context', 'related_exercise_details'},
    'knowledge': {'related_exercise_details'},
    'profile': {'known_profile', 'strength_profile', 'reminder_settings'},
    'general': set(),
}
COMMON_TOOLS = {'get_user_context', 'search_knowledge', 'get_knowledge_item', 'search_evidence'}
DOMAIN_TOOLS = {'health': {'search_exercises'}, 'plan': {'search_exercises', 'propose_plan'},
    'nutrition': {'search_foods', 'propose_meal'}, 'training': {'search_exercises', 'propose_workout'},
    'knowledge': {'search_exercises'}, 'profile': set(), 'general': set()}
SAFETY_FIELDS = {'restrictions', 'injury_status', 'movement_constraints', 'food_allergies'}
PROFILE_FIELDS = {
    'health': SAFETY_FIELDS | {'age', 'sex', 'sleep_hours', 'recovery_status', 'goal'},
    'nutrition': SAFETY_FIELDS | {'age', 'sex', 'height_cm', 'weight_kg', 'goal', 'goal_detail', 'days',
        'dietary_preferences', 'cooking_access', 'food_budget', 'eating_out_frequency'},
    'plan': None, 'training': None, 'profile': None, 'knowledge': set(), 'general': set(),
}
_SEMANTIC_LOCK = Lock()


def fingerprint():
    config=decision_gateway.settings()
    value={'source':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'decision_adapter':hashlib.sha256(Path(decision_gateway.__file__).read_bytes()).hexdigest(),
        'embedding':neural.model_hash(),'mode':os.environ.get('AGENT_ROUTING_MODE','hybrid'),
        'decision_provider':config['provider'],'decision_model':config['model'] if config['configured'] else None}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def _negative_removed(message):
    text=re.sub(r'(?:没有|并无|无|不伴有)(?:疼痛或不适|疼痛|不适|痛感|过敏)', '', message, flags=re.I)
    return re.sub(r'(?:不要|无需|不用|不必|不)(?:再|自动)?(?:关联|修改|更新|更改|生成|制定|启用|记录|保存)'
        r'(?:我的|任何|长期|当前)?(?:训练)?(?:计划|画像|饮食|训练记录|rm|个人资料|记录)','',text,flags=re.I)


def _decision(domains, *, method='rules', scope='focused', risk=(), reason='explicit_domain'):
    chosen=[d for d in DOMAINS if d in domains]
    return {'version':VERSION, 'policy_hash':fingerprint(), 'primary':chosen[0], 'domains':chosen,
        'method':method, 'scope':scope, 'risk_flags':sorted(set(risk)), 'expansions':0,
        'stages':[{'layer':'rules','outcome':reason}]}


def rules(message, history=()):
    text=message.lower()
    clean=_negative_removed(text)
    risk=[]
    if re.search(r'疼|痛|不适|难受|受伤|过敏',clean):risk.append('health_caution')
    if re.search(r'忽略.{0,12}(规则|指令|系统)|不用.{0,6}确认|绕过|publish_knowledge',text):risk.append('untrusted_instruction')
    if re.fullmatch(r'[\s!！?？。，,.]*(你好|您好|嗨|hello|hi|谢谢|谢谢你|你能做什么|你有什么功能)[\s!！?？。，,.]*',text):
        return _decision(['general'],scope='minimal',risk=risk,reason='greeting')
    # A request to combine all records is deliberately comprehensive.
    if re.search(r'(结合|综合|根据).{0,12}(我的记录|所有记录|全部资料|整体情况)',text):
        return _decision(['general'],scope='full',risk=risk,reason='comprehensive_request')
    domains={name for name,pattern in RULES.items() if re.search(pattern,clean,re.I)}
    if 'plan' in domains and not re.search(r'记录|复盘|完成|动作|卧推|深蹲|硬拉|怎么做',text):domains.discard('training')
    if domains:
        return _decision(domains,risk=risk)
    if history and len(text)<=80 and re.search(r'^(那|这个|那个|这样|继续|还有|再|刚才|上面)|怎么样|可以吗|行吗|多少呢',text):
        previous=history[-1]
        prior=previous.get('routing')
        if not prior:
            prior=rules(previous.get('user_message',''))
        if prior and prior.get('scope')!='full' and 'general' not in prior['domains']:
            return _decision(prior['domains'],method='followup',risk=set(risk)|set(prior.get('risk_flags',[])),reason='authorized_user_history')
    return _decision(['general'],method='general',scope='full',risk=risk,reason='uncertain')


@lru_cache(maxsize=2)
def _prototype_vectors(policy_hash, model_hash):
    labels=[domain for domain,examples in PROTOTYPES.items() for _ in examples]
    vectors=neural.embed([text for examples in PROTOTYPES.values() for text in examples])
    return labels,vectors


def semantic_scores(message):
    if not _SEMANTIC_LOCK.acquire(blocking=False):raise RuntimeError('semantic_busy')
    try:
        labels,vectors=_prototype_vectors(fingerprint(),neural.model_hash())
        query=neural.embed([message],query=True)[0]
        scores={domain:max(sum(a*b for a,b in zip(query,vector,strict=True))
            for label,vector in zip(labels,vectors,strict=True) if label==domain) for domain in DOMAINS}
        return sorted(scores.items(),key=lambda pair:pair[1],reverse=True)
    finally:_SEMANTIC_LOCK.release()


async def select(message, history=(), *, allow_external=True):
    started=time.perf_counter()
    route=rules(message,history)
    if route['method']=='general':
        mode=os.environ.get('AGENT_ROUTING_MODE','hybrid')
        if mode=='rules':reason='rules_only'
        elif allow_external and decision_gateway.settings()['configured']:
            route['decision_pending']=True
            route['latency_ms']=round((time.perf_counter()-started)*1000,2)
            return route
        elif len(message)>POLICY['semantic_max_chars']:reason='long_message_general'
        elif not neural.assets_present('embedding'):reason='semantic_assets_unavailable'
        else:
            try:
                ranked=await asyncio.wait_for(asyncio.to_thread(semantic_scores,message),POLICY['semantic_timeout_seconds'])
                best,score=ranked[0];margin=score-ranked[1][1]
                route['semantic']={'model':neural.MANIFEST['embedding']['id'],
                    'score':round(score,4),'margin':round(margin,4),'score_type':'cosine_not_probability'}
                if best!='general' and score>=POLICY['semantic_min_score'] and margin>=POLICY['semantic_min_margin']:
                    route.update(primary=best,domains=[best],method='semantic',scope='focused')
                    reason='accepted'
                else:reason='low_confidence_general'
            except (TimeoutError,ImportError,OSError,ValueError,RuntimeError,IndexError):
                reason='semantic_unavailable_general'
        route['stages'].append({'layer':'local_semantic','outcome':reason})
    route['latency_ms']=round((time.perf_counter()-started)*1000,2)
    return route


def apply_decision(route,result):
    value=copy.deepcopy(route)
    scores=result['probabilities']
    chosen=[d for d in DOMAINS if d!='general' and scores[d]>=POLICY['decision_yes']]
    uncertain=any(POLICY['decision_uncertain']<=score<POLICY['decision_yes'] for score in scores.values())
    outcome='low_confidence_general'
    if chosen and not uncertain:
        value.update(primary=chosen[0],domains=chosen,scope='focused',method='decision')
        outcome='accepted'
    elif not chosen and not uncertain and scores['general']>=POLICY['decision_yes']:
        value.update(primary='general',domains=['general'],scope='minimal',method='decision')
        outcome='accepted_general'
    value['decision']={k:copy.deepcopy(result[k]) for k in ('provider','model','probabilities','latency_ms')}
    value['decision_pending']=False
    value['stages'].append({'layer':'provider_decision','outcome':outcome})
    return value


def context_keys(route):
    if route['scope']=='full':return None
    return BASE_KEYS | set().union(*(CONTEXT_KEYS[d] for d in route['domains']))


def profile_view(facts,route):
    if route['scope']=='full':return copy.deepcopy(facts)
    fields=[PROFILE_FIELDS[d] for d in route['domains']]
    if None in fields:return copy.deepcopy(facts)
    allowed=set().union(*fields)
    return {k:copy.deepcopy(v) for k,v in facts.items() if k in allowed}


def context_view(context,route):
    keys=context_keys(route)
    value={k:copy.deepcopy(v) for k,v in context.items() if keys is None or k in keys}
    if 'known_profile' in value:value['known_profile']=profile_view(value['known_profile'],route)
    # Omitted is distinct from revoked; no health values enter unrelated domains.
    for key in ('health_context','mobility_context'):
        value.setdefault(key,{'enabled':False,'omitted_for_route':True})
    value['routing']=public(route)
    return value


def allowed_tools(route):
    if route['scope']=='full':
        names=COMMON_TOOLS|set().union(*DOMAIN_TOOLS.values())
    elif route['scope']=='minimal':names={'get_user_context'}
    else:names=COMMON_TOOLS|set().union(*(DOMAIN_TOOLS[d] for d in route['domains']))
    if 'search_exercises' in names:names=names|{'get_exercise_details'}
    return names|{'request_route'}


def public(route):
    return {k:copy.deepcopy(route[k]) for k in ('version','primary','domains','scope','method','risk_flags',
        'stages','latency_ms','semantic','decision','expansions') if k in route}


def compatible(turn,route):
    if route['scope']=='full':return True
    prior=turn.get('routing') or rules(turn.get('user_message',''))
    return bool(set(prior['domains'])&set(route['domains']))


def expand(route,domains):
    if not isinstance(domains,list) or not domains or len(domains)>len(DOMAINS) or any(d not in DOMAINS for d in domains):
        raise ValueError('invalid route domains')
    if route.get('expansions',0)>=POLICY['max_expansions']:raise ValueError('route expansion budget exhausted')
    value=copy.deepcopy(route)
    value['domains']=[d for d in DOMAINS if d in set(route['domains'])|set(domains)]
    value.update(primary=value['domains'][0],scope='full' if 'general' in domains else 'focused',
        expansions=route.get('expansions',0)+1)
    value['stages'].append({'layer':'harness_expansion','outcome':'expanded','domains':domains})
    return value


def instruction(route):
    labels='、'.join(LABELS[d] for d in route['domains'])
    return ('\n当前专项：'+labels+'。先回答这几个领域的问题，跨领域问题分别给出要点。'
        '上下文按需提供；omitted_for_route表示本轮未加载，不代表用户没有记录或已撤权。'
        '缺少其他领域工具或资料时，先调用request_route申请领域，再读取get_user_context；'
        '最多扩展两次。不得因路由、余弦分数或健康风险标签推断诊断、力量、用户事实或授权。'
        '动作ID和口径通过search_exercises核对，不依赖初始上下文提供完整目录。'
        '健康与恢复只解释已授权事实及局限，不诊断或开处方；疼痛/不适按原规则处理，历史伤病不统一拒绝计划。'
        '饮食数值以食物库和确认克重确定性计算，缺失日记不等于未进食；'
        '计划及训练沿用原有力量完整性、动作/负重口径和待确认规则。')
