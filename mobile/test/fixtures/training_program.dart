// Synthetic plan for display/interaction checks; never a user's training facts.
Map<String, dynamic> trainingProgramFixture() => {
  'id': 'display-program',
  'generation_id': 'draft-program',
  'name': '三日推拉腿计划',
  'split_type': 'push_pull_legs',
  'cycle_weeks': 4,
  'rationale': '详细制定依据应按需展开',
  'warmup': '逐步热身核对负重',
  'recovery': '结合恢复反馈',
  'progression': '依确认记录评估',
  'risk_warnings': [],
  'assessment': {'note': '起始建议需校准', 'items': []},
  'days': [
    for (final p in [
      ('周一', 'push', 'bench', '完成胸肩推举训练，核对主项余力'),
      ('周三', 'pull', 'barbell_row', '完成背部拉力训练，保持动作可控'),
      ('周五', 'legs', 'squat', '完成下肢训练，核对实际恢复'),
    ])
      {
        'name': p.$1,
        'focus': p.$2,
        'session_goal': p.$4,
        'training_method': 'straight_sets',
        'primary_exercise_id': p.$3,
        'start_time': '19:00',
        'duration_minutes': 45,
        'exercises': [
          {
            'exercise_id': p.$3,
            'weight_kg': 40,
            'sets': 3,
            'reps': 8,
            'rest_seconds': 120,
            'target_rir': 3,
            'load_reference': {'label': '同动作实际表现参考', 'needs_calibration': true},
          },
        ],
      },
  ],
};
