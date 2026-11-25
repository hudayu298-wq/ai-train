import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import 'profile_setup.dart';

class ResearchPage extends StatefulWidget {
  const ResearchPage({super.key, required this.request, this.admin = false});
  final FitnessRequest request;
  final bool admin;
  @override
  State<ResearchPage> createState() => _ResearchPageState();
}

class _ResearchPageState extends State<ResearchPage> {
  Map knowledge = {}, dashboard = {};
  bool busy = false;
  String? message;
  String style = 'balanced';
  final selected = <String>{};
  final query = TextEditingController(
    text: 'resistance training progressive overload systematic review',
  );
  final name = TextEditingController(text: '训练证据与私教策略候选');
  Timer? poll;
  @override
  void initState() {
    super.initState();
    run(() async {});
  }

  @override
  void dispose() {
    query.dispose();
    name.dispose();
    poll?.cancel();
    super.dispose();
  }

  Future<void> load() async {
    final k = await widget.request('/research/knowledge', 'GET', null);
    final d = widget.admin
        ? await widget.request('/research/dashboard', 'GET', null)
        : <String, dynamic>{};
    if (!mounted) {
      return;
    }
    setState(() {
      knowledge = k;
      dashboard = d;
    });
    poll?.cancel();
    if ((d['jobs'] as List? ?? []).any(
      (j) => ['queued', 'running'].contains(j['status']),
    )) {
      poll = Timer(const Duration(seconds: 12), () {
        if (mounted && !busy) {
          run(() async {});
        }
      });
    }
  }

  Future<void> run(Future<void> Function() task) async {
    if (busy) {
      return;
    }
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await task();
      await load();
    } catch (e) {
      if (mounted) {
        setState(() => message = '$e');
      }
    } finally {
      if (mounted) {
        setState(() => busy = false);
      }
    }
  }

  Future<void> review(Map entry, bool approve) async {
    final notes = TextEditingController();
    final text = await showDialog<String>(
      context: context,
      builder: (c) => AlertDialog(
        title: Text(approve ? '审核证据适用性' : '拒绝这条证据'),
        content: TextField(
          controller: notes,
          minLines: 3,
          maxLines: 5,
          maxLength: 1000,
          decoration: const InputDecoration(labelText: '审核理由（至少5字，含人群/局限）'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () {
              if (notes.text.trim().length >= 5) {
                Navigator.pop(c, notes.text.trim());
              }
            },
            child: const Text('提交审核'),
          ),
        ],
      ),
    );
    notes.dispose();
    if (text != null) {
      await run(() async {
        await widget.request(
          '/research/evidence/${entry['id']}/review',
          'POST',
          {'approved': approve, 'notes': text},
        );
      });
    }
  }

  Widget section(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    ),
  );
  Widget evidence(Map e) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(e['claim']),
    subtitle: Text(e['title'] ?? ''),
    children: [
      for (final key in {
        'population': '研究人群',
        'intervention': '干预',
        'comparator': '对照',
        'outcome': '结果',
        'limitations': '局限',
        'source_quote': '摘要原文片段',
      }.entries)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Align(
            alignment: Alignment.centerLeft,
            child: Text('${key.value}：${e[key.key]}'),
          ),
        ),
      SelectableText('${e['url']}'),
      const Text('来源仅为摘要；未自动赋予证据等级。'),
      if (e['status'] != null)
        Text('状态：${e['status']} · ${e['review_notes'] ?? ''}'),
      if (widget.admin)
        Row(
          children: [
            TextButton(
              onPressed: busy ? null : () => review(e, true),
              child: const Text('审核通过'),
            ),
            TextButton(
              onPressed: busy ? null : () => review(e, false),
              child: const Text('拒绝/撤销审核'),
            ),
          ],
        ),
    ],
  );
  Future<void> publish(Map candidate, Map evaluation) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('发布候选版本？'),
        content: const Text(
          '候选已通过当前自动评测。请确认已人工检查证据、适用人群和评测结果。发布后新任务将使用此版本，可回滚。',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(c, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(c, true),
            child: const Text('发布'),
          ),
        ],
      ),
    );
    if (yes == true) {
      await run(() async {
        await widget.request(
          '/research/candidates/${candidate['id']}/publish',
          'POST',
          {
            'evaluation_id': evaluation['id'],
            'expected_release_id': dashboard['active']['id'],
          },
        );
      });
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('研究与私教改进'),
      actions: [
        IconButton(
          onPressed: busy ? null : () => run(() async {}),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (busy) const LinearProgressIndicator(),
        if (message != null) Text(message!),
        section('当前知识版本 · ${knowledge['release_id'] ?? '加载中'}', [
          const Text('私教检索使用已审核发布的证据。研究结论有适用范围，不能代替个人训练反馈。'),
          if ((knowledge['items'] as List? ?? []).isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 12),
              child: Text('尚无已发布证据。私教会说明缺少文献依据。'),
            ),
          for (final e in knowledge['items'] ?? []) evidence(e),
        ]),
        if (widget.admin) ...[
          section('获取研究 · 管理员', [
            TextField(
              controller: query,
              decoration: const InputDecoration(labelText: 'PubMed检索式（建议英文）'),
            ),
            FilledButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      await widget.request('/research/search', 'POST', {
                        'query': query.text,
                        'limit': 3,
                      });
                    }),
              child: const Text('检索并提取候选证据'),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('每日自动检索此主题'),
              subtitle: const Text('开启后每天最多检索一次、3篇摘要，会产生模型费用'),
              value: dashboard['feed']?['enabled'] == true,
              onChanged: busy
                  ? null
                  : (v) => run(() async {
                      await widget.request('/research/feed', 'PUT', {
                        'query': query.text,
                        'limit': 3,
                        'enabled': v,
                        'auto_optimize':
                            dashboard['feed']?['auto_optimize'] == true,
                      });
                    }),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('自动生成改进候选并评测'),
              subtitle: const Text(
                '新增审核证据或累计5条自愿共享反馈时触发，每天最多一次；会产生模型费用，发布仍需确认',
              ),
              value: dashboard['feed']?['auto_optimize'] == true,
              onChanged: busy
                  ? null
                  : (v) => run(() async {
                      await widget.request('/research/feed', 'PUT', {
                        'query': query.text,
                        'limit': 3,
                        'enabled': dashboard['feed']?['enabled'] == true,
                        'auto_optimize': v,
                        'feedback_threshold': 5,
                      });
                    }),
            ),
            const Text('后台每分钟取一个任务。每天最多8项研究任务，其中完整评测最多2次；候选不会自动发布。'),
            for (final j in dashboard['jobs'] ?? [])
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('${j['job_type']} · ${j['status']}'),
                subtitle: Text(
                  '${j['error'] ?? j['result'] ?? j['created_at']}',
                ),
              ),
          ]),
          section('证据审核', [
            for (final e in dashboard['evidence'] ?? []) evidence(e),
            for (final d in dashboard['documents'] ?? [])
              if (['excluded', 'superseded'].contains(d['status']))
                Text('${d['title']} · ${d['status']}'),
          ]),
          section('生成候选策略', [
            TextField(
              controller: name,
              decoration: const InputDecoration(labelText: '候选名称'),
            ),
            SegmentedButton<String>(
              segments: const [
                ButtonSegment(value: 'balanced', label: Text('均衡')),
                ButtonSegment(value: 'concise', label: Text('简洁')),
              ],
              selected: {style},
              onSelectionChanged: busy
                  ? null
                  : (v) => setState(() => style = v.first),
            ),
            const Text('选择已审核证据加入此版本。未选择的条目不会进入新版本。'),
            for (final e in dashboard['evidence'] ?? [])
              if (e['status'] == 'reviewed')
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: selected.contains(e['id']),
                  title: Text(e['claim']),
                  onChanged: busy
                      ? null
                      : (v) => setState(() {
                          if (v == true) {
                            selected.add(e['id']);
                          } else {
                            selected.remove(e['id']);
                          }
                        }),
                ),
            FilledButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      await widget.request('/research/candidates', 'POST', {
                        'name': name.text,
                        'policy': {
                          'answer_style': style,
                          'retrieval_limit': 3,
                          'clarification_limit': 1,
                          'show_sources': true,
                        },
                        'evidence_ids': selected.toList(),
                      });
                    }),
              child: const Text('保存候选版本'),
            ),
            OutlinedButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      await widget.request('/research/optimize', 'POST', {});
                    }),
              child: const Text('依据已授权反馈生成改进并自动评测'),
            ),
            const Text('自动改进仅接收自愿共享的反馈分类计数，不读取全体用户原始对话。'),
          ]),
          section('候选与评测', [
            for (final c in dashboard['candidates'] ?? [])
              ExpansionTile(
                tilePadding: EdgeInsets.zero,
                title: Text(c['name']),
                subtitle: Text('${c['id']}\n基于 ${c['base_release_id']}'),
                children: [
                  Text('策略 ${c['policy']} · ${c['evidence'].length}条证据'),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => run(() async {
                            await widget.request(
                              '/research/candidates/${c['id']}/evaluate',
                              'POST',
                              {},
                            );
                          }),
                    child: const Text('运行真实模型评测'),
                  ),
                  for (final e in dashboard['evaluations'] ?? [])
                    if (e['candidate_id'] == c['id']) ...[
                      Text(
                        '评测 ${e['status']} · ${e['suite_version']} · ${e['duration_seconds']}秒',
                      ),
                      ExpansionTile(
                        title: const Text('查看评测用例与评分理由'),
                        children: [
                          SelectableText(
                            const JsonEncoder.withIndent('  ')
                                .convert(e['variants']),
                          ),
                        ],
                      ),
                      Text('${e['limitations']}'),
                      if (e['status'] == 'passed' &&
                          c['base_release_id'] == dashboard['active']?['id'])
                        FilledButton(
                          onPressed: busy ? null : () => publish(c, e),
                          child: const Text('人工确认并发布'),
                        ),
                    ],
                ],
              ),
          ]),
          section('发布与回滚', [
            for (final r in dashboard['releases'] ?? [])
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text('v${r['version']} · ${r['name']} · ${r['status']}'),
                subtitle: Text('${r['published_at']}'),
                trailing: r['id'] == dashboard['active']?['id']
                    ? TextButton(
                        onPressed: busy
                            ? null
                            : () => run(() async {
                                await widget.request(
                                  '/research/releases/${r['id']}/rollback',
                                  'POST',
                                  {},
                                );
                              }),
                        child: const Text('回滚'),
                      )
                    : null,
              ),
          ]),
        ],
      ],
    ),
  );
}
