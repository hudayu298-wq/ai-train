import 'dart:async';

import 'package:flutter/material.dart';

/// Stable round-robin groups; original destination indices bind facts to sets.
List<Map<String, dynamic>> interleaveSteps(List<Map<String, dynamic>> steps) {
  final result = <Map<String, dynamic>>[];
  final visited = <int>{};
  for (final step in steps) {
    final group = step['group'] as int? ?? 0;
    if (group == 0) {
      result.add(step);
      continue;
    }
    if (!visited.add(group)) {
      continue;
    }
    final members = <String, List<Map<String, dynamic>>>{};
    for (final s in steps.where((s) => s['group'] == group)) {
      members.putIfAbsent(s['exercise_id'] as String, () => []).add(s);
    }
    final count = members.values.fold<int>(
      0,
      (a, b) => a > b.length ? a : b.length,
    );
    for (var round = 0; round < count; round++) {
      for (final sets in members.values) {
        if (round < sets.length) {
          result.add(sets[round]);
        }
      }
    }
  }
  return result;
}

/// A local recording aid. Only the workout confirmation page saves facts.
class SetRunner extends StatefulWidget {
  const SetRunner({
    super.key,
    required this.steps,
    required this.onRecorded,
    this.now,
    this.frozen = false,
  });
  final DateTime Function()? now;
  final bool frozen;
  final List<Map<String, dynamic>> steps;
  final void Function(int index, Map<String, dynamic> actual) onRecorded;
  @override
  State<SetRunner> createState() => _SetRunnerState();
}

class _SetRunnerState extends State<SetRunner> {
  final weight = TextEditingController(), reps = TextEditingController();
  final rpe = TextEditingController(), rir = TextEditingController();
  int index = 0;
  bool pain = false, resting = false, finished = false;
  String? error;
  DateTime? restStarted;
  Timer? timer;
  Map<String, dynamic>? recorded;
  DateTime clock() => widget.now?.call() ?? DateTime.now();
  int get elapsed => restStarted == null
      ? 0
      : clock().difference(restStarted!).inSeconds.clamp(0, 1800);
  Map get step => widget.steps[index];
  Map get target => step['target'] as Map? ?? {};
  int get restTarget => (target['rest_seconds'] as num?)?.toInt() ?? 0;

  @override
  void initState() {
    super.initState();
    load();
  }

  void load() {
    final actual = step['actual'] as Map? ?? {};
    weight.text = '${actual['weight_kg'] ?? ''}';
    reps.text = '${actual['reps'] ?? ''}';
    rpe.text = '${actual['rpe'] ?? ''}';
    rir.text = '${actual['rir'] ?? ''}';
    pain = actual['pain'] == true;
    error = null;
  }

  void confirm() {
    final w = double.tryParse(weight.text), r = int.tryParse(reps.text);
    final effort = double.tryParse(rpe.text);
    final reserve = rir.text.trim().isEmpty ? null : int.tryParse(rir.text);
    if (w == null ||
        !w.isFinite ||
        w < 0 ||
        w > 500 ||
        r == null ||
        r < 1 ||
        r > 100 ||
        effort == null ||
        !effort.isFinite ||
        effort < 1 ||
        effort > 10 ||
        (rir.text.trim().isNotEmpty &&
            (reserve == null || reserve < 0 || reserve > 10))) {
      setState(() => error = '请确认实际重量0–500kg、次数1–100、RPE 1–10；RIR可留空或填写0–10。');
      return;
    }
    recorded = {
      'weight_kg': w,
      'reps': r,
      'rpe': effort,
      'rir': reserve,
      'pain': pain,
    };
    widget.onRecorded(index, recorded!);
    if (index == widget.steps.length - 1) {
      setState(() {
        finished = true;
        error = null;
      });
      return;
    }
    setState(() {
      resting = true;
      restStarted = clock();
      error = null;
    });
    timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  void next() {
    timer?.cancel();
    widget.onRecorded(index, {...recorded!, 'rest_seconds': elapsed});
    setState(() {
      resting = false;
      restStarted = null;
      if (index == widget.steps.length - 1) {
        finished = true;
      } else {
        index++;
        load();
      }
    });
  }

  @override
  void dispose() {
    timer?.cancel();
    weight.dispose();
    reps.dispose();
    rpe.dispose();
    rir.dispose();
    super.dispose();
  }

  Widget input(String label, TextEditingController controller) => TextField(
    controller: controller,
    keyboardType: const TextInputType.numberWithOptions(decimal: true),
    decoration: InputDecoration(labelText: label),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('逐组训练')),
    body: SingleChildScrollView(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('这里只填写本机训练草稿，返回后还需确认保存。未填写的组不会视为完成。'),
          Text(
            widget.frozen
                ? '目标已在服务器冻结，后续修改计划不会改变本次目标；如需改用新目标，请返回解除冻结后重新开练。'
                : '本次未冻结计划目标，保存时请复核计划关联。',
          ),
          if (finished) ...[
            const Text('已逐组记录，请返回核对并保存本次训练。'),
            FilledButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('返回确认训练'),
            ),
          ] else ...[
            LinearProgressIndicator(value: index / widget.steps.length),
            Text(
              '${step['name']} · 第${step['set_number']}组（${index + 1}/${widget.steps.length}）',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            if (target.isNotEmpty)
              Text(
                '计划目标：${target['weight_kg'] ?? '重量待确认'}${target['weight_kg'] == null ? '' : ' kg'} × ${target['reps']}次 · 余力${target['target_rir'] ?? '未指定'} · 休息${target['rest_seconds'] ?? '未指定'}秒',
              ),
            Text('${step['weight_basis'] ?? ''}'),
            if (resting) ...[
              Text('已休息 $elapsed 秒 · 参考休息 $restTarget 秒'),
              if (restTarget > 0 && elapsed >= restTarget)
                const Text('参考休息时间已到，是否继续由你确认。'),
              if (pain) const Text('本组记录不适，请暂停相关动作并评估，不要因倒计时继续训练。'),
              FilledButton(
                onPressed: next,
                child: Text(
                  index == widget.steps.length - 1 ? '结束计时并返回核对' : '结束休息，记录下一组',
                ),
              ),
            ] else ...[
              input('本组实际重量 / kg', weight),
              input('本组实际次数', reps),
              input('本组 RPE 1–10', rpe),
              input('本组 RIR（可选）', rir),
              CheckboxListTile(
                value: pain,
                title: const Text('本组出现疼痛或不适'),
                onChanged: (v) => setState(() => pain = v == true),
              ),
              if (error != null) Text(error!),
              FilledButton(onPressed: confirm, child: const Text('确认本组并开始休息')),
            ],
          ],
        ],
      ),
    ),
  );
}
