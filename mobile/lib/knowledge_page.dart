import 'dart:async';
import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'profile_setup.dart';
import 'knowledge_format.dart';

const knowledgeKinds = {
  '': '全部',
  'muscle': '肌肉',
  'joint': '关节',
  'joint_action': '关节动作',
  'bone_landmark': '骨性标志',
  'exercise_guide': '动作知识',
  'training_principle': '训练原则',
  'nutrition_principle': '饮食原则',
  'measurement_principle': '测量与边界',
};

const factNames = {
  'origin': '主要起点',
  'insertion': '主要止点',
  'joint_ids': '关节',
  'action_ids': '关节动作',
  'attachment_scope': '附着点范围',
  'parts': '分部与例外',
  'joint_type': '关节类型',
  'rom_reference': '活动度参考',
  'use_as_video_threshold': '可直接作视频阈值',
  'joint_id': '所属关节',
  'plane': '运动平面',
  'definition': '定义',
  'opposite_id': '相反动作',
  'exercise_id': '动作编号',
  'variant': '动作变式',
  'primary_muscle_ids': '主要训练肌群',
  'assisting_muscle_ids': '参与肌群',
  'stabilizer_muscle_ids': '稳定作用',
  'principle_ids': '相关原则',
  'load_basis': '负重口径',
  'camera_views': '录像机位',
  'observable': '可以观察',
  'not_observable': '不能据此推断',
  'setup': '准备细节',
  'execution': '执行说明',
  'principle': '原则',
  'recommendations': '建议',
  'governing_service': '规则来源',
  'landmark_ids': '相关骨性标志',
  'phase_notes': '各阶段作用与提示',
  'not_crossing': '不跨越的关节',
  'bone': '所属骨骼',
  'region': '身体区域',
  'location': '位置说明',
  'clinical_boundary': '使用边界',
  'numeric_guidance': '定量参数与单位',
  'evidence_scope': '证据范围',
  'rule_ids': '规则编号',
};

const evidenceNames = {
  'textbook': '教材与教学资料',
  'guideline': '指南与官方建议',
  'position_stand': '专业组织立场声明',
  'original_study': '原始研究',
  'product_policy': '练伴产品策略',
  'unspecified': '来源类型未标注',
};

const retrievalNames = {
  'browse': '分类浏览',
  'legacy': '原关键词检索',
  'bm25': '关键词检索',
  'dense': '语义检索',
  'hybrid': '关键词与语义融合',
  'hybrid_rerank': '关键词与语义融合 · 相关性重排',
};

const statusNames = {
  'draft': '待审核',
  'reviewed': '已审核',
  'published': '已发布',
  'queued': '排队中',
  'running': '进行中',
  'completed': '已完成',
  'failed': '未通过',
  'passed': '已通过',
};

const gateNames = {
  'bm25_and_candidate_present': '关键词基线与融合重排均已评测',
  'recall_at_5_at_least_0_85': '留出集前5条召回率达到门槛',
  'not_worse_than_bm25': '整体检索指标不低于关键词基线',
  'critical_cases_complete': '关键问题所需知识全部命中',
  'unsupported_queries_abstain': '缺少依据的问题保持空结果',
  'real_hybrid_rerank_no_fallback': '完整运行融合重排，未降级',
  'no_test_errors': '检索测试无运行错误',
  'no_withdrawn_results': '未返回已撤回资料',
  'benchmark_targets_available': '评测所需知识与来源均可用',
  'evaluation_bindings_unchanged': '知识、模型与评测版本保持一致',
  'accuracy_at_least_90_percent': '回答正确率达到门槛',
  'no_factual_regressions': '未出现原本正确、接入后错误的回答',
  'critical_cases_pass': '关键回答全部通过',
  'citations_grounded': '引用实际检索到的支持资料',
  'same_returned_model': '对比使用同一模型',
  'retrieval_benchmark_passed': '检索专项评测通过',
};

class KnowledgePage extends StatefulWidget {
  const KnowledgePage({super.key, required this.request, this.admin = false});
  final FitnessRequest request;
  final bool admin;
  @override
  State<KnowledgePage> createState() => _KnowledgePageState();
}

class _KnowledgePageState extends State<KnowledgePage> {
  final query = TextEditingController();
  String kind = '';
  Map info = {}, result = {}, admin = {};
  bool busy = false;
  String? error;
  Timer? poll;
  @override
  void initState() {
    super.initState();
    run();
  }

  @override
  void dispose() {
    query.dispose();
    poll?.cancel();
    super.dispose();
  }

  Future<void> run([Future<void> Function()? task]) async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await task?.call();
      final values = await Future.wait([
        widget.request('/knowledge', 'GET', null),
        widget.request(
          '/knowledge/search?q=${Uri.encodeQueryComponent(query.text)}${kind.isEmpty ? '' : '&kind=$kind'}',
          'GET',
          null,
        ),
        if (widget.admin) widget.request('/knowledge/admin', 'GET', null),
      ]);
      if (!mounted) return;
      setState(() {
        info = values[0];
        result = values[1];
        if (widget.admin) admin = values[2];
      });
      poll?.cancel();
      if ((admin['jobs'] as List? ?? []).any(
        (j) => ['queued', 'running'].contains(j['status']),
      )) {
        poll = Timer(const Duration(seconds: 15), () {
          if (mounted) run();
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<String?> notes(String title) async {
    final controller = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(title),
        content: TextField(
          controller: controller,
          minLines: 3,
          maxLines: 5,
          maxLength: 1500,
          decoration: const InputDecoration(labelText: '说明核对的来源、范围和局限（至少10字）'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              if (controller.text.trim().length >= 10) {
                Navigator.pop(c, controller.text.trim());
              }
            },
            child: const Text('提交'),
          ),
        ],
      ),
    );
    // The dialog may still animate out while its text field is mounted.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    controller.dispose();
    return result;
  }

  Future<bool> confirm(String title, String text) async =>
      await showDialog<bool>(
        context: context,
        builder: (c) => AlertDialog(
          title: Text(title),
          content: Text(text),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(c, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(c, true),
              child: const Text('确认'),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> importBundle() async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['json'],
      withData: true,
    );
    if (picked == null || !mounted) return;
    await run(() async {
      final bytes = picked.files.single.bytes;
      if (bytes == null || bytes.length > 1024 * 1024) {
        throw Exception('请选择不超过1MB的JSON知识包');
      }
      await widget.request(
        '/knowledge/bundles',
        'POST',
        jsonDecode(utf8.decode(bytes)),
      );
    });
  }

  Future<void> detail(String id) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => KnowledgeDetail(
          id: id,
          request: widget.request,
          admin: widget.admin,
        ),
      ),
    );
    if (mounted) run();
  }

  Future<void> evaluateVersion(
    String version, {
    bool retrievalOnly = false,
  }) async {
    if (!await confirm(
      retrievalOnly ? '运行检索对比' : '运行知识专项评测',
      retrievalOnly
          ? '比较关键词、语义与融合重排的命中、排序和响应时间。使用服务器本地模型，不调用对话模型；任务可能持续数分钟。'
          : '比较同一模型接入知识前后的回答、引用与拒答，并检查检索质量；会产生模型调用费用。',
    )) {
      return;
    }
    await run(() async {
      await widget.request(
        '/knowledge/bundles/$version/${retrievalOnly ? 'retrieval-evaluate' : 'evaluate'}',
        'POST',
        {},
      );
    });
  }

  Widget retrievalStatus() {
    final runtime = info['retrieval'] as Map? ?? {};
    final actual = result['retrieval'] as Map? ?? {};
    final mode = actual['effective_mode'];
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (mode != null) Text('本次：${retrievalNames[mode] ?? '检索'}'),
          if (actual['fallback_reason'] != null)
            const Text('本次已改用可用的检索方式；语义检索或重排未完整运行。'),
          if (widget.admin) ...[
            Text(
              runtime['assets_present'] == true &&
                      runtime['runtime_installed'] == true
                  ? '本地语义模型与重排模型已就绪'
                  : '语义模型或运行环境尚未就绪，请检查服务器配置',
            ),
            if (actual['latency_ms'] is num)
              Text(
                '本次检索 ${(actual['latency_ms'] as num).toStringAsFixed(0)} ms',
              ),
          ],
        ],
      ),
    );
  }

  Widget reportDetails(Map report, {bool retrieval = false}) {
    final variants = report['variants'] as Map? ?? {};
    String percent(dynamic value) =>
        value is num ? '${(value * 100).toStringAsFixed(1)}%' : '—';
    final summary = retrieval
        ? '${report['version']} · 检索对比'
        : '${report['version']} · 回答对比';
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text(summary),
      subtitle: Text(
        report['passed'] == true || report['status'] == 'passed'
            ? '评测通过'
            : '未通过或尚未完成全部门槛',
      ),
      children: [
        if (retrieval) ...[
          const Text('留出问题 · 前5条结果。召回率表示找到的相关知识比例；MRR与nDCG反映排序质量。'),
          for (final entry in variants.entries)
            if (entry.value is Map)
              Builder(
                builder: (_) {
                  final test = entry.value['test'] as Map? ?? {};
                  final latency = test['latency_ms'] as Map? ?? {};
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(retrievalNames[entry.key] ?? '检索方式'),
                        Text(
                          '召回率 ${percent(test['recall_at_5'])} · MRR ${percent(test['mrr'])} · nDCG ${percent(test['ndcg_at_5'])}',
                        ),
                        Text(
                          '留出 ${test['cases'] ?? '—'} 题 · 中位 ${latency['p50'] is num ? (latency['p50'] as num).toStringAsFixed(0) : '—'} ms · P95 ${latency['p95'] is num ? (latency['p95'] as num).toStringAsFixed(0) : '—'} ms',
                        ),
                        if ((test['fallback_cases'] as List? ?? []).isNotEmpty)
                          const Text('包含降级运行，不能作为完整融合重排的通过结果。'),
                      ],
                    ),
                  );
                },
              ),
        ] else ...[
          Text(
            '模型原有知识 ${variants['model_only']?['correct'] ?? '—'}/${variants['model_only']?['total'] ?? '—'} → 接入知识 ${variants['with_knowledge']?['correct'] ?? '—'}/${variants['with_knowledge']?['total'] ?? '—'}',
          ),
          if (report['retrieval_evaluation'] is Map)
            reportDetails(
              report['retrieval_evaluation'] as Map,
              retrieval: true,
            ),
        ],
        if (report['gates'] is Map)
          for (final gate in (report['gates'] as Map).entries)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Text(
                '${gate.value == true ? '通过' : '未通过'} · ${gateNames[gate.key] ?? '其他版本校验门槛'}',
              ),
            ),
        if (report['limitations'] != null) Text('${report['limitations']}'),
        if (report['detail_rows_omitted'] != true || report['id'] != null)
          TextButton(
            onPressed: () {
              final data = report['detail_rows_omitted'] == true
                  ? widget.request(
                      '/knowledge/${retrieval ? 'retrieval-evaluations' : 'evaluations'}/${report['id']}',
                      'GET',
                      null,
                    )
                  : Future<dynamic>.value(report);
              showDialog<void>(
                context: context,
                builder: (c) => AlertDialog(
                  title: const Text('管理员审计报告'),
                  content: SizedBox(
                    width: 680,
                    child: FutureBuilder<dynamic>(
                      future: data,
                      builder: (_, snapshot) {
                        if (snapshot.hasError) {
                          return Text('报告加载失败：${snapshot.error}');
                        }
                        if (!snapshot.hasData) {
                          return const SizedBox(
                            height: 80,
                            child: Center(child: CircularProgressIndicator()),
                          );
                        }
                        return SingleChildScrollView(
                          child: SelectableText(
                            const JsonEncoder.withIndent('  ')
                                .convert(snapshot.data),
                          ),
                        );
                      },
                    ),
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(c),
                      child: const Text('关闭'),
                    ),
                  ],
                ),
              );
            },
            child: const Text('查看审计数据'),
          ),
      ],
    );
  }

  Widget management() {
    final reports = admin['evaluations'] as List? ?? [];
    final builtin = admin['available_builtin'] as Map? ?? {};
    return ExpansionTile(
      title: const Text('知识审核与评测'),
      subtitle: const Text('管理员 · 审核来源与范围，评测后人工发布'),
      children: [
        const Text('相关性评分和项目内评测不等于证据等级，也不能证明临床效果或全球SOTA。'),
        Wrap(
          spacing: 8,
          children: [
            if (builtin['version'] != null && builtin['registered'] != true)
              OutlinedButton(
                onPressed: busy
                    ? null
                    : () => run(() async {
                        await widget.request(
                          '/knowledge/builtin-candidate',
                          'POST',
                          {},
                        );
                      }),
                child: const Text('登记新版内置知识'),
              ),
            OutlinedButton(
              onPressed: busy ? null : importBundle,
              child: const Text('导入 JSON 知识包'),
            ),
            OutlinedButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      final bundle = await widget.request(
                        '/knowledge/export',
                        'GET',
                        null,
                      );
                      await Clipboard.setData(
                        ClipboardData(
                          text: const JsonEncoder.withIndent('  ')
                              .convert(bundle),
                        ),
                      );
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('已复制当前知识包，导入新包时请修改版本号')),
                        );
                      }
                    }),
              child: const Text('复制当前知识包'),
            ),
            OutlinedButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      await widget.request('/knowledge/index', 'POST', {});
                    }),
              child: const Text('准备当前知识索引'),
            ),
            OutlinedButton(
              onPressed: busy || info['version'] == null
                  ? null
                  : () => evaluateVersion(
                      '${info['version']}',
                      retrievalOnly: true,
                    ),
              child: const Text('对比当前检索'),
            ),
            OutlinedButton(
              onPressed: busy || info['version'] == null
                  ? null
                  : () => evaluateVersion('${info['version']}'),
              child: const Text('评测当前版本'),
            ),
          ],
        ),
        for (final b in admin['bundles'] as List? ?? [])
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${b['id']} · ${statusNames[b['status']] ?? '待检查'}',
                  style: Theme.of(context).textTheme.titleSmall,
                ),
                Wrap(
                  spacing: 6,
                  children: [
                    if (b['status'] == 'draft')
                      TextButton(
                        onPressed: busy
                            ? null
                            : () async {
                                final text = await notes('核对知识包');
                                if (text != null) {
                                  await run(() async {
                                    await widget.request(
                                      '/knowledge/bundles/${b['id']}/review',
                                      'POST',
                                      {'notes': text},
                                    );
                                  });
                                }
                              },
                        child: const Text('审核'),
                      ),
                    if (['reviewed', 'published'].contains(b['status'])) ...[
                      TextButton(
                        onPressed: busy
                            ? null
                            : () => evaluateVersion(
                                '${b['id']}',
                                retrievalOnly: true,
                              ),
                        child: const Text('检索对比'),
                      ),
                      TextButton(
                        onPressed: busy
                            ? null
                            : () => evaluateVersion('${b['id']}'),
                        child: const Text('评测'),
                      ),
                    ],
                    if (b['status'] == 'reviewed' &&
                        reports.any(
                          (r) =>
                              r['version'] == b['id'] &&
                              r['status'] == 'passed',
                        ))
                      TextButton(
                        onPressed: busy
                            ? null
                            : () async {
                                final report = reports.firstWhere(
                                  (r) =>
                                      r['version'] == b['id'] &&
                                      r['status'] == 'passed',
                                );
                                if (await confirm(
                                  '发布知识版本',
                                  '确认将 ${b['id']} 用于之后的私教任务？现有训练记录保留原版本。',
                                )) {
                                  await run(() async {
                                    await widget.request(
                                      '/knowledge/bundles/${b['id']}/activate',
                                      'POST',
                                      {'evaluation_id': report['id']},
                                    );
                                  });
                                }
                              },
                        child: const Text('发布'),
                      ),
                    if (b['id'] == info['version'] &&
                        b['previous_version'] != null)
                      TextButton(
                        onPressed: busy
                            ? null
                            : () async {
                                if (await confirm(
                                  '回滚知识版本',
                                  '恢复到 ${b['previous_version']}，撤回的来源仍停用。',
                                )) {
                                  await run(() async {
                                    await widget.request(
                                      '/knowledge/bundles/${b['id']}/rollback',
                                      'POST',
                                      {},
                                    );
                                  });
                                }
                              },
                        child: const Text('回滚'),
                      ),
                  ],
                ),
              ],
            ),
          ),
        for (final j in admin['jobs'] as List? ?? [])
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              '${{'knowledge_index': '索引准备', 'retrieval_evaluation': '检索对比', 'knowledge_evaluation': '知识评测'}[j['job_type']] ?? '知识任务'} · ${statusNames[j['status']] ?? '待检查'}',
            ),
            subtitle: Text(
              '${j['error'] ?? (j['input'] as Map? ?? {})['version'] ?? ''}',
            ),
          ),
        for (final r in reports) reportDetails(r as Map),
        for (final r in admin['retrieval_evaluations'] as List? ?? [])
          reportDetails(r as Map, retrieval: true),
      ],
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('健身知识库'),
      actions: [
        IconButton(
          onPressed: busy ? null : run,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        if (busy) const LinearProgressIndicator(),
        if (error != null)
          Text(
            error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        Text(
          '${info['name'] ?? '基础知识'}',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        Text(
          '${info['version'] ?? ''} · ${(info['counts'] as Map? ?? {}).values.fold<int>(0, (sum, n) => sum + (n as int))}条',
        ),
        const SizedBox(height: 8),
        Text('${info['scope'] ?? ''}'),
        Text(
          '${info['verification'] ?? ''}',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        TextField(
          controller: query,
          onSubmitted: (_) => run(),
          decoration: InputDecoration(
            labelText: '搜索肌肉、关节或训练问题',
            suffixIcon: IconButton(
              onPressed: busy ? null : run,
              icon: const Icon(Icons.search),
            ),
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 6,
          children: [
            for (final e in knowledgeKinds.entries)
              ChoiceChip(
                label: Text(e.value),
                selected: kind == e.key,
                onSelected: busy
                    ? null
                    : (_) {
                        setState(() => kind = e.key);
                        run();
                      },
              ),
          ],
        ),
        retrievalStatus(),
        for (final i in result['items'] as List? ?? [])
          ListTile(
            title: Text('${i['title']}'),
            subtitle: Text(
              '${knowledgeKinds[i['kind']] ?? i['kind']} · ${i['summary']}',
            ),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => detail(i['id']),
          ),
        if (!busy && (result['items'] as List? ?? []).isEmpty)
          const Padding(
            padding: EdgeInsets.all(20),
            child: Text('没有命中资料，请尝试更具体的肌肉或动作名称。'),
          ),
        if (widget.admin) management(),
      ],
    ),
  );
}

class KnowledgeDetail extends StatefulWidget {
  const KnowledgeDetail({
    super.key,
    required this.id,
    required this.request,
    this.admin = false,
  });
  final String id;
  final FitnessRequest request;
  final bool admin;
  @override
  State<KnowledgeDetail> createState() => _KnowledgeDetailState();
}

class _KnowledgeDetailState extends State<KnowledgeDetail> {
  late Future<dynamic> data;
  bool withdrawing = false;
  Future<void> withdraw(String type, String id, String title) async {
    final controller = TextEditingController();
    final notes = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text('停用$title'),
        content: TextField(
          controller: controller,
          minLines: 3,
          maxLines: 5,
          maxLength: 1500,
          decoration: const InputDecoration(labelText: '说明来源问题与停用原因（至少10字）'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              if (controller.text.trim().length >= 10) {
                Navigator.pop(c, controller.text.trim());
              }
            },
            child: const Text('停用'),
          ),
        ],
      ),
    );
    await Future<void>.delayed(const Duration(milliseconds: 250));
    controller.dispose();
    if (notes == null || !mounted) {
      return;
    }
    setState(() => withdrawing = true);
    try {
      await widget.request('/knowledge/withdrawals', 'POST', {
        'target_type': type,
        'target_id': id,
        'notes': notes,
      });
      if (mounted) {
        Navigator.of(context).pop();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) {
        setState(() => withdrawing = false);
      }
    }
  }

  @override
  void initState() {
    super.initState();
    data = widget.request('/knowledge/items/${widget.id}', 'GET', null);
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('知识详情')),
    body: FutureBuilder<dynamic>(
      future: data,
      builder: (context, snapshot) {
        if (snapshot.hasError) return Center(child: Text('${snapshot.error}'));
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator());
        }
        final result = snapshot.data as Map;
        final item = (result['items'] as List).first as Map;
        final related = {
          for (final i in result['related_items'] as List? ?? [])
            i['id']: i['title'],
        };
        String display(dynamic v) => v is List
            ? v.map(display).join('\n')
            : v is bool
            ? (v ? '是' : '否')
            : '${related[v] ?? {'sagittal': '矢状面', 'frontal': '额状面', 'transverse': '水平面'}[v] ?? v}';
        return ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              '${item['title']}',
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            Text('${item['summary']}'),
            if (item['evidence_status'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  {
                        'source_checked': '已核对来源，未经独立专业验证',
                        'admin_reviewed': '已完成管理员审核，未经临床验证',
                        'product_default': '练伴产品策略 · 精确参数不等于研究统一处方',
                        'not_graded': '尚未评定证据状态',
                      }[item['evidence_status']] ??
                      '证据状态待核对',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ),
            if (widget.admin)
              OutlinedButton(
                onPressed: withdrawing
                    ? null
                    : () => withdraw('item', widget.id, '这条知识'),
                child: const Text('停用这条知识'),
              ),
            for (final f in (item['facts'] as Map).entries)
              if (display(f.value).isNotEmpty &&
                  (widget.admin ||
                      !{
                        'exercise_id',
                        'governing_service',
                        'rule_ids',
                      }.contains(f.key)))
                Padding(
                  padding: const EdgeInsets.only(top: 14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        factNames[f.key] ?? '${f.key}',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      SelectableText(
                        f.key == 'numeric_guidance'
                            ? friendlyValue(f.value)
                            : display(f.value),
                      ),
                    ],
                  ),
                ),
            const Divider(height: 32),
            Text('适用范围与局限', style: Theme.of(context).textTheme.titleMedium),
            Text((item['population'] as List? ?? []).join('；')),
            Text((item['limitations'] as List? ?? []).join('；')),
            const SizedBox(height: 16),
            Text('关联知识', style: Theme.of(context).textTheme.titleMedium),
            Wrap(
              spacing: 6,
              children: [
                for (final e in related.entries)
                  ActionChip(
                    label: Text('${e.value}'),
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => KnowledgeDetail(
                          id: e.key,
                          request: widget.request,
                          admin: widget.admin,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
            const Divider(height: 32),
            Text(
              '来源 · ${result['version']}',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            for (final c in result['citations'] as List? ?? [])
              for (final s in c['sources'] as List? ?? [])
                Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SelectableText(
                        '${s['title']}\n${s['edition']} · ${s['locator']}\n${evidenceNames[s['evidence_type']] ?? (s['content_use'] == 'product_policy' ? '练伴产品策略' : '来源事实的中文概述')}\n${s['publisher'] == null || s['publisher'] == '' ? '' : '${s['publisher']} · '}${s['published_on'] == null ? '' : '发布 ${s['published_on']} · '}核对 ${s['accessed_on']}\n${s['url']}',
                      ),
                      if (s['licensing_note'] != null)
                        Padding(
                          padding: const EdgeInsets.only(top: 6),
                          child: Text(
                            '${s['licensing_note']}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                        ),
                      if (widget.admin)
                        TextButton(
                          onPressed: withdrawing
                              ? null
                              : () => withdraw('source', s['id'], '该来源及全部关联知识'),
                          child: const Text('停用这个来源'),
                        ),
                    ],
                  ),
                ),
          ],
        );
      },
    ),
  );
}
