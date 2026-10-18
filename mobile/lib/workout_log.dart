import 'dart:convert';

import 'package:flutter/material.dart';

import 'profile_setup.dart';

import 'package:shared_preferences/shared_preferences.dart';

typedef WorkoutRequest = Future<dynamic> Function(String, String, Object?);

class WorkoutReview extends StatelessWidget {
  const WorkoutReview({super.key, required this.record});
  final Map<String, dynamic> record;

  @override
  Widget build(BuildContext context) {
    final summary = record['summary'] as Map?;
    final ai = record['ai_review'] as Map?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (summary != null) ...[
          Text(
            summary['summary'],
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text('基础复盘 · 按确认记录计算'),
          for (final e in summary['exercises'])
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${e['name']} · ${e['sets']}组 / ${e['reps']}次 · 平均RPE ${e['average_rpe']}',
                  ),
                  Text('记录训练量 ${e['volume_kg']} kg·次'),
                  if (e['comparison'] != null)
                    Text(
                      '对比 ${e['comparison']['day']} 同动作：训练量变化 ${e['comparison']['volume_delta_kg']} kg·次',
                    ),
                  Text(e['next_step']),
                ],
              ),
            ),
          const SizedBox(height: 12),
          Text(summary['note'], style: Theme.of(context).textTheme.bodySmall),
        ],
        if (record['plan_progression'] != null)
          PlanChangeCard(
            event: Map<String, dynamic>.from(record['plan_progression']),
          ),
        if (ai != null) ...[
          const Divider(height: 28),
          Text('AI 私教复盘', style: Theme.of(context).textTheme.titleMedium),
          Text(ai['summary']),
          const SizedBox(height: 8),
          const Text('本次完成'),
          for (final s in ai['strengths']) Text('• $s'),
          const SizedBox(height: 8),
          const Text('下次建议'),
          for (final s in ai['next_steps']) Text('• $s'),
          const SizedBox(height: 8),
          Text(
            '模型：${ai['model']} · 建议不作为已完成事实',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }
}

class _SetDraft {
  _SetDraft([Map? data]) {
    weight.text = '${data?['weight_kg'] ?? ''}';
    reps.text = '${data?['reps'] ?? ''}';
    rpe.text = '${data?['rpe'] ?? ''}';
    pain = data?['pain'] == true;
  }
  final weight = TextEditingController();
  final reps = TextEditingController();
  final rpe = TextEditingController();
  bool pain = false;
  Map<String, dynamic> draft() => {
    'weight_kg': weight.text,
    'reps': reps.text,
    'rpe': rpe.text,
    'pain': pain,
  };
  Map<String, dynamic> confirmed() {
    final w = double.tryParse(weight.text),
        r = int.tryParse(reps.text),
        p = double.tryParse(rpe.text);
    if (w == null ||
        !w.isFinite ||
        w < 0 ||
        w > 500 ||
        r == null ||
        r < 1 ||
        r > 100 ||
        p == null ||
        !p.isFinite ||
        p < 1 ||
        p > 10) {
      throw Exception('请逐组确认重量 0–500 kg、次数 1–100 和 RPE 1–10。');
    }
    return {'weight_kg': w, 'reps': r, 'rpe': p, 'pain': pain};
  }

  void dispose() {
    weight.dispose();
    reps.dispose();
    rpe.dispose();
  }
}

class _ExerciseDraft {
  _ExerciseDraft(
    this.id, {
    List? savedSets,
    String text = '',
    this.detectedReps,
  }) {
    notes.text = text;
    sets.addAll(
      savedSets == null ? [_SetDraft()] : savedSets.map((s) => _SetDraft(s)),
    );
  }
  final String id;
  final int? detectedReps;
  final notes = TextEditingController();
  final List<_SetDraft> sets = [];
  Map<String, dynamic> draft() => {
    'exercise_id': id,
    'notes': notes.text,
    'detected_reps': detectedReps,
    'sets': sets.map((s) => s.draft()).toList(),
  };
  Map<String, dynamic> confirmed() => {
    'exercise_id': id,
    'notes': notes.text,
    'detected_reps': detectedReps,
    'sets': sets.map((s) => s.confirmed()).toList(),
  };
  void dispose() {
    notes.dispose();
    for (final s in sets) {
      s.dispose();
    }
  }
}

class WorkoutLogPage extends StatefulWidget {
  const WorkoutLogPage({
    super.key,
    required this.request,
    required this.onSaved,
    required this.exercises,
    required this.coachId,
    this.liveExerciseId,
    this.detectedSets = const [],
    this.liveDurationMinutes,
    this.liveCaptureId,
    this.initialExerciseId,
    this.currentPlan,
  });
  final WorkoutRequest request;
  final Future<void> Function() onSaved;
  final Map<String, Map<String, dynamic>> exercises;
  final String coachId;
  final String? liveExerciseId;
  final List<int> detectedSets;
  final int? liveDurationMinutes;
  final String? liveCaptureId;
  final String? initialExerciseId;
  final Map<String, dynamic>? currentPlan;
  @override
  State<WorkoutLogPage> createState() => _WorkoutLogPageState();
}

class _WorkoutLogPageState extends State<WorkoutLogPage> {
  static const draftKey = 'workout-draft-v1';
  final duration = TextEditingController(), notes = TextEditingController();
  final entries = <_ExerciseDraft>[];
  late String day;
  String? selected, error, reviewError;
  String category = '';
  bool loading = true, busy = false, reviewing = false;
  Map<String, dynamic>? saved, pending, progression;
  String? planDay, planId, progressionError;
  String readiness = 'normal';
  bool completedPlanDay = false, progressing = false;
  Future<void> persistence = Future.value();
  bool get locked => busy || pending != null || saved != null;
  bool restored = false;
  bool otherCapture = false;
  String? draftCaptureId;

  @override
  void initState() {
    super.initState();
    day = DateTime.now()
        .toUtc()
        .add(const Duration(hours: 8))
        .toIso8601String()
        .split('T')
        .first;
    selected = widget.initialExerciseId ?? widget.exercises.keys.firstOrNull;
    restore();
  }

  Future<void> restore() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = prefs.getString(draftKey);
      // A new live capture must not overwrite an existing unsaved workout.
      if (raw != null) {
        final d = jsonDecode(raw) as Map;
        draftCaptureId = d['live_capture_id'];
        otherCapture =
            widget.liveExerciseId != null &&
            draftCaptureId != widget.liveCaptureId;
        day = d['day'];
        planDay = d['plan_day'];
        planId = d['plan_id'];
        readiness = d['readiness'] ?? 'normal';
        completedPlanDay = d['completed_plan_day'] == true;
        duration.text = d['duration'] ?? '';
        notes.text = d['notes'] ?? '';
        pending = d['pending'] == null
            ? null
            : Map<String, dynamic>.from(d['pending']);
        for (final e in d['exercises']) {
          entries.add(
            _ExerciseDraft(
              e['exercise_id'],
              savedSets: e['sets'],
              text: e['notes'] ?? '',
              detectedReps: e['detected_reps'],
            ),
          );
        }
        restored = true;
      } else if (widget.liveExerciseId != null) {
        draftCaptureId = widget.liveCaptureId;
        duration.text = '${widget.liveDurationMinutes ?? ''}';
        entries.add(
          _ExerciseDraft(
            widget.liveExerciseId!,
            savedSets: [
              for (final _ in widget.detectedSets) <String, dynamic>{},
            ],
            detectedReps: widget.detectedSets.fold<int>(0, (a, b) => a + b),
          ),
        );
      }
    } catch (_) {
      error = '训练草稿读取失败，请重新填写；现有服务器记录不受影响。';
    }
    if (mounted) {
      setState(() => loading = false);
      if (entries.isNotEmpty) unawaitedPersist();
    }
  }

  Future<void> persist() {
    if (loading || saved != null) return Future.value();
    final raw = jsonEncode({
      'day': day,
      'duration': duration.text,
      'notes': notes.text,
      'exercises': entries.map((e) => e.draft()).toList(),
      'pending': pending,
      'live_capture_id': draftCaptureId,
      'plan_id': planId,
      'plan_day': planDay,
      'readiness': readiness,
      'completed_plan_day': completedPlanDay,
    });
    persistence = persistence.catchError((_) {}).then((_) async {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(draftKey, raw);
    });
    return persistence;
  }

  void changed() {
    unawaitedPersist();
  }

  void unawaitedPersist() {
    persist().catchError((Object e) {
      if (mounted) setState(() => error = '本机草稿保存失败，请完成服务器保存：$e');
    });
  }

  @override
  void dispose() {
    duration.dispose();
    notes.dispose();
    for (final e in entries) {
      e.dispose();
    }
    super.dispose();
  }

  Future<void> save() async {
    setState(() {
      busy = true;
      error = null;
    });
    try {
      if (pending == null) {
        if (entries.isEmpty) throw Exception('请至少添加一个实际完成的动作。');
        if (entries.any((e) => !widget.exercises.containsKey(e.id)) ||
            entries.map((e) => e.id).toSet().length != entries.length) {
          throw Exception('草稿中的动作已变化，请移除失效或重复的动作后重新选择。');
        }
        final mins = duration.text.trim().isEmpty
            ? null
            : int.tryParse(duration.text);
        if (duration.text.trim().isNotEmpty &&
            (mins == null || mins < 1 || mins > 600)) {
          throw Exception('训练用时请填写 1–600 分钟，或留空。');
        }
        pending = {
          'request_id': 'workout-${DateTime.now().microsecondsSinceEpoch}',
          'day': day,
          'duration_minutes': mins,
          'notes': notes.text,
          'source': draftCaptureId != null ? 'live_confirmed' : 'manual',
          if (planId != null && planDay != null) ...{
            'plan_id': planId,
            'plan_day': planDay,
          },
          'readiness': readiness,
          'completed_plan_day': completedPlanDay,
          'exercises': entries.map((e) => e.confirmed()).toList(),
        };
      }
      await persist();
      final result = Map<String, dynamic>.from(
        await widget.request('/workouts', 'POST', pending),
      );
      saved = result;
      await persistence;
      await (await SharedPreferences.getInstance()).remove(draftKey);
      if (mounted) setState(() {});
      try {
        await widget.onSaved();
      } catch (_) {
        if (mounted) setState(() => error = '训练已保存，画像页面刷新失败，请返回后刷新。');
      }
      await review();
      await evaluateProgression();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> review() async {
    if (saved == null || reviewing) return;
    if (mounted) {
      setState(() {
        reviewing = true;
        reviewError = null;
      });
    }
    try {
      final result = Map<String, dynamic>.from(
        await widget.request('/workouts/${saved!['id']}/review', 'POST', {
          'coach_id': widget.coachId,
        }),
      );
      saved = result;
      await widget.onSaved();
    } catch (e) {
      reviewError =
          '训练与基础复盘已保存。AI 复盘暂未生成：${e.toString().replaceFirst(RegExp(r"^Exception: "), "")}';
    } finally {
      if (mounted) setState(() => reviewing = false);
    }
  }

  Future<void> evaluateProgression() async {
    if (saved == null || progressing) return;
    setState(() {
      progressing = true;
      progressionError = null;
    });
    try {
      final result = Map<String, dynamic>.from(
        await widget.request(
          '/workouts/${saved!['id']}/progression',
          'POST',
          {},
        ),
      );
      if (mounted) setState(() => progression = result);
      await widget.onSaved();
    } catch (e) {
      if (mounted) setState(() => progressionError = '训练已保存，进阶评估可重试：$e');
    } finally {
      if (mounted) setState(() => progressing = false);
    }
  }

  Widget planLink() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (widget.currentPlan != null)
        DropdownButtonFormField<String>(
          initialValue:
              (widget.currentPlan!['days'] as List).any(
                (d) => d['name'] == planDay,
              )
              ? planDay
              : null,
          isExpanded: true,
          decoration: const InputDecoration(labelText: '本次对应哪个计划训练日（可选）'),
          items: [
            for (final d in widget.currentPlan!['days'])
              DropdownMenuItem<String>(
                value: d['name'],
                child: Text('${d['name']}', overflow: TextOverflow.ellipsis),
              ),
          ],
          onChanged: locked
              ? null
              : (value) {
                  setState(() {
                    planDay = value;
                    planId = widget.currentPlan!['id'];
                    if (entries.isEmpty) {
                      final target = (widget.currentPlan!['days'] as List)
                          .firstWhere((d) => d['name'] == value);
                      for (final e in target['exercises']) {
                        entries.add(
                          _ExerciseDraft(
                            e['exercise_id'],
                            savedSets: [
                              for (int i = 0; i < e['sets']; i++)
                                {
                                  'weight_kg': e['weight_kg'],
                                  'reps': e['reps'],
                                },
                            ],
                          ),
                        );
                      }
                    }
                  });
                  changed();
                },
        ),
      if (planDay != null)
        CheckboxListTile(
          contentPadding: EdgeInsets.zero,
          value: completedPlanDay,
          title: const Text('确认本次已完成所选训练日'),
          subtitle: const Text('请把下方组次改为实际完成值；进阶还会核对实际记录，不以勾选代替达标。'),
          onChanged: locked
              ? null
              : (v) {
                  setState(() => completedPlanDay = v ?? false);
                  changed();
                },
        ),
      DropdownButtonFormField<String>(
        initialValue: readiness,
        decoration: const InputDecoration(labelText: '本次恢复与状态'),
        items: const [
          DropdownMenuItem(value: 'good', child: Text('恢复良好')),
          DropdownMenuItem(value: 'normal', child: Text('一般')),
          DropdownMenuItem(value: 'poor', child: Text('疲劳或恢复不足')),
        ],
        onChanged: locked
            ? null
            : (v) {
                setState(() => readiness = v!);
                changed();
              },
      ),
    ],
  );

  Widget input(String label, TextEditingController c, {bool text = false}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: TextField(
          controller: c,
          enabled: !locked,
          onChanged: (_) => changed(),
          maxLength: text ? (c == notes ? 1500 : 500) : null,
          keyboardType: text
              ? TextInputType.multiline
              : const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: label),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final categories =
        widget.exercises.values
            .map((e) => '${e['movement_pattern'] ?? '未分类'}')
            .toSet()
            .toList()
          ..sort();
    final available = widget.exercises.entries
        .where(
          (e) =>
              !entries.any((d) => d.id == e.key) &&
              (category.isEmpty ||
                  '${e.value['movement_pattern'] ?? '未分类'}' == category),
        )
        .toList();
    if (!available.any((e) => e.key == selected)) {
      selected = available.firstOrNull?.key;
    }
    return Scaffold(
      appBar: AppBar(title: Text(saved == null ? '记录本次训练' : '训练复盘')),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(18),
              children: [
                if (error != null)
                  Text(error!, style: const TextStyle(color: Colors.red)),
                if (saved != null) ...[
                  const Text('训练已沉淀到用户画像，后续对话和 AI 计划会参考。'),
                  const SizedBox(height: 16),
                  WorkoutReview(record: saved!),
                  if (progression != null) PlanChangeCard(event: progression!),
                  if (progressing) const LinearProgressIndicator(),
                  if (progressionError != null) Text(progressionError!),
                  if (!progressing && progression == null)
                    TextButton(
                      onPressed: evaluateProgression,
                      child: const Text('评估下一次计划'),
                    ),

                  if (reviewing) const LinearProgressIndicator(),
                  if (reviewError != null) Text(reviewError!),
                  if (saved!['ai_review'] == null && !reviewing)
                    OutlinedButton(
                      onPressed: review,
                      child: const Text('重试 AI 私教复盘'),
                    ),
                  FilledButton(
                    onPressed: () => Navigator.pop(context, !otherCapture),
                    child: Text(otherCapture ? '返回陪训，继续记录本次' : '完成'),
                  ),
                ] else ...[
                  const Text('记录实际完成的每一组。保存后生成复盘，并成为私教了解你的训练档案。'),
                  if (restored) const Text('已恢复本机未完成草稿。'),
                  if (otherCapture)
                    const Text('已有未完成训练草稿。本次实时计次尚未并入，请先保存草稿，再记录本次。'),
                  if (pending != null && !busy)
                    const Text('上次提交结果待确认，已锁定记录。重试会使用同一编号，避免重复保存。'),
                  TextButton.icon(
                    icon: const Icon(Icons.calendar_today_outlined),
                    label: Text('训练日期 $day'),
                    onPressed: locked
                        ? null
                        : () async {
                            final now = DateTime.now().toUtc().add(
                              const Duration(hours: 8),
                            );
                            final picked = await showDatePicker(
                              context: context,
                              initialDate: DateTime.parse(day),
                              firstDate: DateTime(2000),
                              lastDate: now,
                            );
                            if (picked != null && mounted) {
                              setState(
                                () => day = picked
                                    .toIso8601String()
                                    .split('T')
                                    .first,
                              );
                              changed();
                            }
                          },
                  ),
                  planLink(),
                  input('本次训练用时 / 分钟（可留空）', duration),
                  for (final e in entries)
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    widget.exercises[e.id]?['name'] ?? e.id,
                                    style: Theme.of(context)
                                        .textTheme
                                        .titleMedium,
                                  ),
                                ),
                                IconButton(
                                  tooltip: '移除动作',
                                  onPressed: locked
                                      ? null
                                      : () {
                                          setState(() => entries.remove(e));
                                          e.dispose();
                                          changed();
                                        },
                                  icon: const Icon(Icons.close),
                                ),
                              ],
                            ),
                            Text(widget.exercises[e.id]?['weight_basis'] ?? ''),
                            if (e.detectedReps != null)
                              Text(
                                '实时实验计次共 ${e.detectedReps} 次，请逐组自行确认实际次数；不代表动作质量。',
                              ),
                            for (int i = 0; i < e.sets.length; i++) ...[
                              Row(
                                children: [
                                  Text('第 ${i + 1} 组'),
                                  const Spacer(),
                                  IconButton(
                                    tooltip: '移除本组',
                                    onPressed: locked || e.sets.length == 1
                                        ? null
                                        : () {
                                            final removed = e.sets[i];
                                            setState(() => e.sets.removeAt(i));
                                            removed.dispose();
                                            changed();
                                          },
                                    icon: const Icon(
                                      Icons.remove_circle_outline,
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(
                                    child: input('重量 / kg', e.sets[i].weight),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: input('实际次数', e.sets[i].reps),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: input('RPE 1–10', e.sets[i].rpe),
                                  ),
                                ],
                              ),
                              CheckboxListTile(
                                contentPadding: EdgeInsets.zero,
                                title: const Text('本组出现疼痛或不适'),
                                value: e.sets[i].pain,
                                onChanged: locked
                                    ? null
                                    : (v) {
                                        setState(
                                          () => e.sets[i].pain = v ?? false,
                                        );
                                        changed();
                                      },
                              ),
                            ],
                            TextButton.icon(
                              onPressed: locked || e.sets.length >= 20
                                  ? null
                                  : () {
                                      setState(() => e.sets.add(_SetDraft()));
                                      changed();
                                    },
                              icon: const Icon(Icons.add),
                              label: const Text('添加一组'),
                            ),
                            input('动作感受 / 需要下次关注的细节（可留空）', e.notes, text: true),
                          ],
                        ),
                      ),
                    ),
                  DropdownButtonFormField<String>(
                    initialValue: category,
                    decoration: const InputDecoration(labelText: '关节动作分类'),
                    items: [
                      const DropdownMenuItem(value: '', child: Text('全部关节动作')),
                      for (final c in categories)
                        DropdownMenuItem(value: c, child: Text(c)),
                    ],
                    onChanged: locked
                        ? null
                        : (v) => setState(() => category = v ?? ''),
                  ),
                  const SizedBox(height: 12),
                  DropdownButtonFormField<String>(
                    key: ValueKey(
                      'workout-exercise-$selected-${available.length}',
                    ),
                    initialValue: selected,
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: '选择完成的动作'),
                    items: [
                      for (final e in available)
                        DropdownMenuItem(
                          value: e.key,
                          child: Text(e.value['name']),
                        ),
                    ],
                    onChanged: locked
                        ? null
                        : (v) => setState(() => selected = v),
                  ),
                  OutlinedButton.icon(
                    onPressed:
                        locked || selected == null || entries.length >= 20
                        ? null
                        : () {
                            setState(
                              () => entries.add(_ExerciseDraft(selected!)),
                            );
                            changed();
                          },
                    icon: const Icon(Icons.add),
                    label: const Text('添加动作'),
                  ),
                  input('本次整体感受 / 恢复情况（可留空）', notes, text: true),
                  FilledButton(
                    onPressed: busy ? null : save,
                    child: Text(
                      busy
                          ? '保存与复盘中…'
                          : pending == null
                          ? '完成训练并生成复盘'
                          : '重试保存本次训练',
                    ),
                  ),
                  const Text('草稿保存在本机；正式记录和 AI 复盘需要连接服务器。未配置模型时仍可保存并查看基础复盘。'),
                ],
              ],
            ),
    );
  }
}
