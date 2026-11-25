import 'dart:convert';

import 'package:flutter/material.dart';

import 'profile_setup.dart';

/// Manual distance pilot. No camera or uncalibrated joint-angle estimate is used.
class MobilityPage extends StatefulWidget {
  const MobilityPage({super.key, required this.request});
  final FitnessRequest request;

  @override
  State<MobilityPage> createState() => _MobilityPageState();
}

class _MobilityPageState extends State<MobilityPage> {
  Map protocol = {}, settings = {}, summary = {};
  List records = [];
  bool busy = true, practice = false, formConfirmed = false;
  String? error;
  String side = 'left', footwear = 'barefoot';
  String support = 'two_fingers_each_hand', warmup = 'before_training';
  int pain = 0;
  String? pendingSignature;
  Map<String, dynamic>? pendingBody;
  final trials = List.generate(3, (_) => TextEditingController());
  final surface = TextEditingController(text: '平整防滑地面');
  final ruler = TextEditingController(text: '同一厘米尺');
  final assessor = TextEditingController(text: '本人');
  final notes = TextEditingController();
  final painLocation = TextEditingController();

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    for (final c in [
      ...trials,
      surface,
      ruler,
      assessor,
      notes,
      painLocation,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> load() async {
    try {
      final data = await Future.wait([
        widget.request('/mobility/protocol', 'GET', null),
        widget.request('/mobility/settings', 'GET', null),
        widget.request('/mobility/summary', 'GET', null),
        widget.request('/mobility/measurements', 'GET', null),
      ]);
      if (!mounted) return;
      setState(() {
        protocol = data[0] as Map;
        settings = data[1] as Map;
        summary = data[2] as Map;
        records = (data[3] as Map)['items'] as List? ?? [];
        busy = false;
        error = null;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '活动度服务暂不可用：$e';
          busy = false;
        });
      }
    }
  }

  Future<void> action(Future<void> Function() operation) async {
    if (busy) return;
    setState(() => busy = true);
    try {
      await operation();
      await load();
    } catch (e) {
      if (mounted) {
        setState(() {
          error = '$e';
          busy = false;
        });
      }
    }
  }

  void notify(String message) {
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> save() async {
    if (surface.text.trim().isEmpty ||
        ruler.text.trim().isEmpty ||
        assessor.text.trim().isEmpty) {
      notify('请填写场地、尺和测量者，方便下次保持同条件');
      return;
    }
    if (pain > 0 && painLocation.text.trim().isEmpty) {
      notify('请填写疼痛位置；疼痛时立即停止测量');
      return;
    }
    final values = <double>[];
    if (pain == 0) {
      if (!practice || !formConfirmed) {
        notify('请先完成练习并核对3次测量条件');
        return;
      }
      for (final c in trials) {
        final value = double.tryParse(c.text.trim());
        if (value == null ||
            !value.isFinite ||
            value < 0 ||
            value > 30 ||
            (value * 10 - (value * 10).round()).abs() > 0.00000001) {
          notify('请填写3次0–30cm的尺测距离，读到0.1cm；无需换算角度');
          return;
        }
        values.add(value);
      }
    }
    final payload = <String, dynamic>{
      'protocol_id': protocol['id'],
      'protocol_version': protocol['version'],
      'side': side,
      'mode': 'active',
      'loading': 'weight_bearing',
      'source_method': 'manual_tape',
      'unit': 'cm',
      'conditions': {
        'footwear': footwear,
        'support': support,
        'warmup': warmup,
        'surface': surface.text.trim(),
        'ruler': ruler.text.trim(),
        'assessor': assessor.text.trim(),
        'notes': notes.text.trim(),
      },
      'practice_completed': practice,
      'trials': [
        for (final value in values)
          {
            'distance_cm': value,
            'heel_down': formConfirmed,
            'knee_touched_wall': formConfirmed,
            'knee_tracks_second_toe': formConfirmed,
          },
      ],
      'pain_score': pain,
      'pain_location': painLocation.text.trim(),
      'stopped_due_to_pain': pain > 0,
    };
    final nextSignature = jsonEncode(payload);
    if (nextSignature != pendingSignature || pendingBody == null) {
      pendingSignature = nextSignature;
      pendingBody = {
        ...payload,
        'request_id': 'mobility_${DateTime.now().microsecondsSinceEpoch}',
        'observed_at': DateTime.now().toUtc().toIso8601String(),
      };
    }
    await action(() async {
      await widget.request('/mobility/measurements', 'POST', pendingBody);
      pendingBody = null;
      pendingSignature = null;
      if (!mounted) return;
      for (final c in trials) {
        c.clear();
      }
      setState(() {
        practice = false;
        formConfirmed = false;
      });
      notify(pain > 0 ? '已保存停止记录；本条不进入趋势' : '已保存手动尺测记录');
    });
  }

  Widget card(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    ),
  );

  Widget choice(
    String label,
    String value,
    Map<String, String> options,
    ValueChanged<String> changed,
  ) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: DropdownButtonFormField<String>(
      initialValue: value,
      isExpanded: true,
      decoration: InputDecoration(labelText: label),
      items: options.entries
          .map((v) => DropdownMenuItem(value: v.key, child: Text(v.value)))
          .toList(),
      onChanged: busy
          ? null
          : (v) {
              if (v != null) setState(() => changed(v));
            },
    ),
  );

  Widget textField(
    TextEditingController controller,
    String label, {
    bool numeric = false,
  }) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: TextField(
      controller: controller,
      enabled: !busy,
      keyboardType: numeric
          ? const TextInputType.numberWithOptions(decimal: true)
          : TextInputType.text,
      decoration: InputDecoration(labelText: label),
    ),
  );

  Widget trend(String key, String title) {
    final entry = (summary['sides'] as Map? ?? {})[key] as Map? ?? {};
    final latest = entry['latest'] as Map?;
    final baseline = entry['baseline'] as Map?;
    final observation = entry['latest_observation'] as Map?;
    final points = entry['points'] as List? ?? [];
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$title · ${latest == null ? '暂无可比较记录' : '最近有效 ${latest['mean_cm']} cm'}',
          ),
          if (observation != null && observation['comparable'] == false)
            Text(
              '最近一条未进入趋势：${(observation['quality_notes'] as List? ?? []).join('；')}',
            ),
          if (baseline != null)
            Text(
              '个人参考 ${baseline['mean_cm']} cm · ${entry['baseline_mode'] == 'selected' ? '手动指定' : '同条件首条'}',
            ),
          if (entry['comparison_available'] == true)
            Text(
              '相对个人参考 ${((entry['change_cm'] as num?) ?? 0) >= 0 ? '+' : ''}${entry['change_cm']} cm',
            ),
          if (entry['selected_baseline_incompatible'] == true)
            const Text('指定参考与最新条件不同；当前显示同条件首条。'),
          Text('${entry['note'] ?? '同条件积累不同日期的记录后展示变化。'}'),
          if (points.length > 1)
            Wrap(
              spacing: 8,
              children: [
                for (final p in points.reversed.take(7).toList().reversed)
                  Chip(
                    label: Text(
                      '${p['observed_at'].toString().substring(5, 10)} · ${p['mean_cm']} cm',
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }

  Future<bool> confirmDelete(bool all) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(all ? '删除全部活动度记录？' : '删除这条测量？'),
          content: const Text('删除后，个人参考与趋势会按剩余记录更新。'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('删除'),
            ),
          ],
        ),
      ) ??
      false;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('活动度记录')),
    body: busy && protocol.isEmpty
        ? const Center(child: CircularProgressIndicator())
        : RefreshIndicator(
            onRefresh: load,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                if (error != null)
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Column(
                        children: [
                          Text(error!),
                          TextButton(
                            onPressed: busy ? null : load,
                            child: const Text('重试'),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (protocol.isNotEmpty) ...[
                  card('负重膝触墙 · 手动尺测', [
                    const Text('记录主动、负重条件下的大脚趾到墙距离，单位cm。出现疼痛立即停止。'),
                    const SizedBox(height: 8),
                    const Text('摄像头测角尚未校准开放；本页不输出角度、诊断或正常/异常结论。'),
                    ExpansionTile(
                      tilePadding: EdgeInsets.zero,
                      title: const Text('查看测量引导与来源'),
                      children: [
                        for (final step in protocol['steps'] as List? ?? [])
                          Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: Text('$step'),
                          ),
                        Text('协议 ${protocol['id']} · v${protocol['version']}'),
                        const Text(
                          '依据 Konor等，2012；20名健康成人，培训测量者，单次内可靠性研究。App自测与长期变化尚未验证。',
                        ),
                        const SelectableText(
                          'https://pmc.ncbi.nlm.nih.gov/articles/PMC3362988/',
                        ),
                        const Text(
                          '3次极差超过0.5cm提示复测，暂不进入趋势；这是产品质控约定，不是研究的临床阈值。',
                        ),
                      ],
                    ),
                  ]),
                  card('保存设置', [
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('保存我的活动度记录'),
                      subtitle: const Text(
                        '记录属于当前账号；关闭后停止新增并停止向AI提供摘要，已有记录可删除。',
                      ),
                      value: settings['storage_enabled'] == true,
                      onChanged: busy
                          ? null
                          : (v) => action(() async {
                              await widget.request(
                                '/mobility/settings',
                                'PUT',
                                {
                                  'storage_enabled': v,
                                  'ai_context_enabled':
                                      v &&
                                      settings['ai_context_enabled'] == true,
                                },
                              );
                            }),
                    ),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('允许AI使用活动度摘要'),
                      subtitle: const Text(
                        '仅提供日期、侧别、单位、测量质控和可比较趋势，不提供原始备注；AI不能据此诊断或自动加重。',
                      ),
                      value:
                          settings['storage_enabled'] == true &&
                          settings['ai_context_enabled'] == true,
                      onChanged: busy || settings['storage_enabled'] != true
                          ? null
                          : (v) => action(() async {
                              await widget.request(
                                '/mobility/settings',
                                'PUT',
                                {
                                  'storage_enabled': true,
                                  'ai_context_enabled': v,
                                },
                              );
                            }),
                    ),
                  ]),
                  if (settings['storage_enabled'] == true)
                    card('新建测量', [
                      choice('侧别', side, {'left': '左侧', 'right': '右侧'}, (v) {
                        side = v;
                        practice = false;
                        formConfirmed = false;
                      }),
                      choice('鞋袜', footwear, {
                        'barefoot': '赤足',
                        'shoes': '穿鞋（保持同一双）',
                      }, (v) => footwear = v),
                      choice('支撑', support, {
                        'two_fingers_each_hand': '每手两指轻扶墙',
                        'hands_on_wall': '双手扶墙',
                        'none': '不扶墙',
                      }, (v) => support = v),
                      choice('测量时机', warmup, {
                        'before_training': '训练前，未热身',
                        'after_warmup': '相同热身后',
                        'after_training': '训练后',
                      }, (v) => warmup = v),
                      textField(surface, '场地与地面'),
                      textField(ruler, '尺的标识'),
                      textField(assessor, '测量者'),
                      textField(notes, '其他条件（鞋款、热身内容等）'),
                      DropdownButtonFormField<int>(
                        initialValue: pain,
                        decoration: const InputDecoration(
                          labelText: '当前疼痛评分 0–10',
                        ),
                        items: [
                          for (var i = 0; i <= 10; i++)
                            DropdownMenuItem(
                              value: i,
                              child: Text(i == 0 ? '0 · 无疼痛' : '$i · 停止测量'),
                            ),
                        ],
                        onChanged: busy
                            ? null
                            : (v) => setState(() => pain = v ?? 0),
                      ),
                      const SizedBox(height: 12),
                      if (pain > 0) ...[
                        const Text('请立即停止。保存停止记录，无需继续测量；这条记录不进入趋势。'),
                        textField(painLocation, '疼痛位置'),
                      ] else ...[
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          value: practice,
                          onChanged: busy
                              ? null
                              : (v) => setState(() => practice = v ?? false),
                          title: const Text('该侧已练习3次'),
                        ),
                        for (var i = 0; i < 3; i++)
                          textField(
                            trials[i],
                            '第${i + 1}次距离（cm）',
                            numeric: true,
                          ),
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          value: formConfirmed,
                          onChanged: busy
                              ? null
                              : (v) =>
                                    setState(() => formConfirmed = v ?? false),
                          title: const Text('3次均脚跟贴地、膝轻触墙且沿第二趾方向'),
                        ),
                      ],
                      FilledButton.icon(
                        onPressed: busy ? null : save,
                        icon: const Icon(Icons.straighten),
                        label: Text(pain > 0 ? '保存停止记录' : '保存3次手动测量'),
                      ),
                    ]),
                  card('个人参考与趋势', [
                    trend('left', '左侧'),
                    trend('right', '右侧'),
                    const Text('只比较同侧、同协议与同条件的手动记录；变化值不等于临床改善，也不会自动调整训练负荷。'),
                  ]),
                  card('测量历史', [
                    if (records.isEmpty) const Text('暂无记录。'),
                    for (final row in records)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 16),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              '${row['side'] == 'left' ? '左侧' : '右侧'} · ${row['mean_cm'] == null ? '已停止' : '${row['mean_cm']} cm'} · ${row['observed_at'].toString().replaceFirst('T', ' ')}',
                            ),
                            Text(
                              '手动尺测 · 主动 · 负重 · 协议v${row['protocol_version']}',
                            ),
                            Text(
                              '3次：${(row['trials'] as List? ?? []).map((v) => '${v['distance_cm']}').join(' / ')} cm',
                            ),
                            if ((row['pain_score'] as num? ?? 0) > 0)
                              Text(
                                '疼痛 ${row['pain_score']}/10 · ${row['pain_location']} · 已停止',
                              ),
                            for (final note
                                in row['quality_notes'] as List? ?? [])
                              Text('$note'),
                            Wrap(
                              spacing: 8,
                              children: [
                                if (row['comparable'] == true)
                                  TextButton(
                                    onPressed: busy
                                        ? null
                                        : () => action(() async {
                                            await widget.request(
                                              '/mobility/baseline/${row['side']}',
                                              'PUT',
                                              {'record_id': row['id']},
                                            );
                                          }),
                                    child: const Text('设为个人参考'),
                                  ),
                                TextButton(
                                  onPressed: busy
                                      ? null
                                      : () async {
                                          if (!await confirmDelete(false)) {
                                            return;
                                          }
                                          await action(() async {
                                            await widget.request(
                                              '/mobility/measurements/${row['id']}',
                                              'DELETE',
                                              null,
                                            );
                                          });
                                        },
                                  child: const Text('删除记录'),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    if (records.isNotEmpty)
                      TextButton(
                        onPressed: busy
                            ? null
                            : () async {
                                if (!await confirmDelete(true)) return;
                                await action(() async {
                                  await widget.request(
                                    '/mobility/measurements',
                                    'DELETE',
                                    null,
                                  );
                                });
                              },
                        child: const Text('删除全部活动度记录'),
                      ),
                  ]),
                ],
              ],
            ),
          ),
  );
}
