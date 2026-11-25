import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'profile_setup.dart';
import 'ui_components.dart';

const healthMetrics = {
  'weight_kg': ('体重', 'kg'),
  'body_fat_percent': ('体脂率（估算）', '%'),
  'waist_cm': ('腰围', 'cm'),
  'steps': ('区间步数', 'count'),
  'sleep_hours': ('区间睡眠时长', 'h'),
  'resting_hr_bpm': ('静息心率', 'bpm'),
  'hrv_rmssd_ms': ('HRV · RMSSD', 'ms'),
  'active_minutes': ('区间活动分钟', 'min'),
  'active_energy_kcal': ('区间活动热量（估算）', 'kcal'),
};

class HealthDataPage extends StatefulWidget {
  const HealthDataPage({super.key, required this.request});
  final FitnessRequest request;
  @override
  State<HealthDataPage> createState() => _HealthDataPageState();
}

class _HealthDataPageState extends State<HealthDataPage> {
  Map settings = {}, summary = {};
  List records = [];
  bool busy = true;
  String? message;
  String metric = 'weight_kg', method = 'self_report';
  String sleep = 'unknown', energy = 'unknown', trend = 'none';
  final value = TextEditingController(),
      device = TextEditingController(),
      conditions = TextEditingController();
  final start = TextEditingController(
    text: DateTime.now().toUtc().toIso8601String(),
  );
  final end = TextEditingController();
  final fatigue = TextEditingController(),
      discomfort = TextEditingController(),
      constraints = TextEditingController();
  @override
  void initState() {
    super.initState();
    run(() async {}, notifySaved: false);
  }

  @override
  void dispose() {
    for (final c in [
      value,
      device,
      conditions,
      start,
      end,
      fatigue,
      discomfort,
      constraints,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> load() async {
    final results = await Future.wait([
      widget.request('/health-data/settings', 'GET', null),
      widget.request('/health-data/summary', 'GET', null),
      widget.request('/health-data/measurements', 'GET', null),
    ]);
    if (mounted) {
      setState(() {
        settings = results[0];
        summary = results[1];
        records = results[2]['items'];
        busy = false;
      });
    }
  }

  Future<void> run(
    Future<void> Function() task, {
    bool notifySaved = true,
  }) async {
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await task();
      await load();
      if (mounted && notifySaved) {
        setState(() => message = '已保存');
      }
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

  Future<void> consent({bool? storage, bool? ai}) async {
    final enabled = storage ?? settings['storage_enabled'] == true;
    await widget.request('/health-data/settings', 'PUT', {
      'storage_enabled': enabled,
      'ai_context_enabled':
          enabled && (ai ?? settings['ai_context_enabled'] == true),
    });
  }

  Widget input(String label, TextEditingController c, {bool number = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: TextField(
          controller: c,
          enabled: !busy,
          keyboardType: number
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          decoration: InputDecoration(labelText: label),
        ),
      );
  Widget choice(
    String label,
    String selected,
    Map<String, String> choices,
    ValueChanged<String> change,
  ) => DropdownButtonFormField<String>(
    key: ValueKey('$label:$selected'),
    initialValue: selected,
    decoration: InputDecoration(labelText: label),
    isExpanded: true,
    items: [
      for (final e in choices.entries)
        DropdownMenuItem(value: e.key, child: Text(e.value)),
    ],
    onChanged: busy ? null : (v) => setState(() => change(v!)),
  );
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
  Future<void> importFile() async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['json'],
      withData: true,
    );
    if (picked == null) {
      return;
    }
    final bytes = picked.files.single.bytes;
    if (bytes == null || bytes.length > 1024 * 1024) {
      throw Exception('请选择1MB以内的JSON文件');
    }
    final data = jsonDecode(utf8.decode(bytes));
    await widget.request(
      '/health-data/import',
      'POST',
      data is List ? {'records': data} : data,
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('健康与恢复'),
      actions: [
        IconButton(
          onPressed: busy ? null : () => run(() async {}, notifySaved: false),
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    body: AppContent(
      maxWidth: 800,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (busy) const LinearProgressIndicator(),
          if (message != null)
            Padding(padding: const EdgeInsets.all(8), child: Text(message!)),
          ModuleSections(
            enabled: !busy,
            sections: [
              ModuleSection(
                title: '授权与隐私',
                description: '分别管理保存与AI使用授权',
                child: section('由你决定如何使用', [
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('保存测量与恢复反馈'),
                    value: settings['storage_enabled'] == true,
                    onChanged: busy
                        ? null
                        : (v) => run(() => consent(storage: v)),
                  ),
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('允许私教读取健康摘要'),
                    subtitle: const Text('摘要可能发送给已配置的AI服务，可随时关闭'),
                    value: settings['ai_context_enabled'] == true,
                    onChanged: busy || settings['storage_enabled'] != true
                        ? null
                        : (v) => run(() => consent(ai: v)),
                  ),
                  const Text('体脂、睡眠、HRV和活动热量只作辅助。缺失不当作0，不用一次测量改写RM或饮食目标。'),
                ]),
              ),
              ModuleSection(
                title: '近期趋势',
                description: '查看测量摘要和近期恢复情况',
                child: section('近期趋势', [
                  if ((summary['metrics'] as Map? ?? {}).isEmpty)
                    const Text('还没有可用测量。'),
                  for (final e in (summary['metrics'] as Map? ?? {}).entries)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        '${healthMetrics[e.key]?.$1 ?? e.key} · ${e.value['latest']} ${e.value['unit']}',
                      ),
                      subtitle: Text(
                        '近7天 ${e.value['days_last_7']}天 · 均值 ${e.value['mean_last_7'] ?? '暂无'}\n${e.value['comparison_available'] == true ? '较前7天变化 ${e.value['change']}' : '样本不足，暂不比较'} · ${e.value['provider']} ${e.value['device']}',
                      ),
                    ),
                  for (final c in summary['recent_checkins'] ?? [])
                    Text(
                      '${c['day']} · 疲劳 ${c['fatigue'] ?? '未填'}/10 · ${c['temporary_constraints']}',
                    ),
                ]),
              ),
              if (settings['storage_enabled'] == true) ...[
                ModuleSection(
                  title: '添加测量',
                  description: '手动记录或导入已有来源数据',
                  child: section('添加测量', [
                    choice('指标', metric, {
                      for (final e in healthMetrics.entries)
                        e.key: '${e.value.$1} / ${e.value.$2}',
                    }, (v) => metric = v),
                    input('数值', value, number: true),
                    choice('测量方式', method, {
                      'self_report': '自述',
                      'scale': '体重秤',
                      'bia': '体脂秤/BIA',
                      'wearable': '运动手表',
                      'tape': '软尺',
                      'unknown': '未知',
                    }, (v) => method = v),
                    input('设备名称（可选）', device),
                    input('测量条件（如起床后、空腹）', conditions),
                    input('测量/区间开始时间（ISO 8601，含时区）', start),
                    input('区间结束时间（步数/睡眠/活动必填）', end),
                    const Text('例如 2026-10-19T07:00:00+08:00。区间最长24小时。'),
                    FilledButton(
                      onPressed: busy
                          ? null
                          : () => run(() async {
                              final n = double.tryParse(value.text);
                              if (n == null || !n.isFinite) {
                                throw Exception('请填写有效数值');
                              }
                              await widget.request(
                                '/health-data/measurements',
                                'POST',
                                {
                                  'metric': metric,
                                  'value': n,
                                  'unit': healthMetrics[metric]!.$2,
                                  'observed_at': start.text,
                                  if (end.text.trim().isNotEmpty)
                                    'end_at': end.text.trim(),
                                  'provider': 'manual',
                                  'external_id':
                                      'manual-${DateTime.now().microsecondsSinceEpoch}',
                                  'device': device.text,
                                  'method': method,
                                  'conditions': conditions.text,
                                },
                              );
                            }),
                      child: const Text('保存测量'),
                    ),
                    OutlinedButton.icon(
                      onPressed: busy ? null : () => run(importFile),
                      icon: const Icon(Icons.file_upload_outlined),
                      label: const Text('导入来源记录 · JSON'),
                    ),
                    ExpansionTile(
                      title: const Text('导入格式示例'),
                      children: [
                        SelectableText(
                          jsonEncode({
                            'records': [
                              {
                                'metric': 'weight_kg',
                                'value': 70,
                                'unit': 'kg',
                                'observed_at': '2026-10-19T07:00:00+08:00',
                                'provider': 'file_import',
                                'external_id': 'scale-20261019',
                                'device': '我的体重秤',
                                'method': 'scale',
                              },
                            ],
                          }),
                        ),
                      ],
                    ),
                    const Text(
                      'Health Connect、荣耀/华为健康和Withings尚未连接。可导入已有数据，来源由用户提供，未做厂商验证。',
                    ),
                  ]),
                ),
                ModuleSection(
                  title: '恢复反馈',
                  description: '今天的睡眠感受、疲劳与临时限制',
                  child: section('今天的恢复反馈', [
                    choice('睡眠感受', sleep, {
                      'unknown': '未填',
                      'good': '好',
                      'normal': '一般',
                      'poor': '差',
                    }, (v) => sleep = v),
                    choice('精神状态', energy, {
                      'unknown': '未填',
                      'good': '好',
                      'normal': '一般',
                      'poor': '差',
                    }, (v) => energy = v),
                    input('疲劳程度 / 0–10（可选）', fatigue, number: true),
                    input('不适部位（可选）', discomfort),
                    choice('不适变化', trend, {
                      'none': '无不适',
                      'better': '好转',
                      'same': '相同',
                      'worse': '加重',
                      'unknown': '不确定',
                    }, (v) => trend = v),
                    input('临时限制（如本周出差，只能练两天）', constraints),
                    FilledButton(
                      onPressed: busy
                          ? null
                          : () => run(() async {
                              final f = fatigue.text.trim().isEmpty
                                  ? null
                                  : int.tryParse(fatigue.text);
                              if (fatigue.text.trim().isNotEmpty && f == null) {
                                throw Exception('疲劳请填0–10整数');
                              }
                              await widget.request(
                                '/health-data/checkin',
                                'PUT',
                                {
                                  'sleep_quality': sleep,
                                  'energy': energy,
                                  'fatigue': f,
                                  'discomfort_area': discomfort.text,
                                  'discomfort_trend': trend,
                                  'temporary_constraints': constraints.text,
                                },
                              );
                            }),
                      child: const Text('保存今天的反馈'),
                    ),
                  ]),
                ),
              ],
              ModuleSection(
                title: '记录管理',
                description: '查看或删除最近28天的测量记录',
                child: section('测量记录 · 最近28天', [
                  for (final r in records)
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        '${healthMetrics[r['metric']]?.$1} · ${r['value']} ${r['unit']}',
                      ),
                      subtitle: Text(
                        '${r['observed_at']}\n${r['provider']} · ${r['device']}',
                      ),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline),
                        onPressed: busy
                            ? null
                            : () => run(() async {
                                await widget.request(
                                  '/health-data/measurements/${r['id']}',
                                  'DELETE',
                                  null,
                                );
                              }),
                      ),
                    ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () async {
                            final yes = await showDialog<bool>(
                              context: context,
                              builder: (c) => AlertDialog(
                                title: const Text('清空测量与恢复反馈？'),
                                content: const Text(
                                  '将删除所有测量和恢复反馈。历史对话与训练记录可通过账号与安全管理。',
                                ),
                                actions: [
                                  TextButton(
                                    onPressed: () => Navigator.pop(c, false),
                                    child: const Text('取消'),
                                  ),
                                  TextButton(
                                    onPressed: () => Navigator.pop(c, true),
                                    child: const Text('清空'),
                                  ),
                                ],
                              ),
                            );
                            if (yes == true) {
                              await run(() async {
                                await widget.request(
                                  '/health-data/measurements',
                                  'DELETE',
                                  null,
                                );
                              });
                            }
                          },
                    child: const Text('清空全部测量与恢复反馈'),
                  ),
                ]),
              ),
            ],
          ),
        ],
      ),
    ),
  );
}
