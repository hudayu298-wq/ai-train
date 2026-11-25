import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures/module_navigation.dart';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftlab/app.dart';
import 'package:liftlab/auth/login_page.dart';
import 'package:liftlab/auth/session.dart';
import 'package:liftlab/coach_chat.dart';
import 'package:liftlab/library_page.dart';
import 'package:liftlab/health_data_page.dart';
import 'package:liftlab/nutrition_guidance_page.dart';
import 'package:liftlab/user_plan_editor.dart';
import 'package:liftlab/ui_theme.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'fixtures/strength_profile.dart';
import 'fixtures/training_program.dart';

// Synthetic display data only. This client never connects to a running backend.
const exercise = {
  'id': 'bench',
  'name': '杠铃卧推',
  'type': 'weighted',
  'equipment': '杠铃',
  'weight_basis': '含杠铃总重量',
  'movement_pattern': '水平推',
  'body_regions': ['胸部', '手臂'],
  'realtime_supported': true,
  'view': '正侧面拍摄，确保全身和杠铃在画面内。',
};
const samplePlan = {
  'id': 'ui-plan',
  'name': '基础力量',
  'version': 1,
  'source': 'user',
  'cycle_week': 1,
  'cycle_weeks': 4,
  'note': '界面测试样例，不是用户的真实训练计划。',
  'days': [
    {
      'name': '周一 · 上肢',
      'start_time': '19:00',
      'duration_minutes': 45,
      'exercises': [
        {
          'exercise_id': 'bench',
          'name': '杠铃卧推',
          'weight_kg': 50,
          'sets': 3,
          'reps': 8,
          'rest_seconds': 120,
          'target_rir': 3,
        },
      ],
    },
  ],
  'assessment': {'items': []},
};
const facts = {
  'age': 28,
  'height_cm': 175,
  'weight_kg': 70,
  'sex': 'male',
  'goal': 'muscle_gain',
  'experience': 'beginner',
  'training_weekdays': [1, 3, 5],
  'preferred_time': '19:00',
  'session_minutes': 45,
  'equipment': '杠铃、哑铃',
};

dynamic sampleResponse(String path) => switch (path) {
  '/api/strength-profile' => strengthFixture(),
  '/api/catalog' => {
    'exercises': [exercise],
    'foods': [
      {'id': 'rice', 'name': '米饭'},
    ],
  },
  '/api/coach/profile' => {'facts': facts, 'complete': true, 'labels': {}},
  '/api/coach/messages' => {'turns': []},
  '/api/coach/status' => {'configured': true},
  '/api/coach/reminders' => {},
  '/api/onboarding' => {'required': false},
  '/api/plans' => [samplePlan],
  '/api/workouts' => {'items': []},
  '/api/nutrition/today' => {
    'day': '2026-10-25',
    'records': [],
    'groups': [],
    'target_status': 'ready',
    'diary': {'status': 'partial'},
    'interpretation': '今天只记录了一部分，不能据此判断全天摄入不足。',
    'comparison': {
      for (final e in {
        'kcal': [680, 2200],
        'protein': [42, 120],
        'fat': [20, 60],
        'carbs': [83, 295],
      }.entries)
        e.key: {
          'consumed': e.value[0],
          'target': e.value[1],
          'remaining': e.value[1] - e.value[0],
          'percent': e.value[0] / e.value[1] * 100,
          'excess': 0,
        },
    },
  },
  _ => [],
};

final previewKey = GlobalKey();
final mockWrites = <String>[];

Future<void> capture(WidgetTester tester, String name) async {
  if (!const bool.fromEnvironment('UI_PREVIEWS')) return;
  await tester.runAsync(
    () => precacheImage(
      const AssetImage('assets/coach/chibi/steady.png'),
      tester.element(find.byType(MaterialApp)),
    ),
  );
  await tester.pump();
  final boundary = tester.renderObject<RenderRepaintBoundary>(
    find.byKey(previewKey),
  );
  await tester.runAsync(() async {
    final picture = await boundary.toImage(pixelRatio: 1);
    final bytes = await picture.toByteData(format: ui.ImageByteFormat.png);
    final folder = Directory('../.tools/ui-taste/flutter')
      ..createSync(recursive: true);
    File('${folder.path}/$name.png')
        .writeAsBytesSync(bytes!.buffer.asUint8List());
    picture.dispose();
  });
}

Widget frame(Widget child, {double scale = 1}) => RepaintBoundary(
  key: previewKey,
  child: MaterialApp(
    theme: buildAppTheme(),
    debugShowCheckedModeBanner: false,
    builder: (context, child) => LayoutBuilder(
      builder: (context, box) => MediaQuery(
        data: MediaQuery.of(context).copyWith(
          size: Size(box.maxWidth, box.maxHeight),
          disableAnimations: true,
          textScaler: TextScaler.linear(scale),
        ),
        child: child!,
      ),
    ),
    home: child,
  ),
);

Future<void> mountHome(WidgetTester tester, double width) async {
  debugDefaultTargetPlatformOverride = TargetPlatform.linux;
  await tester.binding.setSurfaceSize(Size(width, 900));
  SharedPreferences.setMockInitialValues({});
  FlutterSecureStorage.setMockInitialValues({});
  mockWrites.clear();
  authSession = AuthSession(
    client: MockClient((r) async {
      if (r.method != 'GET') mockWrites.add('${r.method} ${r.url.path}');
      return http.Response(
        jsonEncode(sampleResponse(r.url.path)),
        200,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }),
  );
  await authSession.accept({
    'access_token': 'synthetic-access',
    'refresh_token': 'synthetic-refresh',
    'expires_in': 900,
    'user': {'id': 'ui-synthetic'},
  });
  await tester.pumpWidget(frame(const Home()));
  await tester.pumpAndSettle();
  debugDefaultTargetPlatformOverride = null;
}

Future<void> navigate(WidgetTester tester, double width, String name) async {
  if (width < 1100) {
    await tester.tap(find.byTooltip('Open navigation menu'));
    await tester.pumpAndSettle();
  }
  final destination = find.widgetWithText(ListTile, name);
  await tester.ensureVisible(destination);
  await tester.tap(destination);
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() async {
    final font = FontLoader('LianbanSans')
      ..addFont(rootBundle.load('assets/fonts/NotoSansSC-Regular.otf'));
    await font.load();
    final icons = FontLoader('MaterialIcons')
      ..addFont(
        File(
          '../.tools/flutter/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
        ).readAsBytes().then(ByteData.sublistView),
      );
    await icons.load();
  });

  for (final width in [390.0, 768.0, 1440.0]) {
    testWidgets(
      'home navigation, plan and nutrition at $width without overflow',
      (tester) async {
        addTearDown(() => tester.binding.setSurfaceSize(null));
        await mountHome(tester, width);
        expect(find.byType(CoachChat), findsOneWidget);
        expect(
          find.byTooltip('Open navigation menu'),
          width < 1100 ? findsOneWidget : findsNothing,
        );
        await capture(tester, '${width.toInt()}-chat');
        for (final item in [
          ('训练计划', 'plan'),
          ('饮食', 'nutrition'),
          ('训练记录与复盘', 'history'),
          ('我', 'profile'),
        ]) {
          await navigate(tester, width, item.$1);
          expect(tester.takeException(), isNull);
          await capture(tester, '${width.toInt()}-${item.$2}');
        }
        await tester.pumpWidget(const SizedBox());
      },
    );
  }

  testWidgets('regional profile previews use the real questionnaire layout', (
    tester,
  ) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    for (final width in [390.0, 768.0, 1440.0]) {
      await mountHome(tester, width);
      await navigate(tester, width, '我');
      await openSection(tester, '力量评估');
      for (final item in [
        ('胸部力量参考', 'chest'),
        ('背部力量参考', 'back'),
        ('腿部力量参考', 'legs'),
      ]) {
        await openSection(tester, '${item.$1.substring(0, 2)}表现');
        await tester.ensureVisible(find.text(item.$1));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull);
        await capture(tester, '${width.toInt()}-strength-${item.$2}');
        await sectionOverview(tester, label: '选择评估部位');
      }
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets('generated program hierarchy at mobile tablet and desktop', (
    tester,
  ) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    for (final width in [390.0, 768.0, 1440.0]) {
      await tester.binding.setSurfaceSize(Size(width, 900));
      await tester.pumpWidget(
        frame(
          Scaffold(
            body: SingleChildScrollView(
              child: UserPlanEditor(
                compact: true,
                exercises: const {
                  'bench': '杠铃卧推',
                  'barbell_row': '杠铃划船',
                  'squat': '杠铃深蹲',
                },
                onSaved: () async {},
                post: (p, b) async => trainingProgramFixture(),
              ),
            ),
          ),
          scale: width == 390 ? 1.3 : 1,
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('根据画像生成 AI 计划'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('三日推拉腿计划'));
      await tester.pumpAndSettle();
      await capture(tester, '${width.toInt()}-generated-program');
      await tester.ensureVisible(find.textContaining('周一 · 推'));
      await tester.tap(find.textContaining('周一 · 推'));
      await tester.pumpAndSettle();
      await capture(tester, '${width.toInt()}-generated-day');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    }
  });

  testWidgets(
    'health and nutrition groups fit three widths without accidental writes',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final writes = <String>[];
      Future<dynamic> request(String path, String method, Object? body) async {
        if (method != 'GET') writes.add('$method $path');
        return switch (path) {
          '/health-data/settings' => {
            'storage_enabled': true,
            'ai_context_enabled': false,
          },
          '/health-data/summary' => {'metrics': {}, 'recent_checkins': []},
          '/health-data/measurements' => {'items': []},
          '/nutrition-guidance/settings' => {
            'activity_factor': 1.4,
            'protein_g_per_kg': 1.6,
            'fat_g_per_kg': 0.8,
            'energy_adjustment_kcal': null,
            'eligibility': 'eligible',
            'calibration_enabled': false,
          },
          '/nutrition-guidance/target' => {
            'target': {'kcal': 2200, 'protein': 120, 'fat': 60, 'carbs': 295},
            'target_source': 'formula_estimate',
            'rules': [],
            'sources': [],
            'steps': [],
            'warnings': [],
          },
          '/nutrition-guidance/calibration' => {
            'eligible': false,
            'reasons': ['需更多完整饮食日'],
          },
          '/nutrition-guidance/suggestions' => {'items': []},
          _ => {},
        };
      }

      for (final width in [390.0, 768.0, 1440.0]) {
        await tester.binding.setSurfaceSize(Size(width, 900));
        await tester.pumpWidget(
          frame(
            HealthDataPage(request: request),
            scale: width == 390 ? 1.3 : 1,
          ),
        );
        await tester.pumpAndSettle();
        expect(find.text('数值'), findsNothing);
        await capture(tester, '${width.toInt()}-health-groups');
        await openSection(tester, '添加测量');
        await tester.enterText(find.widgetWithText(TextField, '数值'), '70');
        await capture(tester, '${width.toInt()}-health-measurement');
        await sectionOverview(tester);
        await openSection(tester, '恢复反馈');
        expect(find.widgetWithText(TextField, '数值'), findsNothing);
        await sectionOverview(tester);
        await openSection(tester, '添加测量');
        expect(
          tester
              .widget<TextField>(find.widgetWithText(TextField, '数值'))
              .controller!
              .text,
          '70',
        );
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
        await tester.pumpWidget(
          frame(
            NutritionGuidancePage(request: request),
            scale: width == 390 ? 1.3 : 1,
          ),
        );
        await tester.pumpAndSettle();
        await capture(tester, '${width.toInt()}-nutrition-groups');
        await openSection(tester, '个人设置');
        await tester.enterText(
          find.widgetWithText(TextField, '蛋白质（1.4–2.0 g/kg/日）'),
          '1.8',
        );
        await capture(tester, '${width.toInt()}-nutrition-settings');
        await sectionOverview(tester);
        await openSection(tester, '趋势反馈');
        await sectionOverview(tester);
        await openSection(tester, '个人设置');
        expect(
          tester
              .widget<TextField>(
                find.widgetWithText(TextField, '蛋白质（1.4–2.0 g/kg/日）'),
              )
              .controller!
              .text,
          '1.8',
        );
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
      }
      expect(writes, isEmpty);
    },
  );

  testWidgets(
    'topic fills an editable draft without submitting; resizing retains input',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await mountHome(tester, 1440);
      await tester.tap(find.text('安排训练'));
      await tester.pumpAndSettle();
      final composer = find.descendant(
        of: find.byType(CoachChat),
        matching: find.byType(TextField),
      );
      final text = tester.widget<TextField>(composer).controller!.text;
      expect(text, contains('请先查看我的画像'));
      expect(mockWrites, isEmpty);
      await tester.binding.setSurfaceSize(const Size(390, 844));
      await tester.pumpAndSettle();
      expect(tester.widget<TextField>(composer).controller!.text, text);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  testWidgets(
    'mobile library folds filters and search remains usable with large text',
    (tester) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(const Size(390, 844));
      final calls = <String>[];
      await tester.pumpWidget(
        frame(
          LibraryPage(
            kind: 'exercises',
            onChanged: () async {},
            request: (path, _, _) async {
              calls.add(path);
              return {
                'items': [exercise],
                'total': 1,
                'categories': ['水平推'],
                'body_parts': ['胸部'],
              };
            },
          ),
          scale: 1.3,
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('杠铃卧推'), findsOneWidget);
      expect(find.text('全部分类'), findsNothing);
      await capture(tester, '390-library');
      await tester.enterText(find.byType(TextField), '卧推');
      await tester.tap(find.byIcon(Icons.search));
      await tester.pumpAndSettle();
      expect(Uri.parse(calls.last).queryParameters['q'], '卧推');
      await tester.tap(find.text('筛选与资料语言'));
      await tester.pumpAndSettle();
      expect(find.text('全部分类'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    },
  );

  for (final width in [390.0, 768.0, 1440.0]) {
    testWidgets('login form at $width keeps controls accessible', (
      tester,
    ) async {
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await tester.binding.setSurfaceSize(Size(width, 900));
      await http.runWithClient(
        () async {
          await tester.pumpWidget(
            frame(const LoginPage(), scale: width == 390 ? 1.3 : 1),
          );
          await tester.pumpAndSettle();
          await tester.enterText(find.byType(TextField).last, 'example-only');
          await tester.tap(find.byTooltip('显示密码'));
          await tester.pumpAndSettle();
          expect(
            tester.widget<TextField>(find.byType(TextField).last).obscureText,
            false,
          );
          await tester.enterText(find.byType(TextField).last, '');
          await capture(tester, '${width.toInt()}-login');
          await tester.ensureVisible(find.widgetWithText(FilledButton, '登录'));
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox());
        },
        () => MockClient(
          (_) async => http.Response(
            jsonEncode({
              'policy_version': 'ui-test',
              'registration_open': false,
              'wechat_enabled': false,
            }),
            200,
          ),
        ),
      );
    });
  }
}
