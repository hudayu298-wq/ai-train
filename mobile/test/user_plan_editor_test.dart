import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/user_plan_editor.dart';

void main() {
  testWidgets('AI draft is reviewed before saving with its generation id', (
    tester,
  ) async {
    final requests = <String>[];
    final assessment = {'note': '重量待确认', 'items': <dynamic>[]};
    final draft = {
      'name': 'AI周计划',
      'generation_id': 'draft-123',
      'rationale': '根据画像生成',
      'warmup': '逐步热身',
      'recovery': '安排恢复',
      'progression': '复核余力',
      'assessment': assessment,
      'days': [
        {
          'name': '周一',
          'exercises': [
            {
              'exercise_id': 'bench',
              'weight_kg': null,
              'sets': 3,
              'reps': 6,
              'rest_seconds': 120,
            },
          ],
        },
      ],
    };
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: UserPlanEditor(
              exercises: const {'bench': '平板杠铃卧推'},
              rmRecords: const [],
              onSaved: () async {},
              post: (path, body) async {
                requests.add(path);
                if (path == '/plans/generate') return draft;
                expect(body['generation_id'], 'draft-123');
                expect(body['days'][0]['exercises'][0]['weight_kg'], isNull);
                return {'assessment': assessment};
              },
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('根据画像生成 AI 计划'));
    await tester.pumpAndSettle();
    expect(requests, ['/plans/generate']);
    expect(find.text('制定理由：根据画像生成'), findsOneWidget);
    await tester.ensureVisible(find.text('保存我的计划并评估'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('保存我的计划并评估'));
    await tester.pumpAndSettle();
    expect(requests, ['/plans/generate', '/plans']);
    expect(tester.takeException(), isNull);
  });
  testWidgets(
    'evaluates and saves the user-entered plan without changing values',
    (tester) async {
      final requests = <Map<String, dynamic>>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: UserPlanEditor(
                exercises: const {'bench': '平板杠铃卧推'},
                rmRecords: const [],
                onSaved: () async {},
                post: (path, body) async {
                  requests.add({'path': path, 'body': body});
                  final result = {'note': '参考评估', 'items': <dynamic>[]};
                  return path == '/plans' ? {'assessment': result} : result;
                },
              ),
            ),
          ),
        ),
      );
      Future<void> fill(String label, String text) async {
        final finder = find.byWidgetPredicate(
          (w) => w is TextField && w.decoration?.labelText == label,
        );
        await tester.ensureVisible(finder);
        await tester.enterText(finder, text);
      }

      await fill('计划名称', '我的计划');
      await fill('训练日名称（如周一）', '周二');
      await fill('计划重量 / kg', '73');
      await fill('组数', '4');
      await fill('每组次数', '6');
      await fill('组间休息 / 秒', '120');
      await tester.ensureVisible(find.text('添加到计划'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('添加到计划'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('仅评估草稿'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('仅评估草稿'));
      await tester.pumpAndSettle();
      expect(requests.single['path'], '/plans/assess');
      final plan = requests.single['body'];
      expect(plan['name'], '我的计划');
      expect(plan['days'][0]['name'], '周二');
      expect(plan['days'][0]['exercises'][0], {
        'exercise_id': 'bench',
        'weight_kg': 73.0,
        'sets': 4,
        'reps': 6,
        'rest_seconds': 120,
      });
      await tester.ensureVisible(find.text('保存我的计划并评估'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('保存我的计划并评估'));
      await tester.pumpAndSettle();
      expect(requests.last['path'], '/plans');
      expect(requests.last['body'], plan);
      expect(tester.takeException(), isNull);
    },
  );
}
