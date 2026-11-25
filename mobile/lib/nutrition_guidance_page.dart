import 'package:flutter/material.dart';

import 'profile_setup.dart';
import 'ui_components.dart';
import 'knowledge_format.dart';

class NutritionGuidancePage extends StatefulWidget {
  const NutritionGuidancePage({super.key, required this.request});
  final FitnessRequest request;

  @override
  State<NutritionGuidancePage> createState() => _NutritionGuidancePageState();
}

class _NutritionGuidancePageState extends State<NutritionGuidancePage> {
  Map settings = {}, basis = {}, assessment = {};
  Map? suggestion;
  bool busy = true;
  String? message;
  String? suggestionRequest, confirmationRequest;
  final activity = TextEditingController();
  final protein = TextEditingController();
  final fat = TextEditingController();
  final adjustment = TextEditingController();

  @override
  void initState() {
    super.initState();
    perform(() async {});
  }

  @override
  void dispose() {
    activity.dispose();
    protein.dispose();
    fat.dispose();
    adjustment.dispose();
    super.dispose();
  }

  Future<void> load() async {
    final results = await Future.wait([
      widget.request('/nutrition-guidance/settings', 'GET', null),
      widget.request('/nutrition-guidance/target', 'GET', null),
      widget.request('/nutrition-guidance/calibration', 'GET', null),
      widget.request('/nutrition-guidance/suggestions', 'GET', null),
    ]);
    if (!mounted) return;
    final items = List<Map>.from(results[3]['items'] as List);
    setState(() {
      settings = Map.from(results[0]);
      basis = Map.from(results[1]);
      assessment = Map.from(results[2]);
      final pending = items.where((item) => item['status'] == 'pending');
      suggestion = pending.isEmpty ? null : pending.first;
      activity.text = '${settings['activity_factor']}';
      protein.text = '${settings['protein_g_per_kg']}';
      fat.text = '${settings['fat_g_per_kg']}';
      adjustment.text = settings['energy_adjustment_kcal']?.toString() ?? '';
    });
  }

  Future<void> perform(Future<void> Function() action) async {
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await action();
      await load();
    } catch (error) {
      if (mounted) setState(() => message = '$error');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> save() async {
    final a = double.tryParse(activity.text);
    final p = double.tryParse(protein.text);
    final f = double.tryParse(fat.text);
    final e = adjustment.text.trim().isEmpty
        ? null
        : int.tryParse(adjustment.text);
    if (a == null ||
        p == null ||
        f == null ||
        !a.isFinite ||
        !p.isFinite ||
        !f.isFinite ||
        (adjustment.text.trim().isNotEmpty && e == null)) {
      throw Exception('请填写有效数值，能量调整需为整数');
    }
    await widget.request('/nutrition-guidance/settings', 'PUT', {
      ...settings,
      'activity_factor': a,
      'protein_g_per_kg': p,
      'fat_g_per_kg': f,
      'energy_adjustment_kcal': e,
    });
    suggestionRequest = null;
    confirmationRequest = null;
  }

  Widget number(String label, TextEditingController controller) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: TextField(
      controller: controller,
      enabled: !busy,
      keyboardType: const TextInputType.numberWithOptions(
        decimal: true,
        signed: true,
      ),
      decoration: InputDecoration(labelText: label),
    ),
  );

  Widget panel(String title, List<Widget> children) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          ...children,
        ],
      ),
    ),
  );

  Widget nutrients(Map? values) => values == null
      ? const Text('暂无可用目标，请完善资料或查看提示。')
      : Text(
          '${values['kcal']} kcal/日\n蛋白质 ${values['protein']} g · 脂肪 ${values['fat']} g · 碳水 ${values['carbs']} g',
        );

  bool get suggestionValid {
    final expires = DateTime.tryParse('${suggestion?['expires_at']}');
    return suggestion != null &&
        expires != null &&
        expires.isAfter(DateTime.now()) &&
        assessment['eligible'] == true &&
        suggestion?['assessment']?['data_signature'] ==
            assessment['data_signature'];
  }

  @override
  Widget build(BuildContext context) {
    final rules = List<Map>.from(basis['rules'] as List? ?? []);
    final sources = List<Map>.from(basis['sources'] as List? ?? []);
    return Scaffold(
      appBar: AppBar(title: const Text('营养目标与依据')),
      body: AppContent(
        maxWidth: 800,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (busy) const LinearProgressIndicator(),
            if (message != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 8),
                child: Text(message!),
              ),
            panel('当前目标', [
              nutrients(basis['target'] as Map?),
              const SizedBox(height: 8),
              Text(
                basis['target_source'] == 'confirmed_calibration'
                    ? '来源：已确认的趋势调整'
                    : '来源：公式估算与个人设置',
              ),
              for (final warning in basis['warnings'] as List? ?? [])
                Text('提示：$warning'),
              const SizedBox(height: 8),
              Text(basis['note']?.toString() ?? '营养计划起点；设备消耗不直接叠加。'),
            ]),
            const SizedBox(height: 12),
            ModuleSections(
              enabled: !busy,
              sections: [
                ModuleSection(
                  title: '个人设置',
                  description: '适用情况、营养分配与趋势校准授权',
                  child: panel('个人设置', [
                    const Text('适用人群：健康运动成人，非孕哺期、无进食障碍，且无需肾病等治疗性饮食。'),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<String>(
                      initialValue:
                          settings['eligibility'] as String? ?? 'not_confirmed',
                      key: ValueKey(settings['eligibility']),
                      decoration: const InputDecoration(labelText: '适用情况'),
                      items: const [
                        DropdownMenuItem(
                          value: 'not_confirmed',
                          child: Text('尚未确认'),
                        ),
                        DropdownMenuItem(
                          value: 'eligible',
                          child: Text('我符合上述适用人群'),
                        ),
                        DropdownMenuItem(
                          value: 'needs_professional_review',
                          child: Text('需要专业人员评估'),
                        ),
                      ],
                      onChanged: busy
                          ? null
                          : (value) => setState(() {
                              settings['eligibility'] = value;
                              if (value != 'eligible') {
                                settings['calibration_enabled'] = false;
                              }
                            }),
                    ),
                    number('活动系数（1.2–2.2）', activity),
                    number('蛋白质（1.4–2.0 g/kg/日）', protein),
                    number('脂肪（0.6–1.2 g/kg/日，产品分配）', fat),
                    number('能量调整 kcal/日（留空用默认）', adjustment),
                    const Text('减脂 −500至0；增肌 0至400。默认分别为−250和+200，均为产品起点。'),
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: const Text('授权营养趋势校准'),
                      subtitle: const Text(
                        '使用已授权保存的体重与完整饮食记录；独立于AI摘要授权。保存设置后生效。',
                      ),
                      value: settings['calibration_enabled'] == true,
                      onChanged: busy || settings['eligibility'] != 'eligible'
                          ? null
                          : (value) => setState(
                              () => settings['calibration_enabled'] = value,
                            ),
                    ),
                    FilledButton(
                      onPressed: busy ? null : () => perform(save),
                      child: const Text('保存目标设置'),
                    ),
                  ]),
                ),
                ModuleSection(
                  title: '趋势反馈',
                  description: '查看资格、生成建议并明确确认应用',
                  child: panel('趋势反馈', [
                    const Text(
                      '观察最近14个已结束的完整饮食日；同一来源体重每周至少5天，份量需称重或按标签确认。建议步长100 kcal、48小时有效、两次调整间隔14天，均为产品策略。',
                    ),
                    const SizedBox(height: 8),
                    for (final reason in assessment['reasons'] as List? ?? [])
                      Text('$reason'),
                    if (assessment['weight_trend'] is Map)
                      Text(
                        '体重周变化 ${assessment['weight_trend']['weekly_change_percent']}% · 平均摄入 ${assessment['mean_intake_kcal']} kcal/日',
                      ),
                    const SizedBox(height: 8),
                    OutlinedButton(
                      onPressed: busy || assessment['eligible'] != true
                          ? null
                          : () => perform(() async {
                              suggestionRequest ??=
                                  'nutrition-${DateTime.now().microsecondsSinceEpoch}';
                              await widget.request(
                                '/nutrition-guidance/suggestions',
                                'POST',
                                {'request_id': suggestionRequest},
                              );
                              confirmationRequest = null;
                              suggestionRequest = null;
                            }),
                      child: const Text('生成待确认建议'),
                    ),
                    if (suggestion != null) ...[
                      const Divider(),
                      Text('建议目标 · 有效至 ${suggestion!['expires_at']}'),
                      nutrients(
                        suggestion!['assessment']['proposed_target'] as Map?,
                      ),
                      if (!suggestionValid) const Text('建议已过期或依据变化，请重新生成。'),
                      FilledButton(
                        onPressed: busy || !suggestionValid
                            ? null
                            : () => perform(() async {
                                confirmationRequest ??=
                                    'confirm-${DateTime.now().microsecondsSinceEpoch}';
                                await widget.request(
                                  '/nutrition-guidance/suggestions/${suggestion!['id']}/confirm',
                                  'POST',
                                  {'request_id': confirmationRequest},
                                );
                              }),
                        child: const Text('确认应用建议'),
                      ),
                    ],
                    Text(assessment['note']?.toString() ?? ''),
                  ]),
                ),
                ModuleSection(
                  title: '计算依据',
                  description: '公式步骤、规则版本、来源与适用范围',
                  child: panel('计算过程与规则版本', [
                    Text(basis['version']?.toString() ?? ''),
                    for (final step in basis['steps'] as List? ?? [])
                      Text('${step['label']}：${step['value']} ${step['unit']}'),
                    for (final rule in rules)
                      ExpansionTile(
                        tilePadding: EdgeInsets.zero,
                        title: Text(
                          '${rule['label']} · ${rule['product_default'] == true ? '产品策略' : '研究与指南依据'}',
                        ),
                        children: [
                          Text(
                            '值：${friendlyValue(rule['value'])} ${rule['unit']}\n${rule['population']}\n${rule['limitations']}',
                          ),
                          for (final source in sources.where(
                            (source) => (rule['source_ids'] as List).contains(
                              source['id'],
                            ),
                          ))
                            SelectableText(
                              '${source['title']} (${source['published']})\n${source['url']}\n${source['scope']}',
                            ),
                        ],
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
}
