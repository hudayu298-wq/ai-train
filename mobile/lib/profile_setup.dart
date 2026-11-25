import 'package:flutter/material.dart';

import 'ui_components.dart';
import 'training_plan_overview.dart';

typedef FitnessRequest = Future<dynamic> Function(String, String, Object?);

class StrengthProfile extends StatefulWidget {
  const StrengthProfile({
    super.key,
    required this.request,
    required this.exercises,
    required this.records,
    required this.onSaved,
  });
  final FitnessRequest request;
  final Map<String, String> exercises;
  final List<dynamic> records;
  final Future<void> Function() onSaved;
  @override
  State<StrengthProfile> createState() => _StrengthProfileState();
}

class _StrengthProfileState extends State<StrengthProfile> {
  final weight = TextEditingController(),
      reps = TextEditingController(text: '1');
  final measured = TextEditingController(
    text: DateTime.now()
        .toUtc()
        .add(const Duration(hours: 8))
        .toIso8601String()
        .split('T')
        .first,
  );
  String? exercise, error;
  bool confirmed = false, busy = false;
  @override
  void dispose() {
    weight.dispose();
    reps.dispose();
    measured.dispose();
    super.dispose();
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      final w = double.tryParse(weight.text), r = int.tryParse(reps.text);
      if (exercise == null ||
          w == null ||
          !w.isFinite ||
          w <= 0 ||
          w > 500 ||
          r == null ||
          r < 1 ||
          r > 10) {
        throw Exception('请填写动作、有效重量与1–10次的已有RM。');
      }
      await widget.request('/rm', 'POST', {
        'exercise_id': exercise,
        'weight_kg': w,
        'reps': r,
        'measured_on': measured.text,
        'confirmed_maximum': confirmed,
      });
      await widget.onSaved();
      if (mounted) setState(() => error = '力量数据已保存');
    } catch (e) {
      if (mounted) setState(() => error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text('力量水平 · RM', style: Theme.of(context).textTheme.titleLarge),
          const Text(
            '填写已有的力量数据，例如80kg最多完成5次即5RM。普通训练组不等于RM，无需为使用App测试极限。RM未知可以跳过；新计划的起始负重由必填力量画像提供参考。',
          ),
          for (final r in widget.records)
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text(
                '${widget.exercises[r['exercise_id']] ?? r['exercise_id']} · ${r['weight_kg']} kg × ${r['reps']}RM',
              ),
              subtitle: Text(
                '${r['measured_on']} · ${r['reference_1rm_kg'] == null ? '暂不参与负荷计算' : '1RM参考 ${r['reference_1rm_kg']} kg'}',
              ),
            ),
          DropdownButtonFormField<String>(
            initialValue: exercise,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'RM 对应动作变式'),
            items: [
              for (final e in widget.exercises.entries)
                DropdownMenuItem(
                  value: e.key,
                  child: Text(e.value, overflow: TextOverflow.ellipsis),
                ),
            ],
            onChanged: busy ? null : (v) => setState(() => exercise = v),
          ),
          TextField(
            controller: weight,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'RM 重量 / kg（按动作库负重口径）',
            ),
          ),
          TextField(
            controller: reps,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: '最大完成次数 / 1–10'),
          ),
          TextField(
            controller: measured,
            decoration: const InputDecoration(labelText: '测量日期 / YYYY-MM-DD'),
          ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('确认是该重量的最大完成次数'),
            value: confirmed,
            onChanged: busy
                ? null
                : (v) => setState(() => confirmed = v ?? false),
          ),
          if (error != null) Text(error!),
          OutlinedButton(
            onPressed: busy ? null : save,
            child: Text(busy ? '保存中…' : '保存 RM'),
          ),
        ],
      ),
    ),
  );
}

class ProfileSetup extends StatefulWidget {
  const ProfileSetup({
    super.key,
    required this.facts,
    required this.request,
    required this.onSaved,
    this.buttonText = '保存画像',
    this.strength,
    this.beforeSave,
  });
  final Map<String, dynamic> facts;
  final FitnessRequest request;
  final Future<void> Function() onSaved;
  final String buttonText;
  final Widget? strength;
  final Future<void> Function()? beforeSave;
  @override
  State<ProfileSetup> createState() => _ProfileSetupState();
}

class _ProfileSetupState extends State<ProfileSetup> {
  final form = GlobalKey<FormState>();
  final sections = GlobalKey<ModuleSectionsState>();
  final validationErrors = <String, String>{};
  final fields = <String, TextEditingController>{};
  String sex = '',
      trainingSplit = 'auto',
      trainingMethod = 'auto',
      goal = '',
      experience = '',
      recovery = 'normal',
      injury = 'none',
      cooking = 'basic',
      foodBudget = 'unknown',
      eatingOut = 'sometimes';
  final weekdays = <int>{};
  bool busy = false;
  String? error;
  @override
  void initState() {
    super.initState();
    for (final key in [
      'age',
      'height_cm',
      'weight_kg',
      'session_minutes',
      'preferred_time',
      'training_months',
      'sleep_hours',
      'goal_detail',
      'equipment',
      'training_preferences',
      'dietary_preferences',
      'food_allergies',
      'restrictions',
      'movement_constraints',
      'load_increment_kg',
    ]) {
      fields[key] = TextEditingController(text: '${widget.facts[key] ?? ''}');
    }
    sex = widget.facts['sex'] ?? '';
    trainingSplit = widget.facts['training_split'] ?? 'auto';
    trainingMethod = widget.facts['training_method'] ?? 'auto';
    goal = widget.facts['goal'] ?? '';
    experience = widget.facts['experience'] ?? '';
    recovery = widget.facts['recovery_status'] ?? 'normal';
    injury = widget.facts['injury_status'] ?? 'none';
    cooking = widget.facts['cooking_access'] ?? 'basic';
    foodBudget = widget.facts['food_budget'] ?? 'unknown';
    eatingOut = widget.facts['eating_out_frequency'] ?? 'sometimes';
    weekdays.addAll(
      (widget.facts['training_weekdays'] as List? ?? []).cast<int>(),
    );
  }

  @override
  void dispose() {
    for (final c in fields.values) {
      c.dispose();
    }
    super.dispose();
  }

  Widget input(
    String key,
    String label, {
    bool required = false,
    bool numeric = false,
    String? hint,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: TextFormField(
      controller: fields[key],
      enabled: !busy,
      keyboardType: numeric
          ? const TextInputType.numberWithOptions(decimal: true)
          : TextInputType.text,
      decoration: InputDecoration(labelText: label, hintText: hint),
      validator: (v) {
        final text = v?.trim() ?? '';
        String? issue;
        if (required && text.isEmpty) {
          issue = '请填写$label';
        } else if (text.isNotEmpty) {
          const ranges = <String, (num, num)>{
            'age': (18, 90),
            'height_cm': (120, 230),
            'weight_kg': (35, 250),
            'training_months': (0, 600),
            'session_minutes': (15, 180),
            'sleep_hours': (0, 14),
            'load_increment_kg': (0, 20),
          };
          final range = ranges[key];
          if (range != null) {
            final n = num.tryParse(text);
            final integer = [
              'age',
              'training_months',
              'session_minutes',
            ].contains(key);
            if (n == null ||
                !n.isFinite ||
                (integer && int.tryParse(text) == null)) {
              issue = '$label请填写${integer ? '整数' : '有效数字'}';
            } else if (n < range.$1 ||
                n > range.$2 ||
                (key == 'load_increment_kg' && n <= 0)) {
              issue = key == 'load_increment_kg'
                  ? '最小加重幅度需大于0且不超过20kg'
                  : '$label需在${range.$1}–${range.$2}之间';
            }
          } else if (key == 'preferred_time' && normalizeTime(text) == null) {
            issue = '开始时间请填写00:00–23:59，例如19:00';
          } else if (text.length > (key == 'food_allergies' ? 500 : 1000)) {
            issue = '$label内容过长，请缩短后保存';
          }
        }
        if (issue == null) {
          validationErrors.remove(key);
        } else {
          validationErrors[key] = issue;
        }
        return issue;
      },
    ),
  );
  Widget choice(
    String label,
    String value,
    Map<String, String> choices,
    ValueChanged<String> changed,
  ) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: DropdownButtonFormField<String>(
      initialValue: choices.containsKey(value) ? value : null,
      decoration: InputDecoration(labelText: label),
      items: [
        for (final e in choices.entries)
          DropdownMenuItem(value: e.key, child: Text(e.value)),
      ],
      onChanged: busy ? null : (v) => setState(() => changed(v!)),
      validator: (v) {
        if (v == null) {
          validationErrors[label] = '请选择$label';
          return validationErrors[label];
        }
        validationErrors.remove(label);
        return null;
      },
    ),
  );
  String? normalizeTime(String text) {
    final match = RegExp(r'^(\d{1,2}):([0-5]\d)$')
        .firstMatch(text.trim().replaceAll('：', ':'));
    if (match == null || int.parse(match[1]!) > 23) return null;
    return '${match[1]!.padLeft(2, '0')}:${match[2]}';
  }

  Future<void> save() async {
    validationErrors.clear();
    final valid = form.currentState!.validate();
    if (weekdays.isEmpty) validationErrors['weekdays'] = '请至少选择一个每周训练日';
    final minimum =
        {
          'upper_lower': 2,
          'push_pull_legs': 3,
          'bodypart_four': 4,
          'bodypart_five': 5,
        }[trainingSplit] ??
        1;
    if (weekdays.isNotEmpty && weekdays.length < minimum) {
      validationErrors['training_split'] =
          '${splitChoices[trainingSplit]}至少需$minimum个训练日，请调整训练日或分化';
    }
    if (!valid || validationErrors.isNotEmpty) {
      setState(() => error = '画像尚未保存：${validationErrors.values.join('；')}');
      final key = validationErrors.keys.first;
      final group =
          [
            'age',
            'height_cm',
            'weight_kg',
            '用于代谢估算的性别',
            '训练目标',
            '训练经验',
            'goal_detail',
            'training_months',
          ].contains(key)
          ? 0
          : [
              'sleep_hours',
              '近期恢复',
              '伤病情况',
              'restrictions',
              'movement_constraints',
            ].contains(key)
          ? (widget.strength == null ? 2 : 3)
          : [
              'dietary_preferences',
              'food_allergies',
              '做饭条件',
              '饮食预算',
              '外食频率',
            ].contains(key)
          ? (widget.strength == null ? 3 : 4)
          : 1;
      sections.currentState?.open(group);
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    var strengthChecked = false;
    try {
      if (weekdays.isEmpty) throw Exception('请至少选择一个每周训练日。');
      final values = <String, dynamic>{
        'sex': sex,
        'goal': goal,
        'experience': experience,
        'training_split': trainingSplit,
        'training_method': trainingMethod,
        'days': weekdays.length,
        'training_weekdays': weekdays.toList()..sort(),
        'recovery_status': recovery,
        'injury_status': injury,
        'cooking_access': cooking,
        'food_budget': foodBudget,
        'eating_out_frequency': eatingOut,
      };
      for (final entry in fields.entries) {
        final text = entry.value.text.trim();
        if (['age', 'training_months', 'session_minutes'].contains(entry.key)) {
          if (text.isNotEmpty) {
            final n = int.tryParse(text);
            if (n == null) throw Exception('年龄、训练月数和时长请填写整数。');
            values[entry.key] = n;
          }
        } else if ([
          'height_cm',
          'weight_kg',
          'sleep_hours',
          'load_increment_kg',
        ].contains(entry.key)) {
          if (text.isNotEmpty) {
            final n = double.tryParse(text);
            if (n == null || !n.isFinite) throw Exception('请填写有效数值。');
            values[entry.key] = n;
          }
        } else {
          values[entry.key] = entry.key == 'preferred_time'
              ? normalizeTime(text)!
              : text;
        }
      }
      await widget.beforeSave?.call();
      strengthChecked = true;
      await widget.request('/coach/profile', 'PATCH', values);
      await widget.onSaved();
      if (mounted) setState(() => error = '画像已保存');
    } catch (e) {
      if (!strengthChecked && widget.strength != null) {
        sections.currentState?.open(2);
      }
      if (mounted) setState(() => error = '$e'.replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) => Form(
    key: form,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('了解你，安排合适的训练', style: Theme.of(context).textTheme.headlineSmall),
        const Text('时间安排决定每周训练结构，力量数据帮助选择负荷。对话和每次确认的训练会继续完善这份画像。'),
        const SizedBox(height: 16),
        const Text('按分组填写，切换时保留本页输入，最后统一保存。'),
        const SizedBox(height: 12),
        ModuleSections(
          key: sections,
          enabled: !busy,
          sections: [
            ModuleSection(
              title: '基础资料',
              description: '身体数据、目标与训练经历',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  AdaptiveFields(
                    minWidth: 200,
                    maxColumns: 3,
                    children: [
                      input('age', '年龄（18–90岁）', required: true, numeric: true),
                      input(
                        'height_cm',
                        '身高 / cm',
                        required: true,
                        numeric: true,
                      ),
                      input(
                        'weight_kg',
                        '体重 / kg',
                        required: true,
                        numeric: true,
                      ),
                    ],
                  ),
                  choice('用于代谢估算的性别', sex, {
                    'male': '男性',
                    'female': '女性',
                  }, (v) => sex = v),
                  choice('训练目标', goal, {
                    'muscle_gain': '增肌与力量提升',
                    'fat_loss': '减脂与保持肌肉',
                  }, (v) => goal = v),
                  input('goal_detail', '具体希望改善什么', hint: '例如提升卧推表现、改善体能'),
                  choice('训练经验', experience, {
                    'beginner': '新手',
                    'intermediate': '有训练经验',
                  }, (v) => experience = v),
                  input('training_months', '持续训练月数（可选）', numeric: true),
                ],
              ),
            ),
            ModuleSection(
              title: '训练安排',
              description: '每周训练日、时间、器械与偏好',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '每周能在哪些时间训练',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  Wrap(
                    spacing: 8,
                    children: [
                      for (int d = 1; d <= 7; d++)
                        FilterChip(
                          label: Text('周${'一二三四五六日'[d - 1]}'),
                          selected: weekdays.contains(d),
                          onSelected: busy
                              ? null
                              : (v) => setState(
                                  () =>
                                      v ? weekdays.add(d) : weekdays.remove(d),
                                ),
                        ),
                    ],
                  ),
                  input(
                    'preferred_time',
                    '通常开始时间 / HH:MM',
                    required: true,
                    hint: '例如 19:00',
                  ),
                  input(
                    'session_minutes',
                    '每次可训练分钟数 / 15–180',
                    required: true,
                    numeric: true,
                  ),
                  input(
                    'equipment',
                    '可用器械',
                    required: true,
                    hint: '例如健身房杠铃、哑铃、史密斯机',
                  ),
                  input(
                    'load_increment_kg',
                    '可用最小加重幅度 / kg（可选）',
                    numeric: true,
                    hint: '例如杠铃总重每次增加2.5kg',
                  ),
                  input('training_preferences', '训练偏好与不喜欢的动作（可选）'),
                  choice(
                    '训练分化偏好',
                    trainingSplit,
                    splitChoices,
                    (v) => trainingSplit = v,
                  ),
                  const Text(
                    '分化表示每次练哪些部位，不等于每周训练天数。当前周安排需覆盖所选全部分组；额外训练日可重复分组。',
                  ),
                  choice(
                    '组次训练法偏好',
                    trainingMethod,
                    methodChoices,
                    (v) => trainingMethod = v,
                  ),
                  const Text(
                    '常规组：按动作固定组次；主项5×5：一项5组5次；混合：力量主项配增肌辅助。最终仍需适配时间、器械与实际表现。',
                  ),
                ],
              ),
            ),
            if (widget.strength != null)
              ModuleSection(
                title: '力量评估',
                description: '胸、背、腿各一项实际表现，生成计划前必填',
                child: widget.strength!,
              ),
            ModuleSection(
              title: '恢复与限制',
              description: '睡眠、恢复情况与可训练范围',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '恢复与需要留意的情况',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  input('sleep_hours', '平均每晚睡眠小时数（可选）', numeric: true),
                  choice('近期恢复', recovery, {
                    'good': '恢复良好',
                    'normal': '一般',
                    'poor': '疲劳或恢复不足',
                  }, (v) => recovery = v),
                  choice('伤病情况', injury, {
                    'none': '没有已知伤病',
                    'historical': '有历史伤病，目前可训练',
                    'current': '目前有疼痛或训练限制',
                  }, (v) => injury = v),
                  input('restrictions', '伤病或训练限制（可选）'),
                  input('movement_constraints', '哪些动作不适、目前可训练的范围（可选）'),
                  const Text(
                    '这些信息用于风险提示和调整建议，不会直接停止AI评估；明显不适时应暂停相关动作并确认适合的训练范围。',
                  ),
                ],
              ),
            ),
            ModuleSection(
              title: '饮食习惯',
              description: '偏好、过敏、做饭条件与预算',
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  input('dietary_preferences', '饮食偏好（可选）'),
                  input('food_allergies', '食物过敏与禁忌（可选）'),
                  choice('做饭条件', cooking, {
                    'none': '基本不做饭',
                    'basic': '简单烹饪',
                    'full': '可以正常做饭',
                  }, (v) => cooking = v),
                  choice('饮食预算', foodBudget, {
                    'unknown': '未注明',
                    'limited': '优先节省',
                    'normal': '一般',
                    'flexible': '较灵活',
                  }, (v) => foodBudget = v),
                  choice('外食频率', eatingOut, {
                    'rarely': '很少',
                    'sometimes': '有时',
                    'often': '经常',
                  }, (v) => eatingOut = v),
                ],
              ),
            ),
          ],
        ),
        if (error != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(error!),
          ),
        FilledButton(
          onPressed: busy ? null : save,
          child: Text(busy ? '保存中…' : widget.buttonText),
        ),
      ],
    ),
  );
}

class PlanChangeCard extends StatelessWidget {
  const PlanChangeCard({super.key, required this.event, this.onUndo});
  final Map<String, dynamic> event;
  final VoidCallback? onUndo;
  @override
  Widget build(BuildContext context) => Card(
    child: Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            event['status'] == 'applied' ? '下次训练已更新' : '下次训练评估',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          Text('${event['summary']}'),
          for (final c in event['changes'] as List? ?? [])
            Padding(
              padding: const EdgeInsets.only(top: 10),
              child: Text(
                '${c['name']}\n${c['before']['weight_kg'] ?? '待确认'} kg × ${c['before']['reps']}次 → ${c['after']['weight_kg'] ?? '待确认'} kg × ${c['after']['reps']}次（${c['after']['sets']}组）\n${c['reason']}',
              ),
            ),
          if (onUndo != null)
            TextButton(onPressed: onUndo, child: const Text('撤销这次调整')),
        ],
      ),
    ),
  );
}
