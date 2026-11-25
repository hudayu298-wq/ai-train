import 'package:flutter/material.dart';

import 'training_plan_overview.dart';

String phaseLabel(dynamic phase) =>
    const {
      'foundation': '熟悉与校准',
      'build': '持续训练',
      'consolidate': '巩固与复核',
      'deload': '减量与恢复',
    }[phase] ??
    '$phase';

class CycleSchedulePreview extends StatelessWidget {
  const CycleSchedulePreview({
    super.key,
    required this.plan,
    required this.exercises,
  });
  final Map<String, dynamic> plan;
  final Map<String, String> exercises;

  @override
  Widget build(BuildContext context) {
    final schedule = plan['cycle_schedule'] as List? ?? [];
    if (schedule.isEmpty) return const SizedBox.shrink();
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      title: Text('${plan['cycle_weeks'] ?? schedule.length}周可执行目标'),
      subtitle: const Text('周目的与组次、重量、余力及休息；未来加重仍需训练后评估'),
      children: [
        for (final week in schedule)
          ExpansionTile(
            title: Text(
              '第${week['week']}周 · ${phaseLabel(week['phase'])}${week['week'] == (plan['cycle_week'] ?? 1) ? ' · 当前' : ''}',
            ),
            subtitle: Text('${week['purpose']}'),
            children: [
              TrainingPlanOverview(
                plan: {
                  ...plan,
                  'id': '${plan['id'] ?? plan['name']}-week-${week['week']}',
                  'days': week['days'],
                },
                exercises: exercises,
                showHeader: false,
              ),
            ],
          ),
      ],
    );
  }
}

class CyclePlanPanel extends StatefulWidget {
  const CyclePlanPanel({
    super.key,
    required this.plan,
    required this.exercises,
    required this.post,
    required this.onSaved,
  });
  final Map<String, dynamic> plan;
  final Map<String, String> exercises;
  final Future<dynamic> Function(String, Map<String, dynamic>) post;
  final Future<void> Function() onSaved;
  @override
  State<CyclePlanPanel> createState() => _CyclePlanPanelState();
}

class _CyclePlanPanelState extends State<CyclePlanPanel> {
  bool busy = false;
  String? message;
  final Map<String, String> requestIds = {};

  Future<void> act(String action) async {
    if (busy) return;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      // Retries retain one key; a refreshed plan is a different operation.
      final key = '${widget.plan['id']}-$action';
      final id = requestIds.putIfAbsent(
        key,
        () => 'cycle-${DateTime.now().microsecondsSinceEpoch}-$action',
      );
      final result = await widget.post('/plans/cycle/actions', {
        'request_id': id,
        'base_plan_id': widget.plan['id'],
        'action': action,
      });
      await widget.onSaved();
      if (mounted) setState(() => message = '${result['summary']}');
    } catch (e) {
      if (mounted) setState(() => message = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final status = widget.plan['cycle_status'] as Map?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '第${widget.plan['cycle_week'] ?? 1}/${widget.plan['cycle_weeks'] ?? 4}周',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        if (status != null) ...[
          Text('${status['guidance']}'),
          if ((status['pending_days'] as List? ?? []).isNotEmpty)
            Text('本周待完成：${(status['pending_days'] as List).join('、')}'),
          if (status['cycle_complete'] != true)
            Wrap(
              spacing: 8,
              children: [
                if (status['missed_week'] == true ||
                    status['interruption_review_required'] == true)
                  OutlinedButton(
                    onPressed: busy ? null : () => act('repeat_week'),
                    child: const Text('保留目标，重新开始本周'),
                  ),
                if (status['deload_suggested'] == true)
                  OutlinedButton(
                    onPressed: busy ? null : () => act('deload_week'),
                    child: const Text('确认降低本周组数并重启'),
                  ),
                if (status['ready_to_advance'] == true)
                  OutlinedButton(
                    onPressed: busy ? null : () => act('advance_week'),
                    child: const Text('进入下一周目标'),
                  ),
              ],
            ),
          if (status['deload_suggested'] == true)
            const Text('减量确认会按当前产品策略减少组数、保留重量与次数；不适动作应暂停，不能带痛执行。'),
          for (final change in status['deload_preview'] ?? [])
            Text(
              '${change['day']} · ${widget.exercises[change['exercise_id']] ?? change['exercise_id']}：${change['before_sets']} → ${change['after_sets']}组',
            ),
        ],
        if (busy) const LinearProgressIndicator(),
        if (message != null) Text(message!),
        CycleSchedulePreview(plan: widget.plan, exercises: widget.exercises),
      ],
    );
  }
}
