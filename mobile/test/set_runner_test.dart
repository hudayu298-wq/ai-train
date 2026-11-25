import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/set_runner.dart';

Finder field(String label) => find.byWidgetPredicate(
  (w) => w is TextField && w.decoration?.labelText == label,
);

void main() {
  test('alternating groups interleave unequal set counts without losing destination identity', () {
    final ordered = interleaveSteps([
      {'exercise_id': 'a', 'group': 1, 'destination_index': 0},
      {'exercise_id': 'a', 'group': 1, 'destination_index': 1},
      {'exercise_id': 'a', 'group': 1, 'destination_index': 2},
      {'exercise_id': 'b', 'group': 1, 'destination_index': 3},
      {'exercise_id': 'b', 'group': 1, 'destination_index': 4},
      {'exercise_id': 'c', 'group': 0, 'destination_index': 5},
    ]);
    expect(ordered.map((s) => s['destination_index']), [0, 3, 1, 4, 2, 5]);
  });
  testWidgets(
    'targets never fill facts; confirmation measures rest and advances only on tap',
    (tester) async {
      var now = DateTime.utc(2026, 10, 24);
      final records = <Map<String, dynamic>>[];
      await tester.pumpWidget(
        MaterialApp(
          home: SetRunner(
            steps: [
              for (var i = 1; i <= 2; i++)
                {
                  'name': '卧推',
                  'set_number': i,
                  'target': {
                    'weight_kg': 75,
                    'reps': 5,
                    'rest_seconds': 60,
                    'target_rir': 2,
                  },
                },
            ],
            now: () => now,
            onRecorded: (index, actual) =>
                records.add({'index': index, ...actual}),
          ),
        ),
      );
      expect(
        tester.widget<TextField>(field('本组实际重量 / kg')).controller!.text,
        '',
      );
      await tester.tap(find.text('确认本组并开始休息'));
      await tester.pump();
      expect(records, isEmpty);
      expect(find.textContaining('请确认实际重量'), findsOneWidget);
      await tester.enterText(field('本组实际重量 / kg'), '40');
      await tester.enterText(field('本组实际次数'), '6');
      await tester.enterText(field('本组 RPE 1–10'), '8');
      await tester.tap(find.text('确认本组并开始休息'));
      await tester.pump();
      expect(records.single['weight_kg'], 40);
      expect(records.single.containsKey('rest_seconds'), false);
      now = now.add(const Duration(seconds: 70));
      await tester.pump(const Duration(seconds: 70));
      expect(find.textContaining('参考休息时间已到'), findsOneWidget);
      expect(records, hasLength(1)); // A timer never confirms another set.
      await tester.tap(find.text('结束休息，记录下一组'));
      await tester.pump();
      expect(records.last['rest_seconds'], 70);
      expect(find.textContaining('第2组'), findsOneWidget);
      expect(tester.widget<TextField>(field('本组实际次数')).controller!.text, '');
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 2));
      expect(records, hasLength(2));
    },
  );

  testWidgets(
    'last set returns to confirmation without inventing post workout rest',
    (tester) async {
      final records = <Map>[];
      await tester.pumpWidget(
        MaterialApp(
          home: SetRunner(
            steps: const [
              {
                'name': '卧推',
                'set_number': 1,
                'actual': {'weight_kg': 40, 'reps': 5, 'rpe': 7},
              },
            ],
            onRecorded: (_, actual) => records.add(actual),
          ),
        ),
      );
      await tester.tap(find.text('确认本组并开始休息'));
      await tester.pump();
      expect(find.text('返回确认训练'), findsOneWidget);
      expect(records.single.containsKey('rest_seconds'), false);
      expect(records.single['reps'], 5);
    },
  );
}
