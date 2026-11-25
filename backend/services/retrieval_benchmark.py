"""Frozen project retrieval evaluation; labels are never supplied to neural models.

Test is the report's primary split. Dev is reported separately. This is a project
benchmark with editorial labels, not an external expert blind trial or a global
SOTA claim. Empty retrieval is assessed separately from generated-answer refusal.
"""
import copy
import hashlib
import json
import math
import os
import platform
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version as package_version

from . import knowledge_store as kb, knowledge_retrieval as retrieval

PATH = Path(__file__).parent.parent / 'data/knowledge_retrieval_benchmark.json'
K = 5
GATE_POLICY = {
    'version': 'retrieval-gates-20261022-v1',
    'primary_split': 'test',
    'candidate_mode': 'hybrid_rerank',
    'baseline_mode': 'bm25',
    'minimum_recall_at_5': 0.85,
    'metric_tolerance': 1e-12,
    'critical_required_coverage': 1.0,
    'unsupported_abstention_accuracy': 1.0,
    'actual_neural_pipeline_required': True,
}
GATE_NAMES = (
    'bm25_and_candidate_present', 'recall_at_5_at_least_0_85',
    'not_worse_than_bm25', 'critical_cases_complete', 'unsupported_queries_abstain',
    'real_hybrid_rerank_no_fallback', 'no_test_errors', 'no_withdrawn_results',
    'benchmark_targets_available', 'evaluation_bindings_unchanged',
)


def suite_hash():
    return hashlib.sha256(PATH.read_bytes()).hexdigest()


def valid_report(report, bundle, withdrawals):
    """Recheck every publication binding; a stale passed flag is insufficient."""
    if not isinstance(report, dict):
        return False
    required_gates = set(GATE_NAMES)
    gates = report.get('gates', {})
    return bool(report.get('passed') is True
        and required_gates <= gates.keys() and all(gates[key] is True for key in required_gates)
        and report.get('suite_hash') == suite_hash()
        and report.get('dataset_hash') == suite_hash()
        and report.get('version') == bundle['version']
        and report.get('fingerprint') == kb.fingerprint(bundle)
        and report.get('pipeline_fingerprint') == retrieval.fingerprint()
        and report.get('model_versions') == retrieval.neural.MANIFEST
        and report.get('gate_policy') == GATE_POLICY
        and report.get('withdrawals') == sorted(withdrawals)
        and report.get('primary_split') == 'test')


def dataset():
    value = json.loads(PATH.read_text(encoding='utf-8'))
    cases = value['cases']
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Benchmark IDs must be unique and nonempty')
    for case in cases:
        relevance = case['relevance']
        abstain = case.get('expected_abstain', False)
        if (case['split'] not in ('dev', 'test') or not case['query'].strip()
                or len(case['query']) > 400 or not case['category']
                or any(type(v) is not int or v not in (1, 2) for v in relevance.values())
                or bool(relevance) == bool(abstain)
                or set(case.get('required_ids', [])) - relevance.keys()
                or len(relevance) > K):
            raise ValueError('Invalid retrieval benchmark case: ' + case['id'])
    if not all(any(c['split'] == split for c in cases) for split in ('dev', 'test')):
        raise ValueError('Both dev and test splits are required')
    return value


def percentile(values, quantile):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * quantile
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def environment():
    packages={}
    for name in ('onnxruntime','tokenizers','numpy'):
        try:
            packages[name]=package_version(name)
        except PackageNotFoundError:
            packages[name]=None
    return {'python':platform.python_version(),'system':platform.system(),'machine':platform.machine(),
        'logical_cpus':os.cpu_count(),'intra_op_threads':max(1,min(2,int(os.environ.get('KNOWLEDGE_CPU_THREADS','1')))),
        'packages':packages,'external_api_calls':0,'execution':'local_cpu',
        'latency_note':'本报告仅代表当前评测机器；不外推手机或云服务器时延。'}


def grade(case, returned_ids, *, withdrawn_ids=()):
    """Binary recall/RR and graded nDCG, with explicit withdrawal exclusions.

    Missing bundle nodes remain in the denominator. Withdrawn labels are excluded
    from relevance metrics but recorded, and cannot make publication pass.
    """
    withdrawn_ids = set(withdrawn_ids)
    returned = list(dict.fromkeys(returned_ids))[:K]
    original = case['relevance']
    relevance = {key: gain for key, gain in original.items() if key not in withdrawn_ids}
    removed = sorted(set(original) & withdrawn_ids)
    found = set(returned) & relevance.keys()
    unsupported = case.get('expected_abstain', False)
    required = case.get('required_ids') or [key for key, gain in original.items() if gain == 2]
    rr = next((1 / rank for rank, key in enumerate(returned, 1) if key in relevance), 0.0)
    gain = lambda value: 2 ** value - 1
    dcg = sum(gain(relevance.get(key, 0)) / math.log2(rank + 1) for rank, key in enumerate(returned, 1))
    idcg = sum(gain(value) / math.log2(rank + 1)
               for rank, value in enumerate(sorted(relevance.values(), reverse=True)[:K], 1))
    scored = bool(relevance) and not unsupported
    return {
        'case_id': case['id'], 'split': case['split'], 'category': case['category'],
        'returned_ids': returned, 'relevant_ids': sorted(relevance), 'hit_ids': sorted(found),
        'withdrawn_label_ids': removed, 'scored_supported': scored,
        'recall_at_5': len(found) / len(relevance) if scored else None,
        'mrr': rr if scored else None, 'ndcg_at_5': dcg / idcg if scored else None,
        'retrieval_hit': bool(found) if scored else None,
        'required_ids': required, 'required_complete': bool(required) and set(required) <= set(returned) and not removed,
        'critical': bool(case.get('critical')), 'expected_abstain': unsupported,
        'abstained': not returned, 'abstention_correct': not returned if unsupported else None,
        'withdrawn_result_ids': sorted(set(returned) & withdrawn_ids),
    }


def aggregate(rows, *, target_ids=(), corpus_ids=()):
    supported = [r for r in rows if r['scored_supported']]
    unsupported = [r for r in rows if r['expected_abstain']]
    critical = [r for r in rows if r['critical']]
    hits = {key for r in rows for key in r['hit_ids']}
    returned = {key for r in rows for key in r['returned_ids']}
    mean = lambda key: sum(r[key] for r in supported) / len(supported) if supported else None
    return {
        'cases': len(rows), 'supported_cases': len(supported), 'unsupported_cases': len(unsupported),
        'unscored_supported_cases': sum(not r['scored_supported'] and not r['expected_abstain'] for r in rows),
        'recall_at_5': mean('recall_at_5'), 'mrr': mean('mrr'), 'ndcg_at_5': mean('ndcg_at_5'),
        'coverage': sum(r['retrieval_hit'] for r in supported) / len(supported) if supported else None,
        'target_coverage': len(hits & set(target_ids)) / len(set(target_ids)) if target_ids else None,
        'corpus_returned_coverage': len(returned & set(corpus_ids)) / len(set(corpus_ids)) if corpus_ids else None,
        'required_cases': sum(bool(r['required_ids']) for r in supported),
        'required_complete_cases': sum(r['required_complete'] for r in supported),
        'critical_cases': len(critical),
        'critical_passed': sum(r['required_complete'] and not r['withdrawn_result_ids'] and not r.get('error') for r in critical),
        'abstention_accuracy': sum(r['abstention_correct'] for r in unsupported) / len(unsupported) if unsupported else None,
        'false_abstentions': sum(r['abstained'] for r in supported),
        'withdrawn_result_count': sum(len(r['withdrawn_result_ids']) for r in rows),
        'errors': sum(bool(r.get('error')) for r in rows),
        'effective_modes': dict(Counter(r.get('effective_mode', 'unknown') for r in rows)),
        'fallback_cases': [r['case_id'] for r in rows if r.get('fallback_reason')],
        'latency_ms': {'p50': percentile([r['elapsed_ms'] for r in rows], 0.5),
                       'p95': percentile([r['elapsed_ms'] for r in rows], 0.95)},
    }


def _actual_mode(row, requested, models, pipeline):
    if (row.get('error') or row.get('effective_mode') != requested
            or row.get('fallback_reason') or row.get('pipeline_fingerprint') != pipeline):
        return False
    if requested in ('dense', 'hybrid', 'hybrid_rerank'):
        if row.get('embedding_model') != models['embedding']['id'] or not row.get('vector_backend'):
            return False
    return requested != 'hybrid_rerank' or row.get('reranker_model') == models['reranker']['id']


def evaluate(connection, bundle, modes=('legacy', 'bm25', 'dense', 'hybrid_rerank')):
    """Run actual scoped retrieval, without any answer-generation API calls."""
    frozen = dataset()
    frozen_hash, bundle_hash = suite_hash(), kb.fingerprint(bundle)
    pipeline = retrieval.fingerprint()
    models = copy.deepcopy(retrieval.neural.MANIFEST)
    if not modes or len(set(modes)) != len(modes) or any(m not in ('legacy', 'bm25', 'dense', 'hybrid', 'hybrid_rerank') for m in modes):
        raise ValueError('Evaluation modes must be unique supported pipelines')
    started = time.perf_counter()
    with connection() as db:
        withdrawals = sorted(kb.blocked(db))
    nodes = {item['id']: item for item in bundle['items']}
    withdrawn_ids = {key for key, item in nodes.items() if not kb.eligible(item, set(withdrawals))}
    # Include withdrawn item IDs even when they are absent from this corpus.
    withdrawn_ids |= {v[len('item:'):] for v in withdrawals if v.startswith('item:')}
    eligible_ids = set(nodes) - withdrawn_ids
    targets = {key for case in frozen['cases'] for key in case['relevance']}
    results = {mode: [] for mode in modes}
    # Dev runs first; test latencies follow dev warmup. Alternating mode order
    # reduces order bias, while preserving actual model/index work in the timings.
    ordered = [c for split in ('dev', 'test') for c in frozen['cases'] if c['split'] == split]
    for number, case in enumerate(ordered):
        for mode in modes if number % 2 == 0 else tuple(reversed(modes)):
            observed = time.perf_counter()
            diagnostic, returned, error = {}, [], None
            try:
                with connection() as db:
                    result = kb.retrieve(db, case['query'], bundle=bundle, mode=mode, limit=K)
                    returned = [item['id'] for item in result['items']]
                    diagnostic = result.get('retrieval', {})
            except Exception as exc:
                # An isolated failed connection is rolled back. A benchmark row is
                # marked as an error, never silently accepted as successful abstention.
                error = type(exc).__name__
            row = grade(case, returned, withdrawn_ids=withdrawn_ids)
            row.update({key: diagnostic.get(key) for key in (
                'effective_mode', 'fallback_reason', 'embedding_model', 'reranker_model',
                'vector_backend', 'pipeline_fingerprint')})
            row.update(query=case['query'], requested_mode=mode, error=error,
                       elapsed_ms=(time.perf_counter() - observed) * 1000)
            if error:
                row['abstention_correct'] = False if row['expected_abstain'] else None
            row['actual_requested_pipeline'] = _actual_mode(row, mode, models, pipeline)
            results[mode].append(row)

    variants = {}
    for mode, rows in results.items():
        variant = {'cases': rows}
        for split in ('dev', 'test'):
            subset = [r for r in rows if r['split'] == split]
            split_targets = {key for c in frozen['cases'] if c['split'] == split for key in c['relevance']} - withdrawn_ids
            variant[split] = aggregate(subset, target_ids=split_targets, corpus_ids=eligible_ids)
            variant[split]['groups'] = {
                group: aggregate([r for r in subset if r['category'] == group], target_ids={
                    key for c in frozen['cases'] if c['split'] == split and c['category'] == group for key in c['relevance']} - withdrawn_ids,
                    corpus_ids=eligible_ids)
                for group in sorted({r['category'] for r in subset})
            }
        variants[mode] = variant

    comparisons = {}
    if 'bm25' in results:
        base = {r['case_id']: r for r in results['bm25'] if r['split'] == 'test'}
        for mode, rows in results.items():
            if mode == 'bm25':
                continue
            comparisons[mode] = []
            for row in rows:
                if row['split'] != 'test':
                    continue
                before = base[row['case_id']]
                changes = {key: row[key] - before[key] for key in ('recall_at_5', 'mrr', 'ndcg_at_5')
                           if row[key] is not None and before[key] is not None}
                regression = any(value < -GATE_POLICY['metric_tolerance'] for value in changes.values())
                regression |= bool(before['abstention_correct'] is True and row['abstention_correct'] is False)
                regression |= bool(before['required_complete'] and not row['required_complete'])
                comparisons[mode].append({'case_id': row['case_id'], 'query': row['query'], 'category': row['category'],
                    'metric_changes': changes, 'regression': regression,
                    'baseline_ids': before['returned_ids'], 'candidate_ids': row['returned_ids'],
                    'lost_relevant_ids': sorted(set(before['hit_ids']) - set(row['hit_ids'])),
                    'gained_relevant_ids': sorted(set(row['hit_ids']) - set(before['hit_ids']))})

    with connection() as db:
        ending_withdrawals = sorted(kb.blocked(db))
    test = variants.get('hybrid_rerank', {}).get('test', {})
    baseline = variants.get('bm25', {}).get('test', {})
    candidate_rows = [r for r in results.get('hybrid_rerank', []) if r['split'] == 'test']
    not_worse = all(test.get(key) is not None and baseline.get(key) is not None
                    and test[key] + GATE_POLICY['metric_tolerance'] >= baseline[key]
                    for key in ('recall_at_5', 'mrr', 'ndcg_at_5'))
    gates = {
        'bm25_and_candidate_present': bool(test and baseline),
        'recall_at_5_at_least_0_85': test.get('recall_at_5') is not None and test['recall_at_5'] >= GATE_POLICY['minimum_recall_at_5'],
        'not_worse_than_bm25': not_worse,
        'critical_cases_complete': bool(test.get('critical_cases')) and test.get('critical_cases') == test.get('critical_passed'),
        'unsupported_queries_abstain': test.get('unsupported_cases', 0) > 0 and test.get('abstention_accuracy') == 1.0,
        'real_hybrid_rerank_no_fallback': bool(candidate_rows) and all(r['actual_requested_pipeline'] for r in candidate_rows),
        'no_test_errors': bool(test) and test.get('errors') == 0 and baseline.get('errors') == 0,
        'no_withdrawn_results': all(not r['withdrawn_result_ids'] for rows in results.values() for r in rows),
        'benchmark_targets_available': not (targets - eligible_ids),
        'evaluation_bindings_unchanged': frozen_hash == suite_hash() and bundle_hash == kb.fingerprint(bundle)
            and pipeline == retrieval.fingerprint() and withdrawals == ending_withdrawals,
    }
    return {
        'suite_version': frozen['version'], 'suite_hash': frozen_hash, 'dataset_hash': frozen_hash,
        'version': bundle['version'], 'fingerprint': bundle_hash, 'pipeline_fingerprint': pipeline,
        'model_versions': models, 'withdrawals': withdrawals, 'primary_split': 'test',
        'environment':environment(),
        'gate_policy': copy.deepcopy(GATE_POLICY), 'variants': variants, 'paired_regressions': comparisons,
        'coverage': {'bundle_items': len(nodes), 'eligible_items': len(eligible_ids), 'labeled_items': len(targets & set(nodes)),
            'label_fraction': len(targets & set(nodes)) / len(nodes) if nodes else 0,
            'unlabeled_item_ids': sorted(set(nodes) - targets), 'missing_target_ids': sorted(targets - set(nodes)),
            'withdrawn_target_ids': sorted(targets & withdrawn_ids)},
        'gates': gates, 'passed': all(gates.values()), 'duration_seconds': time.perf_counter() - started,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'limitations': '项目内编辑的80问相关性基准，20dev/60test，未经外部独立专家盲评。'
            '检索空结果只表示拒检，不证明生成回答的医学拒答或临床安全。'
            '只向模型传递查询与知识正文，不传相关性标签或required_ids。'
            'MRR在前5条计算；nDCG使用2^相关性-1增益。'
            'dev先运行，test时延通常处于热缓存；完整分块/索引/模型加载开销按实际发生计入。'
            '逐题回归均保留；发布主门槛只用test，未据本次结果修改阈值，不宣称全球SOTA。',
    }
