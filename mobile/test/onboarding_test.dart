import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/fitness_onboarding.dart';

import 'fixtures/strength_profile.dart';

void main() {
  testWidgets(
    'profile save automatically generates a draft and requires confirmation',
    (tester) async {
      tester.view.physicalSize = const Size(800, 1600);
      tester.view.devicePixelRatio = 1;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final calls = <String>[];
      Map<String, dynamic>? submittedProfile;
      final facts = {
        'age': 28,
        'height_cm': 175,
        'weight_kg': 70,
        'sex': 'male',
        'goal': 'muscle_gain',
        'experience': 'beginner',
        'days': 1,
        'training_weekdays': [1],
        'preferred_time': '19:00',
        'session_minutes': 45,
        'equipment': '杠铃和哑铃',
      };
      var finished = false;
      Future<dynamic> request(String path, String method, Object? body) async {
        calls.add('$method $path');
        if (path == '/onboarding') {
          return {'required': true, 'facts': facts, 'step': 'profile'};
        }
        if (path == '/rm') return [];
        if (path == '/strength-profile') return strengthFixture();
        if (path == '/coach/profile') {
          submittedProfile = Map<String, dynamic>.from(body as Map);
          return {};
        }
        if (path == '/plans/generate') {
          return {
            'name': '四周基础计划',
            'generation_id': 'draft-1',
            'cycle_weeks': 4,
            'weeks': ['第1周校准', '第2周复核', '第3周进阶', '第4周总结'],
            'risk_warnings': [],
            'rationale': '适配每周一45分钟',
            'warmup': '热身',
            'recovery': '恢复',
            'progression': '按完成记录调整',
            'days': [
              {
                'name': '周一 · 训练1',
                'weekday': 1,
                'start_time': '19:00',
                'duration_minutes': 45,
                'exercises': [
                  {
                    'exercise_id': 'bench',
                    'weight_kg': 50,
                    'sets': 3,
                    'reps': 5,
                    'rest_seconds': 120,
                  },
                ],
              },
            ],
            'assessment': {'note': '重量待确认', 'items': []},
          };
        }
        if (path == '/plans') {
          expect((body as Map)['generation_id'], 'draft-1');
          return {
            'assessment': {'note': '已确认', 'items': []},
          };
        }
        if (path == '/onboarding/complete') return {'complete': true};
        throw Exception('Unexpected $path');
      }

      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: FilledButton(
                onPressed: () => Navigator.push(
                  context,
                  MaterialPageRoute<void>(
                    builder: (_) => FitnessOnboarding(
                      request: request,
                      exercises: const {'bench': '卧推'},
                      details: const {},
                      onFinished: () async {
                        finished = true;
                      },
                    ),
                  ),
                ),
                child: const Text('开始'),
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.text('开始'));
      await tester.pumpAndSettle();
      expect(find.text('建立你的训练画像'), findsOneWidget);
      final save = find.text('保存画像并生成训练计划');
      await tester.ensureVisible(save);
      await tester.pumpAndSettle();
      await tester.tap(save);
      await tester.pumpAndSettle();
      expect(submittedProfile?['training_weekdays'], [1]);
      expect(submittedProfile?['session_minutes'], 45);
      expect(calls, contains('POST /plans/generate'));
      expect(calls, isNot(contains('POST /plans')));
      expect(find.text('确认使用这个计划'), findsOneWidget);
      expect(find.text('我的 RM 数据'), findsNothing);
      await tester.ensureVisible(find.text('确认使用这个计划'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('确认使用这个计划'));
      await tester.pumpAndSettle();
      expect(calls, contains('POST /onboarding/complete'));
      expect(finished, true);
      expect(find.text('开始'), findsOneWidget);
    },
  );
}
