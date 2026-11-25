import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/cycle_plan_panel.dart';

Map<String, dynamic> cyclePlan() => {
  'id': 'plan-current',
  'cycle_week': 1,
  'cycle_weeks': 2,
  'cycle_status': {
    'guidance': '断训后先复核',
    'pending_days': ['周一'],
    'interruption_review_required': true,
    'deload_suggested': true,
    'deload_preview': [
      {'day': '周一', 'exercise_id': 'bench', 'before_sets': 4, 'after_sets': 3},
    ],
  },
  'cycle_schedule': [
    for (var i = 1; i <= 2; i++)
      {
        'week': i,
        'phase': i == 1 ? 'foundation' : 'deload',
        'purpose': i == 1 ? '校准' : '恢复',
        'days': [
          {
            'name': '周一',
            'exercises': [
              {
                'exercise_id': 'bench',
                'weight_kg': 50,
                'sets': i == 1 ? 4 : 2,
                'reps': 6,
                'target_rir': i == 1 ? 3 : 4,
                'rest_seconds': 120,
              },
            ],
          },
        ],
      },
  ],
};

void main() {
  testWidgets(
    'week preview displays the actual prescribed reduction and effort',
    (tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CycleSchedulePreview(
                plan: cyclePlan(),
                exercises: const {'bench': '卧推'},
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('2周可执行目标'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('第2周 · 减量与恢复'));
      await tester.pumpAndSettle();
      await tester.tap(find.textContaining('周一 · 待注明训练部位'));
      await tester.pumpAndSettle();
      expect(find.text('50 kg · 2组 × 6次'), findsOneWidget);
      expect(find.text('组间休息120秒 · 目标余力4次'), findsOneWidget);
    },
  );

  testWidgets(
    'confirmed deload shows concrete targets and retries one operation',
    (tester) async {
      final requests = <Map<String, dynamic>>[];
      var saved = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: CyclePlanPanel(
                plan: cyclePlan(),
                exercises: const {'bench': '卧推'},
                onSaved: () async {
                  saved++;
                },
                post: (path, payload) async {
                  expect(path, '/plans/cycle/actions');
                  requests.add(Map<String, dynamic>.from(payload));
                  if (requests.length == 1) throw Exception('temporary');
                  return {'summary': '已确认减量'};
                },
              ),
            ),
          ),
        ),
      );
      expect(find.text('周一 · 卧推：4 → 3组'), findsOneWidget);
      final action = find.text('确认降低本周组数并重启');
      await tester.tap(action);
      await tester.pumpAndSettle();
      await tester.tap(action);
      await tester.pumpAndSettle();
      expect(requests.length, 2);
      expect(requests.first, requests.last);
      expect(requests.first['base_plan_id'], 'plan-current');
      expect(requests.first['action'], 'deload_week');
      expect(saved, 1);
      expect(find.text('已确认减量'), findsOneWidget);
    },
  );
}
