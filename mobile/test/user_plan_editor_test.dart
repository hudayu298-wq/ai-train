import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/user_plan_editor.dart';

void main() {
  testWidgets('plan filters intersect and edited entries remain selectable', (
    tester,
  ) async {
    Map<String, dynamic>? saved;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: UserPlanEditor(
              exercises: const {'bench': '杠铃卧推', 'curl': '哑铃弯举'},
              exerciseDetails: const {
                'bench': {
                  'movement_pattern': '水平推',
                  'body_regions': ['胸部', '手臂'],
                  'weight_basis': '含杠铃总重量',
                },
                'curl': {
                  'movement_pattern': '肘屈曲',
                  'body_regions': ['手臂'],
                  'weight_basis': '单只哑铃重量',
                },
              },
              rmRecords: const [],
              onSaved: () async {},
              post: (path, body) async {
                saved = body;
                return {
                  'assessment': {'note': '已评估', 'items': <dynamic>[]},
                };
              },
            ),
          ),
        ),
      ),
    );
    Finder dropdown(String label) => find.byWidgetPredicate(
      (w) =>
          w is DropdownButtonFormField<String> &&
          w.decoration.labelText == label,
    );
    Future<void> choose(String label, String value) async {
      await tester.ensureVisible(dropdown(label));
      await tester.pumpAndSettle();
      await tester.tap(dropdown(label));
      await tester.pumpAndSettle();
      await tester.tap(find.text(value).last);
      await tester.pumpAndSettle();
    }

    await choose('关节动作分类', '肘屈曲');
    expect(find.text('可选 1 个负重动作。'), findsOneWidget);
    await choose('训练部位', '胸部');
    expect(find.text('当前分类与部位下没有可用动作，请调整筛选。'), findsOneWidget);
    final add = find.widgetWithText(OutlinedButton, '添加到计划');
    expect(tester.widget<OutlinedButton>(add).onPressed, isNull);
    await choose('训练部位', '手臂');
    expect(find.textContaining('单只哑铃重量'), findsOneWidget);
    Future<void> fill(String label, String value) async {
      final finder = find.byWidgetPredicate(
        (w) => w is TextField && w.decoration?.labelText == label,
      );
      await tester.ensureVisible(finder);
      await tester.enterText(finder, value);
      await tester.pumpAndSettle();
    }

    await fill('计划名称', '按分类计划');
    await fill('训练日名称（如周一）', '周一');
    await fill('计划重量 / kg', '10');
    await fill('组数', '3');
    await fill('每组次数', '8');
    await fill('组间休息 / 秒', '90');
    await tester.ensureVisible(add);
    await tester.pumpAndSettle();
    await tester.tap(add);
    await tester.pumpAndSettle();
    await choose('关节动作分类', '水平推');
    await tester.ensureVisible(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle();
    await tester.tap(find.byIcon(Icons.edit_outlined));
    await tester.pumpAndSettle();
    expect(find.text('全部关节动作'), findsOneWidget);
    expect(find.text('全部训练部位'), findsOneWidget);
    final update = find.text('更新该动作');
    await tester.ensureVisible(update);
    await tester.pumpAndSettle();
    await tester.tap(update);
    await tester.pumpAndSettle();
    final save = find.text('保存我的计划并评估');
    await tester.ensureVisible(save);
    await tester.pumpAndSettle();
    await tester.tap(save);
    await tester.pumpAndSettle();
    expect(saved!['days'][0]['exercises'][0]['exercise_id'], 'curl');
    expect(tester.takeException(), isNull);
  });
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
        await tester.pumpAndSettle();
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
