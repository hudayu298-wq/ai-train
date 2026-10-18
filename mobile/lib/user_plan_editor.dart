import 'package:flutter/material.dart';

class UserPlanEditor extends StatefulWidget {
  const UserPlanEditor({
    super.key,
    required this.post,
    required this.onSaved,
    required this.exercises,
    required this.rmRecords,
    this.currentPlan,
  });
  final Future<dynamic> Function(String, Map<String, dynamic>) post;
  final Future<void> Function() onSaved;
  final Map<String, String> exercises;
  final List<dynamic> rmRecords;
  final Map<String, dynamic>? currentPlan;
  @override
  State<UserPlanEditor> createState() => _UserPlanEditorState();
}

class _UserPlanEditorState extends State<UserPlanEditor> {
  final title = TextEditingController();
  final day = TextEditingController();
  final weight = TextEditingController();
  final sets = TextEditingController();
  final reps = TextEditingController();
  final rest = TextEditingController();
  final rmWeight = TextEditingController();
  final rmReps = TextEditingController(text: '1');
  final rmDate = TextEditingController(
    text: DateTime.now().toIso8601String().split('T').first,
  );
  String exercise = 'bench', rmExercise = 'bench';
  bool confirmed = false, busy = false;
  int? editing;
  String? message;
  final List<Map<String, dynamic>> entries = [];
  Map<String, dynamic>? assessment;

  @override
  void initState() {
    super.initState();
    final plan = widget.currentPlan;
    if (plan != null) {
      title.text = plan['name'];
      for (final d in plan['days']) {
        for (final e in d['exercises']) {
          entries.add({'day': d['name'], ...Map<String, dynamic>.from(e)});
        }
      }
    }
  }

  @override
  void dispose() {
    for (final c in [
      title,
      day,
      weight,
      sets,
      reps,
      rest,
      rmWeight,
      rmReps,
      rmDate,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  double numeric(TextEditingController c) {
    final n = double.tryParse(c.text);
    if (n == null || !n.isFinite) throw Exception('请填写有效数值');
    return n;
  }

  int integer(TextEditingController c) {
    final n = int.tryParse(c.text);
    if (n == null) throw Exception('组数、次数与休息秒数请填写整数');
    return n;
  }

  Widget field(String label, TextEditingController c, {bool text = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: TextField(
          controller: c,
          keyboardType: text
              ? TextInputType.text
              : const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(
            labelText: label,
            border: const OutlineInputBorder(),
          ),
        ),
      );
  Widget selector(String label, String value, ValueChanged<String> change) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: DropdownButtonFormField<String>(
          key: ValueKey('$label-$value'),
          initialValue: value,
          decoration: InputDecoration(
            labelText: label,
            border: const OutlineInputBorder(),
          ),
          items: widget.exercises.entries
              .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
              .toList(),
          onChanged: busy
              ? null
              : (v) {
                  if (v != null) setState(() => change(v));
                },
        ),
      );
  Future<void> run(Future<void> Function() work) async {
    if (busy) return;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await work();
    } catch (e) {
      if (mounted) setState(() => message = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Map<String, dynamic> payload() {
    if (editing != null) throw Exception('请先更新正在编辑的动作，再保存或评估');
    if (title.text.trim().isEmpty || entries.isEmpty) {
      throw Exception('请填写计划名称并添加至少一个动作');
    }
    final groups = <String, List<Map<String, dynamic>>>{};
    for (final e in entries) {
      groups.putIfAbsent(e['day'], () => []).add({
        for (final k in [
          'exercise_id',
          'weight_kg',
          'sets',
          'reps',
          'rest_seconds',
        ])
          k: e[k],
      });
    }
    return {
      'name': title.text.trim(),
      'days': [
        for (final d in groups.entries) {'name': d.key, 'exercises': d.value},
      ],
    };
  }

  void addEntry() {
    try {
      if (day.text.trim().isEmpty) throw Exception('请填写训练日名称');
      final w = numeric(weight),
          s = integer(sets),
          r = integer(reps),
          pause = integer(rest);
      if (w <= 0 ||
          w > 500 ||
          s < 1 ||
          s > 20 ||
          r < 1 ||
          r > 100 ||
          pause < 0 ||
          pause > 1800) {
        throw Exception('请检查重量、组次和休息范围');
      }
      setState(() {
        final e = {
          'day': day.text.trim(),
          'exercise_id': exercise,
          'weight_kg': w,
          'sets': s,
          'reps': r,
          'rest_seconds': pause,
        };
        if (editing == null) {
          entries.add(e);
        } else {
          entries[editing!] = e;
        }
        editing = null;
        assessment = null;
        message = null;
      });
    } catch (e) {
      setState(() => message = e.toString());
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('我的 RM 数据', style: Theme.of(context).textTheme.titleLarge),
          const Text('填写已有数据：例如80kg最多完成5次即5RM。普通训练组不等于RM；不需要为使用App专门尝试极限重量。'),
          selector('RM 对应动作变式', rmExercise, (v) => rmExercise = v),
          field('RM 重量 / kg（含杠铃）', rmWeight),
          field('最多完成次数 / 1–10', rmReps),
          field('数据日期 / YYYY-MM-DD', rmDate, text: true),
          CheckboxListTile(
            value: confirmed,
            title: const Text('确认是该重量的最大完成次数'),
            onChanged: busy
                ? null
                : (v) => setState(() => confirmed = v ?? false),
          ),
          FilledButton(
            onPressed: busy
                ? null
                : () => run(() async {
                    await widget.post('/rm', {
                      'exercise_id': rmExercise,
                      'weight_kg': numeric(rmWeight),
                      'reps': integer(rmReps),
                      'measured_on': rmDate.text.trim(),
                      'confirmed_maximum': confirmed,
                    });
                    await widget.onSaved();
                    if (mounted) {
                      setState(() {
                        assessment = null;
                        message = 'RM已保存，请重新评估计划';
                      });
                    }
                  }),
            child: const Text('保存 RM'),
          ),
          for (final r in widget.rmRecords)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${widget.exercises[r['exercise_id']]} · ${r['weight_kg']}kg × ${r['reps']}RM',
              ),
              subtitle: Text(
                '${r['measured_on']} · ${r['reference_1rm_kg'] == null ? '未确认最大次数，暂不参与评估' : '${r['reps'] == 1 ? '用户提供1RM' : '估算1RM'} ${r['reference_1rm_kg']}kg'}',
              ),
            ),
          const Divider(height: 32),
          Text('自己制定训练计划', style: Theme.of(context).textTheme.titleLarge),
          field('计划名称', title, text: true),
          field('训练日名称（如周一）', day, text: true),
          selector('计划动作', exercise, (v) => exercise = v),
          field('计划重量 / kg', weight),
          field('组数', sets),
          field('每组次数', reps),
          field('组间休息 / 秒', rest),
          OutlinedButton(
            onPressed: busy ? null : addEntry,
            child: Text(editing == null ? '添加到计划' : '更新该动作'),
          ),
          for (int i = 0; i < entries.length; i++)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${entries[i]['day']} · ${widget.exercises[entries[i]['exercise_id']]}',
              ),
              subtitle: Text(
                '${entries[i]['weight_kg']}kg · ${entries[i]['sets']} × ${entries[i]['reps']} · 休息${entries[i]['rest_seconds']}秒',
              ),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  IconButton(
                    icon: const Icon(Icons.edit_outlined),
                    onPressed: busy
                        ? null
                        : () => setState(() {
                            final e = entries[i];
                            editing = i;
                            day.text = e['day'];
                            exercise = e['exercise_id'];
                            weight.text = '${e['weight_kg']}';
                            sets.text = '${e['sets']}';
                            reps.text = '${e['reps']}';
                            rest.text = '${e['rest_seconds']}';
                          }),
                  ),
                  IconButton(
                    icon: const Icon(Icons.delete_outline),
                    onPressed: busy
                        ? null
                        : () => setState(() {
                            entries.removeAt(i);
                            editing = null;
                            assessment = null;
                          }),
                  ),
                ],
              ),
            ),
          OutlinedButton(
            onPressed: busy
                ? null
                : () => run(() async {
                    final result = await widget.post(
                      '/plans/assess',
                      payload(),
                    );
                    if (mounted) {
                      setState(
                        () => assessment = Map<String, dynamic>.from(result),
                      );
                    }
                  }),
            child: const Text('仅评估草稿'),
          ),
          FilledButton(
            onPressed: busy
                ? null
                : () => run(() async {
                    final result = await widget.post('/plans', payload());
                    await widget.onSaved();
                    if (mounted) {
                      setState(() {
                        assessment = Map<String, dynamic>.from(
                          result['assessment'],
                        );
                        message = '用户计划已保存';
                      });
                    }
                  }),
            child: const Text('保存我的计划并评估'),
          ),
          if (message != null) Text(message!),
          if (assessment != null) ...[
            Text(assessment!['note']),
            for (final item in assessment!['items'])
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(
                  '${item['day']} · ${widget.exercises[item['exercise_id']]}',
                ),
                subtitle: Text(
                  '${item['load_percent'] == null ? '暂无可用RM评估' : '相对负荷 ${item['load_percent']}% · 1RM参考 ${item['reference_1rm_kg']}kg'}\n${item['message']}',
                ),
              ),
          ],
        ],
      ),
    ),
  );
}
