import 'dart:convert';

import 'package:flutter/material.dart';

import 'profile_setup.dart';
import 'ui_components.dart';
import 'ui_theme.dart';

String loadReferenceText(dynamic reference) {
  if (reference is! Map) return '';
  final label = '${reference['label'] ?? ''}';
  return reference['needs_calibration'] == true ? '$label · 首训需校准' : label;
}

class RegionalStrengthProfile extends StatefulWidget {
  const RegionalStrengthProfile({super.key, required this.request});
  final FitnessRequest request;

  @override
  State<RegionalStrengthProfile> createState() =>
      RegionalStrengthProfileState();
}

class _StrengthDraft {
  String? exercise;
  int? rir;
  bool confirmed = false, pain = false;
  final weight = TextEditingController();
  final reps = TextEditingController();
  final equipment = TextEditingController();
  final measured = TextEditingController(
    text: DateTime.now()
        .toUtc()
        .add(const Duration(hours: 8))
        .toIso8601String()
        .split('T')
        .first,
  );

  void dispose() {
    for (final c in [weight, reps, equipment, measured]) {
      c.dispose();
    }
  }
}

class RegionalStrengthProfileState extends State<RegionalStrengthProfile> {
  static const regions = {'chest': '胸部', 'back': '背部', 'legs': '腿部'};
  final drafts = {for (final r in regions.keys) r: _StrengthDraft()};
  final sections = GlobalKey<ModuleSectionsState>();
  Map<String, dynamic>? data;
  String? error, savedItems;
  bool loading = true, saving = false;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    for (final draft in drafts.values) {
      draft.dispose();
    }
    super.dispose();
  }

  Future<void> load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final result = Map<String, dynamic>.from(
        await widget.request('/strength-profile', 'GET', null),
      );
      if (!mounted) return;
      for (final item in result['items'] as List? ?? []) {
        final d = drafts[item['region']];
        if (d == null) continue;
        d.exercise = item['exercise_id'];
        d.weight.text = '${item['weight_kg']}';
        d.reps.text = '${item['reps']}';
        d.rir = item['rir'];
        d.equipment.text = '${item['equipment_id'] ?? ''}';
        d.measured.text = '${item['measured_on']}';
        d.pain = item['pain'] == true;
        d.confirmed = item['confirmed'] == true;
      }
      setState(() => data = result);
      if (result['ready'] == true) savedItems = jsonEncode(values());
    } catch (e) {
      if (mounted) setState(() => error = '力量评估加载失败：$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  List<Map<String, dynamic>> values() => [
    for (final r in regions.keys)
      {
        'region': r,
        'exercise_id': drafts[r]!.exercise,
        'weight_kg': double.tryParse(drafts[r]!.weight.text),
        'reps': int.tryParse(drafts[r]!.reps.text),
        'rir': drafts[r]!.rir,
        'measured_on': drafts[r]!.measured.text.trim(),
        'equipment_id': drafts[r]!.equipment.text.trim(),
        'confirmed': drafts[r]!.confirmed,
        'pain': drafts[r]!.pain,
      },
  ];

  List<dynamic> options(String region) =>
      data?['options']?[region] as List? ?? [];

  Map? selected(String region) =>
      options(region)
          .cast<Map>()
          .where((e) => e['id'] == drafts[region]!.exercise)
          .firstOrNull;

  /// Called by the enclosing profile Save. No base-profile completion or generation
  /// proceeds until all three actual performance anchors have been checked.
  Future<void> saveRequired() async {
    try {
      if (loading || saving || data == null) {
        throw Exception('请等待胸、背、腿力量评估加载完成，失败时先重试。');
      }
      final problems = <String>[];
      String? firstProblem;
      final now = DateTime.now().toUtc().add(const Duration(hours: 8));
      final day = DateTime.utc(now.year, now.month, now.day);
      for (final r in regions.keys) {
        final priorCount = problems.length;
        final d = drafts[r]!;
        final w = double.tryParse(d.weight.text), n = int.tryParse(d.reps.text);
        final measured = DateTime.tryParse(d.measured.text.trim());
        final validDate =
            measured != null &&
            RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(d.measured.text.trim()) &&
            measured.toIso8601String().split('T').first ==
                d.measured.text.trim() &&
            !DateTime.utc(
              measured.year,
              measured.month,
              measured.day,
            ).isAfter(day) &&
            day
                    .difference(
                      DateTime.utc(measured.year, measured.month, measured.day),
                    )
                    .inDays <=
                90;
        if (selected(r) == null) problems.add('${regions[r]}请选择一个熟悉的评估动作');
        if (w == null || !w.isFinite || w <= 0 || w > 500) {
          problems.add('${regions[r]}请填写有效重量');
        }
        if (n == null || n < 1 || n > 15) {
          problems.add('${regions[r]}请填写1–15次实际完成次数');
        }
        if (d.rir == null) problems.add('${regions[r]}请选择当时还能完成的次数');
        if (!validDate) problems.add('${regions[r]}请填写近90天内的真实表现日期');
        if (selected(r)?['requires_equipment_id'] == true &&
            d.equipment.text.trim().isEmpty) {
          problems.add('${regions[r]}请注明所用器械编号或名称');
        }
        if (d.pain) problems.add('${regions[r]}这项表现有不适，请选择当前可无不适完成的替代动作');
        if (!d.confirmed) problems.add('${regions[r]}请确认数据来自本人实际完成');
        if (problems.length > priorCount) firstProblem ??= r;
      }
      if (problems.isNotEmpty) {
        sections.currentState?.open(
          regions.keys.toList().indexOf(firstProblem!),
        );
        throw Exception('力量画像尚未补齐：${problems.join('；')}。');
      }
      final items = values();
      if (jsonEncode(items) == savedItems && data!['ready'] == true) return;
      setState(() {
        saving = true;
        error = null;
      });
      final result = Map<String, dynamic>.from(
        await widget.request('/strength-profile', 'PUT', {
          'items': items,
          'base_revision': data!['revision'],
        }),
      );
      if (mounted) {
        setState(() {
          data = result;
          savedItems = jsonEncode(items);
        });
      }
      if (result['ready'] != true) throw Exception('胸、背、腿力量评估仍需补充，请核对提示。');
    } catch (e) {
      if (mounted) setState(() => error = '$e'.replaceFirst('Exception: ', ''));
      rethrow;
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Widget field(
    String region,
    String label,
    TextEditingController c, {
    bool number = true,
  }) => TextField(
    controller: c,
    enabled: !saving,
    keyboardType: number
        ? const TextInputType.numberWithOptions(decimal: true)
        : TextInputType.text,
    decoration: InputDecoration(labelText: '${regions[region]} · $label'),
  );

  Widget regionPanel(String r) {
    final d = drafts[r]!;
    final choice = selected(r);
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              '${regions[r]}力量参考',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<String>(
              key: ValueKey('$r-${d.exercise}'),
              initialValue: choice == null ? null : d.exercise,
              isExpanded: true,
              decoration: InputDecoration(labelText: '${regions[r]} · 评估动作'),
              items: [
                for (final e in options(r))
                  DropdownMenuItem(
                    value: '${e['id']}',
                    child: Text(
                      '${e['name']}',
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
              ],
              onChanged: saving
                  ? null
                  : (v) => setState(() {
                      if (d.exercise == v) return;
                      d.exercise = v;
                      d.weight.clear();
                      d.reps.clear();
                      d.rir = null;
                      d.equipment.clear();
                      d.confirmed = false;
                      d.pain = false;
                    }),
            ),
            const SizedBox(height: 8),
            Text(
              choice?['unit_label'] ?? '选择你熟悉、能提供实际表现的动作，不限定标准三大项。',
              style: const TextStyle(fontSize: 12, color: AppColors.muted),
            ),
            const SizedBox(height: 16),
            AdaptiveFields(
              minWidth: 180,
              children: [
                field(r, '实际重量 / kg', d.weight),
                field(r, '实际完成次数 / 1–15', d.reps),
              ],
            ),
            const SizedBox(height: 16),
            DropdownButtonFormField<int>(
              key: ValueKey('$r-rir-${d.rir}'),
              initialValue: d.rir,
              isExpanded: true,
              decoration: InputDecoration(
                labelText: '${regions[r]} · 当时还能完成几次',
              ),
              items: [
                for (var n = 0; n <= 5; n++)
                  DropdownMenuItem(
                    value: n,
                    child: Text(
                      n == 0
                          ? '0次 · 已达本次极限'
                          : n == 5
                          ? '至少5次 · 比较轻松'
                          : '$n次 · 主观估计',
                    ),
                  ),
              ],
              onChanged: saving ? null : (v) => setState(() => d.rir = v),
            ),
            const SizedBox(height: 16),
            field(r, '表现日期 / YYYY-MM-DD', d.measured, number: false),
            if (choice?['requires_equipment_id'] == true) ...[
              const SizedBox(height: 16),
              field(r, '器械编号或名称', d.equipment, number: false),
            ],
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: d.pain,
              title: Text('${regions[r]}这组有疼痛或不适'),
              onChanged: saving
                  ? null
                  : (v) => setState(() => d.pain = v == true),
            ),
            CheckboxListTile(
              contentPadding: EdgeInsets.zero,
              value: d.confirmed,
              title: Text('确认${regions[r]}数据是本人实际完成，重量口径已核对'),
              onChanged: saving
                  ? null
                  : (v) => setState(() => d.confirmed = v == true),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Divider(height: 32),
      Text('胸、背、腿力量画像 · 必填', style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 8),
      const Text(
        '每块选择一个熟悉动作，填写近期实际完成的重量、次数和余力。可用平时的训练表现，无需专门测试极限。补齐后才会生成有具体建议重量的计划。',
      ),
      const SizedBox(height: 8),
      const Text(
        '三块数据用于估计大致力量与起始负重，不同动作和器械不直接换算成同一个RM。新动作的建议重量仍须首训热身核对。',
        style: TextStyle(fontSize: 12, color: AppColors.muted),
      ),
      if (loading) const LinearProgressIndicator(),
      if (error != null)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(
            error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ),
      if (!loading && data == null)
        OutlinedButton(onPressed: load, child: const Text('重新加载力量评估')),
      if (data != null) ...[
        const SizedBox(height: 16),
        Text(
          data!['ready'] == true
              ? '已保存：胸、背、腿资料齐全'
              : '尚需补齐：${(data!['missing'] as List? ?? []).map((e) => e['label']).join('、')}',
          style: const TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 16),
        ModuleSections(
          key: sections,
          enabled: !saving,
          overviewLabel: '选择评估部位',
          previousLabel: '上个部位',
          nextLabel: '下个部位',
          sections: [
            for (final r in regions.keys)
              ModuleSection(
                title: '${regions[r]}表现',
                description: '选择熟悉动作，填写真实重量、次数与余力',
                child: regionPanel(r),
              ),
          ],
        ),
        const Text(
          '随下方“保存画像”按钮一同保存；这些数据不会自动变成训练日志或实测RM。',
          style: TextStyle(fontSize: 12, color: AppColors.muted),
        ),
      ],
    ],
  );
}
