"""Nutrition rule cards sourced from the same registry as the executable service."""
import json

from . import nutrition


def install_nutrition(sources, nodes):
    known = {source['id'] for source in sources}
    for entry in nutrition.SOURCES:
        if entry['id'] in known:
            continue
        sources.append({'id': entry['id'], 'title': entry['title'], 'url': entry['url'],
            'edition': entry['published'], 'section': entry['scope'], 'accessed_on': '2026-10-22',
            'content_use': 'paraphrased_facts', 'licensing_note': '仅以中文概述研究或官方资料中的事实，未复制原文表格、图片或正文。',
            'evidence_type': {'original_research': 'original_study', 'official_guidance': 'guideline',
                              'position_stand': 'position_stand'}[entry['kind']]})
    policy_id = 'nutrition-product-policy'
    if policy_id not in known:
        sources.append({'id': policy_id, 'title': '练伴营养规则与趋势校准产品策略',
            'url': 'https://github.com/hudayu298-wq/ai-train',
            'edition': nutrition.RULE_VERSION, 'section': 'docs/NUTRITION_RULES.md：参数、边界、授权、数据资格、确认与失效检查',
            'accessed_on': '2026-10-22', 'content_use': 'product_policy', 'evidence_type': 'product_policy',
            'licensing_note': '本产品自主制定的保守流程与参数，未宣称为论文阈值或经过临床验证。'})
    ids = {node['id'] for node in nodes}
    for rule in nutrition.rules():
        key = 'nutrition_rule_' + rule['id']
        if key in ids:
            continue
        references = [{'source_id': source_id, 'locator': next(entry['scope'] for entry in nutrition.SOURCES if entry['id'] == source_id)}
                      for source_id in rule['source_ids']]
        if rule['product_default'] or not references:
            references.append({'source_id': policy_id, 'locator': '规则 ' + rule['id'] + '；' + rule['limitations']})
        value = json.dumps(rule['value'], ensure_ascii=False, sort_keys=True)
        nodes.append({'id': key, 'kind': 'nutrition_principle', 'title': rule['label'] + '定量规则',
            'aliases': [rule['id'], '营养目标依据', '饮食趋势校准'],
            'summary': rule['limitations'],
            'facts': {'principle': rule['label'] + '：' + rule['limitations'],
                      'recommendations': ['按个人资料和已保存设置计算；数据不足时不生成自动校准建议。',
                                          '食物仍按数据库确定性换算；仅能记录当天饮食，记录不全不能当作热量不足。'],
                      'governing_service': 'backend/services/nutrition.py / backend/nutrition_guidance.py',
                      'rule_ids': [rule['id']], 'numeric_guidance': [value + ' ' + rule['unit']],
                      'evidence_scope': '产品默认/策略' if rule['product_default'] else '原始研究公式；不是个体消耗实测'},
            'population': [rule['population']],
            'limitations': [rule['limitations'], '版本 ' + rule['version'] + '；本产品未做独立临床验证。'],
            'references': references, 'exercise_ids': [],
            'evidence_status': 'product_default' if rule['product_default'] else 'source_checked'})
