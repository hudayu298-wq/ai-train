import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/workout_log.dart';
import 'package:shared_preferences/shared_preferences.dart';

const exercises = {
  'bench': {'name': '杠铃卧推', 'weight_basis': '含杠铃总重', 'movement_pattern': '水平推'},
  'squat': {'name': '高杠深蹲', 'weight_basis': '含杠铃总重', 'movement_pattern': '蹲'},
};

Finder field(String label) => find.byWidgetPredicate(
  (w) => w is TextField && w.decoration?.labelText == label,
);

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  Future<void> largeView(WidgetTester tester) async {
    tester.view.physicalSize = const Size(700, 1900);
    tester.view.devicePixelRatio = 1;
    addTearDown(() {
      tester.view.resetPhysicalSize();
      tester.view.resetDevicePixelRatio();
    });
  }

  Map<String, dynamic> response(Map input) => {
    'id': 'workout-${input['request_id']}',
    ...input,
    'summary': {
      'summary': '已记录1个动作、2组、14次。',
      'exercises': [],
      'note': '训练量不代表力量提升',
    },
    'ai_review': null,
  };

  testWidgets(
    'plan targets stay separate and runner writes only confirmed draft values',
    (tester) async {
      await largeView(tester);
      Map? submitted;
      await tester.pumpWidget(
        MaterialApp(
          home: WorkoutLogPage(
            request: (path, method, body) async {
              if (path == '/workouts/start') {
                return {
                  'id': 'execution-1',
                  'plan_snapshot': {
                    'id': 'plan-1',
                    'version': 1,
                    'days': [
                      {
                        'name': '周一',
                        'exercises': [
                          {
                            'exercise_id': 'bench',
                            'sets': 1,
                            'weight_kg': 75,
                            'reps': 5,
                            'rest_seconds': 60,
                            'target_rir': 2,
                          },
                        ],
                      },
                    ],
                  },
                  'started_at': '2026-10-24T10:00:00Z',
                };
              }
              if (path != '/workouts') throw Exception('模型未配置');
              submitted = body as Map;
              return response(submitted!);
            },
            onSaved: () async {},
            exercises: exercises,
            coachId: 'gentle',
            currentPlan: const {
              'id': 'plan-1',
              'days': [
                {
                  'name': '周一',
                  'exercises': [
                    {
                      'exercise_id': 'bench',
                      'sets': 1,
                      'weight_kg': 75,
                      'reps': 5,
                      'rest_seconds': 60,
                      'target_rir': 2,
                    },
                  ],
                },
              ],
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      final daySelector = find.byWidgetPredicate(
        (w) =>
            w is DropdownButtonFormField<String> &&
            w.decoration.labelText == '本次对应哪个计划训练日（可选）',
      );
      await tester.tap(daySelector);
      await tester.pumpAndSettle();
      await tester.tap(find.text('周一').last);
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(field('重量 / kg')).controller!.text, '');
      expect(tester.widget<TextField>(field('实际次数')).controller!.text, '');
      await tester.ensureVisible(find.text('开始逐组训练与休息计时'));
      await tester.tap(find.text('开始逐组训练与休息计时'));
      await tester.pumpAndSettle();
      expect(find.textContaining('75 kg × 5次'), findsOneWidget);
      await tester.enterText(field('本组实际重量 / kg'), '40');
      await tester.enterText(field('本组实际次数'), '6');
      await tester.enterText(field('本组 RPE 1–10'), '8');
      await tester.tap(find.text('确认本组并开始休息'));
      await tester.pumpAndSettle();
      expect(submitted, isNull);
      await tester.tap(find.text('返回确认训练'));
      await tester.pumpAndSettle();
      expect(
        tester.widget<TextField>(field('重量 / kg')).controller!.text,
        '40.0',
      );
      await tester.ensureVisible(find.text('完成训练并生成复盘'));
      await tester.tap(find.text('完成训练并生成复盘'));
      await tester.pumpAndSettle();
      expect(submitted!['plan_id'], 'plan-1');
      expect(submitted!['execution_id'], 'execution-1');
      expect(submitted!['completed_plan_day'], false);
      expect(submitted!['exercises'][0]['sets'][0]['weight_kg'], 40);
      expect(submitted!['exercises'][0]['sets'][0]['reps'], 6);
    },
  );

  testWidgets(
    'confirmed sets save once, review failure retains record and same-id retry survives navigation',
    (tester) async {
      await largeView(tester);
      final payloads = <Map>[];
      int refreshes = 0;
      Future<dynamic> request(String path, String method, Object? body) async {
        if (path.endsWith('/review')) throw Exception('未配置模型');
        if (path.endsWith('/progression')) throw Exception('未配置模型');
        payloads.add(jsonDecode(jsonEncode(body)) as Map);
        if (payloads.length == 1) throw Exception('网络中断');
        return response(body as Map);
      }

      Widget page() => MaterialApp(
        home: WorkoutLogPage(
          request: request,
          onSaved: () async {
            refreshes++;
          },
          exercises: exercises,
          coachId: 'gentle',
        ),
      );
      await tester.pumpWidget(page());
      await tester.pumpAndSettle();
      await tester.tap(find.text('添加动作'));
      await tester.pumpAndSettle();
      await tester.enterText(field('重量 / kg'), '40');
      await tester.enterText(field('实际次数'), '8');
      await tester.enterText(field('RPE 1–10'), '7');
      await tester.tap(find.text('添加一组'));
      await tester.pumpAndSettle();
      await tester.enterText(field('重量 / kg').at(1), '40');
      await tester.enterText(field('实际次数').at(1), '6');
      await tester.enterText(field('RPE 1–10').at(1), '9');
      await tester.tap(find.text('本组出现疼痛或不适').last);
      await tester.pumpAndSettle();
      await tester.tap(find.text('完成训练并生成复盘'));
      await tester.pumpAndSettle();
      expect(find.textContaining('网络中断'), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
      await tester.pumpWidget(page());
      await tester.pumpAndSettle();
      expect(find.text('已恢复本机未完成草稿。'), findsOneWidget);
      expect(tester.widget<TextField>(field('重量 / kg').first).enabled, false);
      await tester.tap(find.text('重试保存本次训练'));
      await tester.pumpAndSettle();
      expect(payloads.length, 2);
      expect(payloads[0], payloads[1]);
      expect(payloads[1]['exercises'][0]['sets'][1]['pain'], true);
      expect(payloads[1]['exercises'][0]['sets'][1]['reps'], 6);
      expect(refreshes, 1);
      expect(find.textContaining('训练与基础复盘已保存'), findsOneWidget);
      expect(find.text('已记录1个动作、2组、14次。'), findsOneWidget);
      expect(
        (await SharedPreferences.getInstance()).getString('workout-draft-v1'),
        isNull,
      );
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'live counts pre-create sets but require actual repetitions, load and RPE confirmation',
    (tester) async {
      await largeView(tester);
      int posts = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: WorkoutLogPage(
            request: (p, m, b) async {
              posts++;
              return {};
            },
            onSaved: () async {},
            exercises: exercises,
            coachId: 'steady',
            liveExerciseId: 'bench',
            detectedSets: const [4, 5],
            liveDurationMinutes: 12,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(field('实际次数'), findsNWidgets(2));
      expect(
        tester.widget<TextField>(field('实际次数').first).controller!.text,
        '',
      );
      expect(find.textContaining('实时实验计次共 9 次'), findsOneWidget);
      await tester.tap(find.text('完成训练并生成复盘'));
      await tester.pumpAndSettle();
      expect(posts, 0);
      expect(find.textContaining('请逐组确认重量'), findsOneWidget);
      expect(tester.widget<TextField>(field('重量 / kg').first).enabled, true);
      await tester.pumpWidget(const SizedBox());
    },
  );
}
