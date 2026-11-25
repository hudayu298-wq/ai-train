import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/profile_setup.dart';
import 'package:liftlab/user_plan_editor.dart';
import 'package:liftlab/ui_components.dart';

import 'fixtures/training_program.dart';
import 'profile_setup_test.dart' show validFacts;

void main() {
  testWidgets(
    'new AI plan groups daily goals before details and confirms their metadata',
    (tester) async {
      final calls = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AppContent(
              child: UserPlanEditor(
                compact: true,
                exercises: const {
                  'bench': '卧推',
                  'barbell_row': '划船',
                  'squat': '深蹲',
                },
                onSaved: () async {},
                post: (p, b) async {
                  calls.add(p);
                  if (p == '/plans/generate') return trainingProgramFixture();
                  expect(b['generation_id'], 'draft-program');
                  expect(b['days'][1]['focus'], 'pull');
                  expect(b['days'][1]['training_method'], 'straight_sets');
                  expect(b['days'][1]['session_goal'], '完成背部拉力训练，保持动作可控');
                  return {
                    'assessment': {'note': '确认完成', 'items': []},
                  };
                },
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('根据画像生成 AI 计划'));
      await tester.pumpAndSettle();
      expect(find.textContaining('目标：完成背部拉力训练'), findsOneWidget);
      expect(find.text('训练法：常规固定组'), findsNWidgets(3));
      expect(find.text('主项 · 卧推'), findsNothing);
      expect(find.text('制定理由：详细制定依据应按需展开'), findsNothing);
      expect(calls, ['/plans/generate']);
      await tester.ensureVisible(find.textContaining('周一 · 推'));
      await tester.tap(find.textContaining('周一 · 推'));
      await tester.pumpAndSettle();
      expect(find.text('主项 · 卧推'), findsOneWidget);
      expect(find.text('40 kg · 3组 × 8次'), findsOneWidget);
      await tester.ensureVisible(find.text('确认使用这个计划'));
      await tester.tap(find.text('确认使用这个计划'));
      await tester.pumpAndSettle();
      expect(calls, ['/plans/generate', '/plans']);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'split and method are independent profile facts; insufficient days never submit',
    (tester) async {
      var writes = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AppContent(
              child: ProfileSetup(
                facts: {
                  ...validFacts,
                  'training_split': 'bodypart_five',
                  'training_method': 'five_by_five',
                },
                request: (p, m, b) async {
                  writes++;
                  return {};
                },
                onSaved: () async {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('保存画像'));
      await tester.tap(find.text('保存画像'));
      await tester.pumpAndSettle();
      expect(writes, 0);
      expect(find.textContaining('至少需5个训练日'), findsOneWidget);
      expect(find.text('组次训练法偏好'), findsOneWidget);
      expect(find.text('主项5×5'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
