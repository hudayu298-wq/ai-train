"""Source-labelled rule cards share versions/values with executable policies."""
import json
from pathlib import Path
from .knowledge_nutrition import install_nutrition


def install_principles(sources,nodes):
    install_nutrition(sources,nodes)
    policy=json.loads((Path(__file__).parent.parent/'policies/training-v1.json').read_text(encoding='utf-8'))
    sid='training-product-policy'
    sources.append({'id':sid,'title':'练伴可执行周期与进阶产品规则','url':'https://github.com/hudayu298-wq/ai-train',
        'edition':policy['version'],'section':'backend/policies/training-v1.json 与 backend/periodization.py',
        'accessed_on':'2026-10-22','content_use':'product_policy','evidence_type':'product_policy','publisher':'练伴',
        'licensing_note':'产品自定执行约束；用于审计和版本管理，没有宣称这些精确阈值已获研究或临床验证。'})
    entries=[
        ('cycle_week_targets','逐周可执行目标','周期以周、阶段、训练日和逐动作目标表示；周数变动必须核对实际执行目标。',
            ['训练周包含组数、次数、重量、余力与休息；基于实际完成情况进入下一周。','复杂周期不是普通健康成人训练的必要前提。'],
            ['default_target_rir','week_review_days']),
        ('progression_gate','进阶门槛的来源与范围','符合产品进阶资格只代表允许考虑调整，不等于下一次一定加重。',
            ['这些数值为当前产品默认，不是所有人适用的ACSM统一处方。','结合相同器械与负重口径、当前不适、实际完成与可靠RM校验。'],
            ['progression_rpe_ceiling','max_weight_increase_fraction','max_rep_change','rm_max_age_days']),
        ('deload_week','减量周与退出复核','减量安排应说明触发原因、调整内容、持续范围和后续复核。',
            ['明确减量周的实际目标，并由用户确认重大周期调整。','不能把组数、次数或重量降低的某一固定比例说成所有人的研究标准。'],
            ['reduction_rpe_floor','deload_set_fraction','max_weight_reduction_fraction']),
        ('missed_sessions','漏练与断训处理','未完成的计划不当作已完成记录，断训后根据实际情况复核目标。',
            ['不把漏练量强行补到下一次，也不据此自动改写RM。','保留训练事实与周计划版本，调整有理由并可追溯。'],
            ['interruption_review_days']),
        ('readiness_limits','恢复反馈与力量结论','恢复自述和授权设备摘要属于辅助证据，不等于RM变化。',
            ['睡眠不足或恢复差可用于复核安排，单次HRV或体脂读数不能证明力量下降。','缺少数据时保持不确定性，不虚构训练完成和生理测量。'],[]),
        ('cycle_reassessment','周期结束后的复评','完成周期后回顾实际执行、训练表现、可用时间与下一阶段目标。',
            ['下一周期使用最新画像、RM与完成记录重新生成并确认。','实际训练增长不直接等于最大力量增长，不能自动伪造新RM。'],[]),
    ]
    for key,title,summary,recommendations,keys in entries:
        nodes.append({'id':'training_rule_'+key,'kind':'training_principle','title':title,'aliases':[key],
            'summary':summary,'facts':{'principle':summary,'recommendations':recommendations,
                'governing_service':'backend/periodization.py / backend/progression.py',
                'rule_ids':keys,'numeric_guidance':[f'{k} = {policy[k]}' for k in keys],
                'evidence_scope':'执行数值为练伴产品默认；训练原则参考一般健康成人指南，不能直接扩展为伤病康复处方。'},
            'population':['使用练伴计划的一般成年用户；需要结合个体资料与适用范围'],
            'limitations':['产品流程未经独立临床验证。','版本 '+policy['version']+'；适用性与参数仍需专业审阅和真实用户验证。'],
            'references':[{'source_id':sid,'locator':'训练策略：'+key},
                {'source_id':'acsm-2026','locator':'Individualization；精确执行阈值并非来自该指南'}],
            'exercise_ids':[],'evidence_status':'product_default'})
