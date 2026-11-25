import 'package:flutter/material.dart';

import 'regional_strength_profile.dart';
import 'ui_theme.dart';

const splitChoices = {
  'auto': '让AI按画像选择',
  'full_body': '全身训练',
  'upper_lower': '二分化 · 上肢/下肢',
  'push_pull_legs': '三分化 · 推/拉/腿',
  'bodypart_four': '四分化 · 胸/背/肩臂/腿',
  'bodypart_five': '五分化 · 胸/背/肩/腿/手臂',
};
const methodChoices = {
  'auto': '让AI按画像选择',
  'straight_sets': '常规固定组',
  'five_by_five': '主项5×5',
  'strength_hypertrophy': '力量与增肌混合',
};
const focusLabels = {
  'full_body': '全身',
  'upper': '上肢',
  'lower': '下肢',
  'push': '推 · 胸肩肱三头',
  'pull': '拉 · 背肱二头',
  'legs': '腿部',
  'chest': '胸部',
  'back': '背部',
  'shoulders': '肩部',
  'shoulders_arms': '肩与手臂',
  'arms': '手臂',
};

class TrainingPlanOverview extends StatelessWidget {
  const TrainingPlanOverview({
    super.key,
    required this.plan,
    required this.exercises,
    this.showHeader = true,
  });
  final Map<String, dynamic> plan;
  final Map<String, String> exercises;
  final bool showHeader;

  @override
  Widget build(BuildContext context) {
    final days = plan['days'] as List? ?? [];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (showHeader) ...[
          Text(
            '${plan['name']}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
        ],
        Text(
          '${splitChoices[plan['split_type']] ?? '旧计划 · 未记录分化'} · 每周${days.length}次 · ${plan['cycle_weeks'] ?? 4}周',
          style: const TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 12),
        const Text('训练日安排', style: TextStyle(fontWeight: FontWeight.w600)),
        const Text(
          '先看每天的目标，展开对应训练日查看动作与负荷。',
          style: TextStyle(color: AppColors.muted),
        ),
        const SizedBox(height: 12),
        for (final day in days)
          Card(
            child: ExpansionTile(
              key: PageStorageKey(
                'plan-day-${plan['id'] ?? plan['generation_id'] ?? plan['name']}-${day['name']}',
              ),
              maintainState: true,
              tilePadding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 8,
              ),
              childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
              title: Text(
                '${day['name']} · ${focusLabels[day['focus']] ?? '待注明训练部位'}',
              ),
              subtitle: Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('目标：${day['session_goal'] ?? '旧计划未记录本次目标'}'),
                    const SizedBox(height: 6),
                    Text(
                      '训练法：${methodChoices[day['training_method']] ?? '旧计划未记录训练法'}',
                      style: const TextStyle(
                        color: AppColors.ink,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      [
                        if (day['start_time'] != null) '${day['start_time']}',
                        if (day['duration_minutes'] != null)
                          '${day['duration_minutes']}分钟',
                        '${(day['exercises'] as List).length}个动作',
                      ].join(' · '),
                    ),
                  ],
                ),
              ),
              children: [
                if (day['training_method'] == 'five_by_five')
                  const Text('5×5用于指定主项；恢复周按确认的减量组数执行。'),
                for (final e in day['exercises']) ...[
                  const Divider(height: 24),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '${e['exercise_id'] == day['primary_exercise_id'] ? '主项' : '辅助动作'} · ${exercises[e['exercise_id']] ?? e['name'] ?? e['exercise_id']}',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '${e['weight_kg'] ?? '待确认'} kg · ${e['sets']}组 × ${e['reps']}次',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                  ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      '组间休息${e['rest_seconds']}秒 · 目标余力${e['target_rir'] ?? '待确认'}次',
                      style: const TextStyle(color: AppColors.muted),
                    ),
                  ),
                  if (loadReferenceText(e['load_reference']).isNotEmpty)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Text(
                        loadReferenceText(e['load_reference']),
                        style: const TextStyle(
                          color: AppColors.muted,
                          fontSize: 12,
                        ),
                      ),
                    ),
                ],
              ],
            ),
          ),
      ],
    );
  }
}
