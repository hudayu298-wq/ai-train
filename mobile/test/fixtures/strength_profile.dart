// Synthetic questionnaire data; never sent to a live backend.
Map<String, dynamic> strengthFixture({bool ready = true}) {
  const names = {
    'bench': '平板杠铃卧推',
    'dumbbell_bench': '平板哑铃卧推',
    'barbell_row': '俯身杠铃划船',
    'squat': '高杠杠铃深蹲',
  };
  return {
    'ready': ready,
    'revision': ready ? 'synthetic-strength-revision' : null,
    'items': ready
        ? [
            for (final p in [
              ('chest', 'bench', 60),
              ('back', 'barbell_row', 40),
              ('legs', 'squat', 80),
            ])
              {
                'region': p.$1,
                'exercise_id': p.$2,
                'weight_kg': p.$3,
                'reps': 8,
                'rir': 2,
                'equipment_id': '',
                'confirmed': true,
                'pain': false,
                'measured_on': DateTime.now()
                    .toUtc()
                    .add(const Duration(hours: 8))
                    .toIso8601String()
                    .split('T')
                    .first,
              },
          ]
        : [],
    'missing': ready
        ? []
        : [
            for (final e in {'chest': '胸部', 'back': '背部', 'legs': '腿部'}.entries)
              {'region': e.key, 'label': e.value},
          ],
    'options': {
      for (final e in {
        'chest': ['bench', 'dumbbell_bench'],
        'back': ['barbell_row'],
        'legs': ['squat'],
      }.entries)
        e.key: [
          for (final id in e.value)
            {
              'id': id,
              'name': names[id],
              'unit_label': id == 'dumbbell_bench' ? '单只哑铃重量' : '含杠铃杆的总重量',
              'requires_equipment_id': false,
            },
        ],
    },
  };
}
