import 'package:flutter/material.dart';

class UserPlanEditor extends StatefulWidget {
  const UserPlanEditor({
    super.key,
    required this.post,
    required this.onSaved,
    required this.exercises,
    required this.rmRecords,
    this.exerciseDetails = const {},
    this.currentPlan,
  });
  final Future<dynamic> Function(String, Map<String, dynamic>) post;
  final Future<void> Function() onSaved;
  final Map<String, String> exercises;
  final Map<String, Map<String, dynamic>> exerciseDetails;
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
  String movementCategory = '', bodyRegion = '';
  bool confirmed = false, busy = false;
  int? editing;
  String? message;
  final List<Map<String, dynamic>> entries = [];
  Map<String, dynamic>? assessment;
  Map<String, dynamic>? aiDraft;
  String? generationId;

  @override
  void initState() {
    super.initState();
    exercise = widget.exercises.keys.firstOrNull ?? '';
    rmExercise = exercise;
    final plan = widget.currentPlan;
    if (plan != null) {
      generationId = plan['generation_id'];
      if (plan['source'] == 'ai') aiDraft = plan;
      title.text = plan['name'];
      for (final d in plan['days']) {
        for (final e in d['exercises']) {
          entries.add({'day': d['name'], ...Map<String, dynamic>.from(e)});
        }
      }
    }
  }

  String movementFor(String id) =>
      widget.exerciseDetails[id]?['movement_pattern'] as String? ?? '未分类';

  List<String> regionsFor(String id) =>
      (widget.exerciseDetails[id]?['body_regions'] as List? ?? [])
          .map((v) => '$v')
          .toList();

  List<String> get movementCategories =>
      (widget.exercises.keys.map(movementFor).toSet().toList()..sort());

  List<String> get bodyRegions =>
      (widget.exercises.keys.expand(regionsFor).toSet().toList()..sort());

  Map<String, String> get filteredExercises => {
    for (final e in widget.exercises.entries)
      if ((movementCategory.isEmpty ||
              movementFor(e.key) == movementCategory) &&
          (bodyRegion.isEmpty || regionsFor(e.key).contains(bodyRegion)))
        e.key: e.value,
  };

  void filterExercises({String? category, String? region}) {
    movementCategory = category ?? movementCategory;
    bodyRegion = region ?? bodyRegion;
    if (!filteredExercises.containsKey(exercise)) {
      exercise = filteredExercises.keys.firstOrNull ?? '';
    }
  }

  @override
  void didUpdateWidget(covariant UserPlanEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!movementCategories.contains(movementCategory)) movementCategory = '';
    if (!bodyRegions.contains(bodyRegion)) bodyRegion = '';
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
  Widget selector(
    String label,
    String value,
    ValueChanged<String> change, {
    Map<String, String>? options,
  }) {
    final choices = options ?? widget.exercises;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: DropdownButtonFormField<String>(
        key: ValueKey('$label-$value-${choices.keys.join(',')}'),
        initialValue: choices.containsKey(value) ? value : null,
        isExpanded: true,
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
        ),
        items: choices.entries
            .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
            .toList(),
        onChanged: busy || choices.isEmpty
            ? null
            : (v) {
                if (v != null) setState(() => change(v));
              },
      ),
    );
  }

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
      if (generationId != null) 'generation_id': generationId,
      'days': [
        for (final d in groups.entries) {'name': d.key, 'exercises': d.value},
      ],
    };
  }

  void addEntry() {
    try {
      if (!filteredExercises.containsKey(exercise)) {
        throw Exception('请先选择可用的计划动作');
      }
      if (day.text.trim().isEmpty) throw Exception('请填写训练日名称');
      final w = weight.text.trim().isEmpty ? null : numeric(weight),
          s = integer(sets),
          r = integer(reps),
          pause = integer(rest);
      if ((w != null && (w <= 0 || w > 500)) ||
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
          Text('AI 制定训练计划', style: Theme.of(context).textTheme.titleLarge),
          const Text(
            '根据已保存的画像、目标和RM生成一周草稿。点击生成会将画像及RM发送到已配置的模型服务，并替换当前未保存草稿；已保存的计划保留。',
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            icon: const Icon(Icons.auto_awesome),
            label: Text(busy ? '处理中…' : '根据画像生成 AI 计划'),
            onPressed: busy
                ? null
                : () => run(() async {
                    final result = Map<String, dynamic>.from(
                      await widget.post('/plans/generate', {}),
                    );
                    if (!mounted) return;
                    setState(() {
                      aiDraft = result;
                      generationId = result['generation_id'];
                      title.text = result['name'];
                      entries.clear();
                      for (final d in result['days']) {
                        for (final e in d['exercises']) {
                          entries.add({
                            'day': d['name'],
                            ...Map<String, dynamic>.from(e),
                          });
                        }
                      }
                      editing = null;
                      assessment = Map<String, dynamic>.from(
                        result['assessment'],
                      );
                      message = 'AI草稿已生成，请检查下方动作与负荷，确认后保存';
                    });
                  }),
          ),
          if (busy) const LinearProgressIndicator(),
          if (message != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Text(message!),
            ),
          if (aiDraft != null) ...[
            Text('制定理由：${aiDraft!['rationale']}'),
            Text('热身：${aiDraft!['warmup']}'),
            Text('恢复：${aiDraft!['recovery']}'),
            Text('调整建议：${aiDraft!['progression']}'),
          ],
          const Divider(height: 32),
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
          Text('检查与调整计划草稿', style: Theme.of(context).textTheme.titleLarge),
          const Text('重量为空表示待确认；开始该动作前应先填写合适的负荷。'),
          field('计划名称', title, text: true),
          field('训练日名称（如周一）', day, text: true),
          selector(
            '关节动作分类',
            movementCategory,
            (v) => filterExercises(category: v),
            options: {
              '': '全部关节动作',
              for (final category in movementCategories) category: category,
            },
          ),
          selector(
            '训练部位',
            bodyRegion,
            (v) => filterExercises(region: v),
            options: {
              '': '全部训练部位',
              for (final region in bodyRegions) region: region,
            },
          ),
          selector(
            '计划动作',
            exercise,
            (v) => exercise = v,
            options: filteredExercises,
          ),
          Text(
            filteredExercises.isEmpty
                ? '当前分类与部位下没有可用动作，请调整筛选。'
                : '可选 ${filteredExercises.length} 个负重动作。',
          ),
          if (filteredExercises.containsKey(exercise) &&
              widget.exerciseDetails.containsKey(exercise))
            Text(
              '${movementFor(exercise)} · 训练部位：${regionsFor(exercise).join('、')}\n${widget.exerciseDetails[exercise]?['weight_basis'] ?? ''}',
            ),
          field('计划重量 / kg', weight),
          field('组数', sets),
          field('每组次数', reps),
          field('组间休息 / 秒', rest),
          OutlinedButton(
            onPressed: busy || !filteredExercises.containsKey(exercise)
                ? null
                : addEntry,
            child: Text(editing == null ? '添加到计划' : '更新该动作'),
          ),
          for (int i = 0; i < entries.length; i++)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${entries[i]['day']} · ${widget.exercises[entries[i]['exercise_id']]}',
              ),
              subtitle: Text(
                '${entries[i]['weight_kg'] == null ? '重量待确认' : '${entries[i]['weight_kg']}kg'} · ${entries[i]['sets']} × ${entries[i]['reps']} · 休息${entries[i]['rest_seconds']}秒',
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
                            movementCategory = '';
                            bodyRegion = '';
                            weight.text = e['weight_kg'] == null
                                ? ''
                                : '${e['weight_kg']}';
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
                        message = '计划已确认保存';
                      });
                    }
                  }),
            child: const Text('保存我的计划并评估'),
          ),
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
