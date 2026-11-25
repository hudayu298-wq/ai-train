import 'dart:convert';

import 'package:flutter/material.dart';

import 'profile_setup.dart';
import 'set_runner.dart';

import 'package:shared_preferences/shared_preferences.dart';

typedef WorkoutRequest = Future<dynamic> Function(String, String, Object?);

class WorkoutReview extends StatelessWidget {
  const WorkoutReview({super.key, required this.record});
  final Map<String, dynamic> record;

  String describeSet(dynamic value, {bool target = false}) {
    if (value == null) return target ? '额外组，无计划目标' : '未记录';
    return '${value['weight_kg'] == null ? '重量待确认' : '${value['weight_kg']} kg'} × ${value['reps']}次'
        ' · RIR ${value[target ? 'target_rir' : 'rir'] ?? '未记录'}'
        ' · 休息 ${value['rest_seconds'] == null ? '未记录' : '${value['rest_seconds']}秒'}';
  }

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
        if (summary?['target_comparison'] is Map) ...[
          const Divider(),
          Text(
            summary!['target_comparison']['basis'] == 'server_plan_at_start'
                ? '计划目标与实际完成 · 开练冻结版本'
                : '计划目标与实际完成 · 按确认保存时的计划版本',
          ),
          Text(summary['target_comparison']['note']),
          for (final row in summary['target_comparison']['sets'])
            Text(
              '${(record['exercises'] as List).where((e) => e['exercise_id'] == row['exercise_id']).map((e) => e['name']).firstOrNull ?? row['exercise_id']} · 工作组${row['set_number']}：'
              '目标 ${describeSet(row['target'], target: true)}；'
              '实际 ${describeSet(row['actual'])}',
            ),
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
    assisted = data?['assisted'] == true;
    setType = data?['set_type'] ?? 'working';
    rest.text = '${data?['rest_seconds'] ?? ''}';
    rir.text = '${data?['rir'] ?? ''}';
  }
  final weight = TextEditingController();
  final reps = TextEditingController();
  final rpe = TextEditingController();
  final rest = TextEditingController(), rir = TextEditingController();
  bool pain = false;
  bool assisted = false;
  String setType = 'working';
  Map<String, dynamic> draft() => {
    'weight_kg': weight.text,
    'reps': reps.text,
    'rpe': rpe.text,
    'pain': pain,
    'assisted': assisted,
    'set_type': setType,
    'rest_seconds': rest.text,
    'rir': rir.text,
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
    int? optionalInt(TextEditingController c, int max) {
      if (c.text.trim().isEmpty) {
        return null;
      }
      final v = int.tryParse(c.text);
      if (v == null || v < 0 || v > max) {
        throw Exception('请检查实际休息和剩余次数');
      }
      return v;
    }

    return {
      'weight_kg': w,
      'reps': r,
      'rpe': p,
      'pain': pain,
      'assisted': assisted,
      'set_type': setType,
      'rest_seconds': optionalInt(rest, 1800),
      'rir': optionalInt(rir, 10),
    };
  }

  void dispose() {
    weight.dispose();
    reps.dispose();
    rpe.dispose();
    rest.dispose();
    rir.dispose();
  }
}

class _ExerciseDraft {
  _ExerciseDraft(
    this.id, {
    List? savedSets,
    String text = '',
    this.detectedReps,
    this.loadBasis = 'catalog',
    String equipmentText = '',
    String discomfortText = '',
    this.group = 0,
  }) {
    notes.text = text;
    equipment.text = equipmentText;
    discomfort.text = discomfortText;
    sets.addAll(
      savedSets == null ? [_SetDraft()] : savedSets.map((s) => _SetDraft(s)),
    );
  }
  final String id;
  final int? detectedReps;
  final notes = TextEditingController();
  final equipment = TextEditingController(),
      discomfort = TextEditingController();
  String loadBasis;
  int group;
  final List<_SetDraft> sets = [];
  Map<String, dynamic> draft() => {
    'exercise_id': id,
    'notes': notes.text,
    'detected_reps': detectedReps,
    'equipment_id': equipment.text,
    'load_basis': loadBasis,
    'discomfort_area': discomfort.text,
    'execution_group': group,
    'sets': sets.map((s) => s.draft()).toList(),
  };
  Map<String, dynamic> confirmed() => {
    'exercise_id': id,
    'notes': notes.text,
    'detected_reps': detectedReps,
    'equipment_id': equipment.text,
    'load_basis': loadBasis,
    'discomfort_area': discomfort.text,
    'sets': sets.map((s) => s.confirmed()).toList(),
  };
  void dispose() {
    notes.dispose();
    equipment.dispose();
    discomfort.dispose();
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
  String? planDay, planId, progressionError, startRequestId;
  Map<String, dynamic>? execution;
  String readiness = 'normal';
  String completionReason = 'unknown';
  final completionNotes = TextEditingController();
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
        execution = d['execution'] == null
            ? null
            : Map<String, dynamic>.from(d['execution']);
        startRequestId = d['start_request_id'];
        readiness = d['readiness'] ?? 'normal';
        completionReason = d['completion_reason'] ?? 'unknown';
        completionNotes.text = d['completion_notes'] ?? '';
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
              equipmentText: e['equipment_id'] ?? '',
              loadBasis: e['load_basis'] ?? 'catalog',
              discomfortText: e['discomfort_area'] ?? '',
              group: e['execution_group'] ?? 0,
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
      'execution': execution,
      'start_request_id': startRequestId,
      'plan_day': planDay,
      'readiness': readiness,
      'completed_plan_day': completedPlanDay,
      'completion_reason': completionReason,
      'completion_notes': completionNotes.text,
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
    completionNotes.dispose();
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
          if (execution != null) 'execution_id': execution!['id'],
          'execution_groups': executionGroups(),
          'source': draftCaptureId != null ? 'live_confirmed' : 'manual',
          if (planId != null && planDay != null) ...{
            'plan_id': planId,
            'plan_day': planDay,
          },
          'readiness': readiness,
          'completed_plan_day': completedPlanDay,
          'completion_reason': completedPlanDay
              ? 'as_planned'
              : completionReason,
          'completion_notes': completionNotes.text,
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

  List<List<String>> executionGroups() {
    final groups = <int, List<String>>{};
    for (final e in entries) {
      if (e.group > 0) {
        groups.putIfAbsent(e.group, () => []).add(e.id);
      }
    }
    if (groups.values.any((g) => g.length < 2 || g.length > 4)) {
      throw Exception('每个交替组请选择2至4个动作；单个动作请设为普通组。');
    }
    return groups.values.toList();
  }

  Future<void> runSets() async {
    try {
      executionGroups();
      if (planId != null && planDay != null && execution == null) {
        setState(() {
          busy = true;
          error = null;
        });
        startRequestId ??= 'start-${DateTime.now().microsecondsSinceEpoch}';
        await persist();
        execution = Map<String, dynamic>.from(
          await widget.request('/workouts/start', 'POST', {
            'plan_id': planId,
            'plan_day': planDay,
            'day': day,
            'request_id': startRequestId,
          }),
        );
        await persist();
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          busy = false;
          error = '$e';
        });
      }
      return;
    }
    if (!mounted) {
      return;
    }
    setState(() => busy = false);
    final steps = <Map<String, dynamic>>[];
    final destinations = <_SetDraft>[];
    Map? dayTarget;
    final referencePlan = execution?['plan_snapshot'] ?? widget.currentPlan;
    if (referencePlan?['id'] == planId && planDay != null) {
      for (final d in referencePlan!['days']) {
        if (d['name'] == planDay) dayTarget = d as Map;
      }
    }
    for (final e in entries) {
      Map? target;
      for (final t in dayTarget?['exercises'] ?? []) {
        if (t['exercise_id'] == e.id) target = t as Map;
      }
      var workingIndex = 0;
      for (var i = 0; i < e.sets.length; i++) {
        final set = e.sets[i];
        final planned =
            set.setType == 'working' &&
            target != null &&
            workingIndex < target['sets'];
        if (set.setType == 'working') workingIndex++;
        steps.add({
          'exercise_id': e.id,
          'group': e.group,
          'destination_index': destinations.length,
          'name': widget.exercises[e.id]?['name'] ?? e.id,
          'set_number': i + 1,
          'actual': set.draft(),
          'weight_basis': widget.exercises[e.id]?['weight_basis'],
          'target': planned ? target : null,
        });
        destinations.add(set);
      }
    }
    if (steps.isEmpty) return;
    final orderedSteps = interleaveSteps(steps);
    await Navigator.push(
      context,
      MaterialPageRoute<void>(
        builder: (_) => SetRunner(
          steps: orderedSteps,
          frozen: execution != null,
          onRecorded: (index, actual) {
            final set =
                destinations[orderedSteps[index]['destination_index'] as int];
            set.weight.text = '${actual['weight_kg']}';
            set.reps.text = '${actual['reps']}';
            set.rpe.text = '${actual['rpe']}';
            set.rir.text = '${actual['rir'] ?? ''}';
            set.pain = actual['pain'] == true;
            if (actual['rest_seconds'] != null) {
              set.rest.text = '${actual['rest_seconds']}';
            }
            changed();
          },
        ),
      ),
    );
    if (mounted) setState(() {});
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
          onChanged: locked || execution != null
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
                                  // Targets are displayed separately; actual values need confirmation.
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
      if (execution != null) ...[
        Text(
          '已冻结开练目标 · 版本${execution!['plan_snapshot']['version'] ?? 1} · ${execution!['started_at']}',
        ),
        TextButton(
          onPressed: locked
              ? null
              : () {
                  setState(() {
                    execution = null;
                    startRequestId = null;
                    completedPlanDay = false;
                  });
                  changed();
                },
          child: const Text('保留实际草稿，解除冻结以重新关联计划'),
        ),
      ],
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
                    onPressed: locked || execution != null
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
                  OutlinedButton.icon(
                    onPressed: locked || entries.isEmpty ? null : runSets,
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('开始逐组训练与休息计时'),
                  ),
                  input('本次训练用时 / 分钟（可留空）', duration),
                  DropdownButtonFormField<String>(
                    initialValue: completionReason,
                    decoration: const InputDecoration(labelText: '本次完成情况/影响因素'),
                    items: [
                      for (final e in {
                        'unknown': '未注明',
                        'as_planned': '按安排完成',
                        'time': '时间不足',
                        'equipment': '器械不可用',
                        'fatigue': '疲劳',
                        'discomfort': '不适',
                        'other': '其他',
                      }.entries)
                        DropdownMenuItem(value: e.key, child: Text(e.value)),
                    ],
                    onChanged: locked
                        ? null
                        : (v) {
                            setState(() {
                              completionReason = v!;
                              if (!['unknown', 'as_planned'].contains(v)) {
                                completedPlanDay = false;
                              }
                            });
                            changed();
                          },
                  ),
                  input('完成情况补充（可选）', completionNotes, text: true),
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
                            ExpansionTile(
                              tilePadding: EdgeInsets.zero,
                              title: const Text('器械与负重口径（可选）'),
                              children: [
                                input(
                                  '器械标识（如A区史密斯1号）',
                                  e.equipment,
                                  text: true,
                                ),
                                DropdownButtonFormField<String>(
                                  initialValue: e.loadBasis,
                                  decoration: const InputDecoration(
                                    labelText: '本次记录的重量口径',
                                  ),
                                  items: [
                                    for (final b in {
                                      'catalog': '使用动作库标注口径',
                                      'total': '总重量',
                                      'per_hand': '单手重量',
                                      'machine_display': '器械显示重量',
                                    }.entries)
                                      DropdownMenuItem(
                                        value: b.key,
                                        child: Text(b.value),
                                      ),
                                  ],
                                  onChanged: locked
                                      ? null
                                      : (v) {
                                          setState(() => e.loadBasis = v!);
                                          changed();
                                        },
                                ),
                                input('不适部位（可选）', e.discomfort, text: true),
                                const Text('更换器械或口径后不会直接据此加重。'),
                              ],
                            ),
                            DropdownButtonFormField<int>(
                              initialValue: e.group,
                              decoration: const InputDecoration(
                                labelText: '执行编排',
                              ),
                              items: [
                                const DropdownMenuItem(
                                  value: 0,
                                  child: Text('普通组，逐动作执行'),
                                ),
                                for (var g = 1; g <= 5; g++)
                                  DropdownMenuItem(
                                    value: g,
                                    child: Text('交替组 $g（同组2–4个动作轮流）'),
                                  ),
                              ],
                              onChanged: locked
                                  ? null
                                  : (v) {
                                      setState(() => e.group = v!);
                                      changed();
                                    },
                            ),
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
                              ExpansionTile(
                                tilePadding: EdgeInsets.zero,
                                title: Text(
                                  '${e.sets[i].setType == 'warmup' ? '热身组' : '工作组'}${e.sets[i].assisted ? ' · 有辅助' : ''} · 组细节',
                                ),
                                children: [
                                  SwitchListTile(
                                    contentPadding: EdgeInsets.zero,
                                    title: const Text('这是热身组'),
                                    value: e.sets[i].setType == 'warmup',
                                    onChanged: locked
                                        ? null
                                        : (v) {
                                            setState(
                                              () => e.sets[i].setType = v
                                                  ? 'warmup'
                                                  : 'working',
                                            );
                                            changed();
                                          },
                                  ),
                                  CheckboxListTile(
                                    contentPadding: EdgeInsets.zero,
                                    title: const Text('本组有他人辅助完成'),
                                    value: e.sets[i].assisted,
                                    onChanged: locked
                                        ? null
                                        : (v) {
                                            setState(
                                              () => e.sets[i].assisted =
                                                  v == true,
                                            );
                                            changed();
                                          },
                                  ),
                                  input('实际组间休息 / 秒（可选）', e.sets[i].rest),
                                  input(
                                    '完成后还能做几次 / RIR 0–10（可选）',
                                    e.sets[i].rir,
                                  ),
                                ],
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
