import 'package:flutter/material.dart';

class UserPlanEditor extends StatefulWidget {
  const UserPlanEditor({
    super.key,
    required this.post,
    required this.onSaved,
    required this.exercises,
    this.rmRecords = const [],
    this.compact = false,
    this.autoGenerate = false,
    this.exerciseDetails = const {},
    this.currentPlan,
  });
  final Future<dynamic> Function(String, Map<String, dynamic>) post;
  final Future<void> Function() onSaved;
  final Map<String, String> exercises;
  final Map<String, Map<String, dynamic>> exerciseDetails;
  final List<dynamic> rmRecords;
  final bool compact, autoGenerate;
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
  String exercise = 'bench';
  String movementCategory = '', bodyRegion = '';
  bool busy = false, editingCurrent = false;
  int? editing;
  String? message;
  final List<Map<String, dynamic>> entries = [];
  Map<String, dynamic>? assessment;
  Map<String, dynamic>? aiDraft;
  String? generationId, basePlanId;

  @override
  void initState() {
    super.initState();
    exercise = widget.exercises.keys.firstOrNull ?? '';
    final plan = widget.currentPlan;
    if (plan != null) {
      basePlanId = plan['id'];
      if (!widget.compact && plan['source'] == 'ai') aiDraft = plan;
      title.text = plan['name'];
      for (final d in plan['days']) {
        for (final e in d['exercises']) {
          entries.add({'day': d['name'], ...Map<String, dynamic>.from(e)});
        }
      }
    }
    if (widget.autoGenerate) {
      WidgetsBinding.instance.addPostFrameCallback((_) => generate());
    }
  }

  String movementFor(String id) =>
      widget.exerciseDetails[id]?['movement_pattern'] as String? ?? '未分类';

  List<String> regionsFor(String id) =>
      (widget.exerciseDetails[id]?['body_regions'] as List? ?? [])
          .map((v) => '$v')
          .toList();

  List<String> get movementCategories =>
      (widget.exercises.keys
          .where(
            (id) => bodyRegion.isEmpty || regionsFor(id).contains(bodyRegion),
          )
          .map(movementFor)
          .toSet()
          .toList()
        ..sort());

  List<String> get bodyRegions =>
      (widget.exercises.keys
          .where(
            (id) =>
                movementCategory.isEmpty || movementFor(id) == movementCategory,
          )
          .expand(regionsFor)
          .toSet()
          .toList()
        ..sort());

  Map<String, String> get filteredExercises => {
    for (final e in widget.exercises.entries)
      if ((movementCategory.isEmpty ||
              movementFor(e.key) == movementCategory) &&
          (bodyRegion.isEmpty || regionsFor(e.key).contains(bodyRegion)))
        e.key: e.value,
  };

  void filterExercises({String? category, String? region}) {
    if (category != null) {
      movementCategory = category;
      if (!bodyRegions.contains(bodyRegion)) bodyRegion = '';
    }
    if (region != null) {
      bodyRegion = region;
      if (!movementCategories.contains(movementCategory)) movementCategory = '';
    }
    normalizeExerciseSelection();
  }

  void normalizeExerciseSelection() {
    if (!filteredExercises.containsKey(exercise)) {
      exercise = filteredExercises.keys.firstOrNull ?? '';
    }
  }

  @override
  void didUpdateWidget(covariant UserPlanEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    final allCategories = widget.exercises.keys.map(movementFor).toSet();
    if (!allCategories.contains(movementCategory)) movementCategory = '';
    if (!bodyRegions.contains(bodyRegion)) bodyRegion = '';
    normalizeExerciseSelection();
  }

  @override
  void dispose() {
    for (final c in [title, day, weight, sets, reps, rest]) {
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
      if (generationId == null && basePlanId != null)
        'base_plan_id': basePlanId,
      'days': [
        for (final d in groups.entries)
          {
            'name': d.key,
            'exercises': d.value,
            for (final original
                in (aiDraft ?? widget.currentPlan)?['days'] ?? [])
              if (original['name'] == d.key)
                for (final key in ['weekday', 'start_time', 'duration_minutes'])
                  if (original[key] != null) key: original[key],
          },
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

  Future<void> generate() => run(() async {
    final result = Map<String, dynamic>.from(
      await widget.post('/plans/generate', {}),
    );
    if (!mounted) return;
    setState(() {
      aiDraft = result;
      generationId = result['generation_id'];
      basePlanId = null;
      title.text = result['name'];
      entries.clear();
      for (final d in result['days']) {
        for (final e in d['exercises']) {
          entries.add({'day': d['name'], ...Map<String, dynamic>.from(e)});
        }
      }
      editing = null;
      assessment = Map<String, dynamic>.from(result['assessment']);
      message = 'AI草稿已生成，请检查下方动作与负荷，确认后保存';
    });
  });

  Widget confirmButton() => FilledButton(
    onPressed: busy
        ? null
        : () => run(() async {
            final result = await widget.post('/plans', payload());
            await widget.onSaved();
            if (mounted) {
              setState(() {
                assessment = Map<String, dynamic>.from(result['assessment']);
                message = '计划已确认保存';
              });
            }
          }),
    child: Text(
      widget.compact ? (aiDraft == null ? '保存修改' : '确认使用这个计划') : '保存我的计划并评估',
    ),
  );

  List<Widget> editorControls() => [
    const Divider(height: 28),
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
      options: {'': '全部训练部位', for (final region in bodyRegions) region: region},
    ),
    selector('计划动作', exercise, (v) => exercise = v, options: filteredExercises),
    if (movementCategory.isNotEmpty || bodyRegion.isNotEmpty)
      Align(
        alignment: Alignment.centerLeft,
        child: TextButton.icon(
          onPressed: busy
              ? null
              : () => setState(() {
                  movementCategory = '';
                  bodyRegion = '';
                  normalizeExerciseSelection();
                }),
          icon: const Icon(Icons.filter_alt_off_outlined, size: 18),
          label: const Text('清除动作筛选'),
        ),
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
              final result = await widget.post('/plans/assess', payload());
              if (mounted) {
                setState(() => assessment = Map<String, dynamic>.from(result));
              }
            }),
      child: const Text('仅评估草稿'),
    ),
    if (!widget.compact) confirmButton(),
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
  ];

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('AI 制定训练计划', style: Theme.of(context).textTheme.titleLarge),
          const Text(
            '根据每周训练日、可用时间、目标和力量水平生成整体周期计划。点击生成会将画像及RM发送到已配置的模型服务，并替换当前未保存草稿；已保存的计划保留。',
          ),
          const SizedBox(height: 12),
          FilledButton.icon(
            icon: const Icon(Icons.auto_awesome),
            label: Text(busy ? '处理中…' : '根据画像生成 AI 计划'),
            onPressed: busy ? null : generate,
          ),
          if (busy) const LinearProgressIndicator(),
          if (message != null)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Text(message!),
            ),
          if (aiDraft != null) ...[
            Text('制定理由：${aiDraft!['rationale']}'),
            if (aiDraft!['cycle_weeks'] != null)
              Text('${aiDraft!['cycle_weeks']}周整体周期'),
            for (final week in aiDraft!['weeks'] ?? []) Text('$week'),
            for (final warning in aiDraft!['risk_warnings'] ?? [])
              Text('风险提示：$warning'),
            Text('热身：${aiDraft!['warmup']}'),
            Text('恢复：${aiDraft!['recovery']}'),
            Text('调整建议：${aiDraft!['progression']}'),
          ],
          if (widget.currentPlan != null && widget.compact && aiDraft == null)
            OutlinedButton.icon(
              onPressed: busy
                  ? null
                  : () => setState(() => editingCurrent = !editingCurrent),
              icon: const Icon(Icons.edit_outlined),
              label: const Text('修改当前计划'),
            ),
          if (!widget.compact || aiDraft != null || editingCurrent) ...[
            if (widget.compact) ...[
              Text(title.text, style: Theme.of(context).textTheme.titleLarge),
              for (final e in entries)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(
                    '${e['day']} · ${widget.exercises[e['exercise_id']] ?? e['exercise_id']}',
                  ),
                  subtitle: Text(
                    '${e['weight_kg'] ?? '待确认'} kg · ${e['sets']}组 × ${e['reps']}次 · 休息${e['rest_seconds']}秒',
                  ),
                ),
              confirmButton(),
              ExpansionTile(
                title: const Text('调整动作与负荷'),
                children: editorControls(),
              ),
            ] else
              ...editorControls(),
          ],
        ],
      ),
    ),
  );
}
