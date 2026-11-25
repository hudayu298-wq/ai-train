import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftlab/app.dart';
import 'package:liftlab/coach_chat.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:liftlab/auth/session.dart';

void main() {
  testWidgets(
    'privacy refresh discards an in-flight reply and reloads history',
    (tester) async {
      final response = Completer<Map<String, dynamic>>();
      var reads = 0;
      Future<dynamic> request(String path, String method, Object? body) async {
        if (path == '/coach/status') return {'configured': true};
        if (method == 'GET') {
          reads++;
          return {'turns': <dynamic>[]};
        }
        return response.future;
      }

      Widget chat(int token) => MaterialApp(
        home: Scaffold(
          body: CoachChat(
            refreshToken: token,
            request: request,
            onProfileChanged: () async {},
          ),
        ),
      );
      await tester.pumpWidget(chat(0));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '待发送内容');
      await tester.tap(find.byTooltip('发送消息'));
      await tester.pump();
      await tester.pumpWidget(chat(1));
      await tester.pump();
      response.complete({
        'request_id': 'old',
        'reply': '已删除来源的旧回复',
        'user_message': '待发送内容',
        'profile_changes': <dynamic>[],
      });
      await tester.pumpAndSettle();
      expect(find.text('已删除来源的旧回复'), findsNothing);
      expect(reads, 2);
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '待发送内容',
      );
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('late history response cannot undo privacy refresh', (
    tester,
  ) async {
    final old = Completer<Map<String, dynamic>>();
    var reads = 0;
    Future<dynamic> request(String path, String method, Object? body) async {
      if (path == '/coach/status') return {'configured': true};
      if (++reads == 1) return old.future;
      return {'turns': <dynamic>[]};
    }

    Widget chat(int token) => MaterialApp(
      home: Scaffold(
        body: CoachChat(
          refreshToken: token,
          request: request,
          onProfileChanged: () async {},
        ),
      ),
    );
    await tester.pumpWidget(chat(0));
    await tester.pump();
    await tester.pumpWidget(chat(1));
    await tester.pumpAndSettle();
    old.complete({
      'turns': [
        {
          'request_id': 'old',
          'user_message': '旧问题',
          'reply': '过期历史',
          'profile_changes': <dynamic>[],
        },
      ],
    });
    await tester.pumpAndSettle();
    expect(find.text('过期历史'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('chat saves a turn and displays extracted evidence', (
    tester,
  ) async {
    int profileReloads = 0;
    final result = {
      'request_id': 'previous-0001',
      'user_message': '我28岁',
      'reply': '你目前最想达成什么目标？',
      'profile_changes': [
        {'label': '年龄', 'field': 'age', 'value': 28, 'evidence': '28岁'},
      ],
    };
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CoachChat(
            onProfileChanged: () async {
              profileReloads++;
            },
            request: (path, method, body) async {
              if (path == '/coach/status') return {'configured': true};
              if (method == 'GET') return {'turns': <dynamic>[]};
              final input = body as Map;
              expect(input['message'], '我28岁');
              return {...result, 'request_id': input['request_id']};
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '我28岁');
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('发送消息'));
    await tester.pumpAndSettle();
    expect(profileReloads, 1);
    expect(find.text('我28岁'), findsOneWidget);
    expect(find.text('你目前最想达成什么目标？'), findsOneWidget);
    final saved = find.text('已记录画像：年龄');
    await tester.ensureVisible(saved);
    await tester.pumpAndSettle();
    await tester.tap(saved);
    await tester.pumpAndSettle();
    expect(find.text('你的原话：“28岁”'), findsOneWidget);
    expect(
      tester.widget<TextField>(find.byType(TextField)).controller!.text,
      '',
    );
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'failed chat preserves input and retries with the same request id',
    (tester) async {
      final ids = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CoachChat(
              onProfileChanged: () async {},
              request: (path, method, body) async {
                if (path == '/coach/status') return {'configured': true};
                if (method == 'GET') return {'turns': <dynamic>[]};
                final input = body as Map;
                ids.add(input['request_id']);
                if (ids.length == 1) throw Exception('连接失败，请重试');
                return {
                  'request_id': input['request_id'],
                  'user_message': input['message'],
                  'reply': '你好，想聊训练还是饮食？',
                  'profile_changes': <dynamic>[],
                };
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '你好');
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('发送消息'));
      await tester.pumpAndSettle();
      expect(
        tester.widget<TextField>(find.byType(TextField)).controller!.text,
        '你好',
      );
      expect(find.textContaining('连接失败'), findsOneWidget);
      await tester.tap(find.text('重试'));
      await tester.pumpAndSettle();
      expect(ids.length, 2);
      expect(ids.first, ids.last);
      expect(find.text('你好'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('home is chat and drawer opens each fitness page', (
    tester,
  ) async {
    SharedPreferences.setMockInitialValues({});
    tester.platformDispatcher.accessibilityFeaturesTestValue =
        const FakeAccessibilityFeatures(disableAnimations: true);
    addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    final sent = <Map<String, dynamic>>[];
    var healthAi = true, historyReads = 0;
    await http.runWithClient(
      () async {
        FlutterSecureStorage.setMockInitialValues({});
        authSession = AuthSession();
        await authSession.accept({
          'access_token': 'test-access',
          'refresh_token': 'test-refresh',
          'expires_in': 900,
          'user': {'id': 'test-user', 'display_name': '测试用户'},
        });
        await tester.pumpWidget(const LiftLab());
        await tester.pumpAndSettle();
        expect(find.byType(CoachChat), findsOneWidget);
        expect(find.byType(NavigationBar), findsNothing);
        expect(find.text('我的用户画像'), findsNothing);
        for (final item in ['饮食', '训练计划', 'AI 陪训', '我', '私教提醒', 'AI 私教']) {
          await tester.tap(find.byTooltip('Open navigation menu'));
          await tester.pumpAndSettle();
          await tester.tap(find.widgetWithText(ListTile, item));
          await tester.pumpAndSettle();
          expect(find.widgetWithText(AppBar, item), findsOneWidget);
          expect(
            find.byTooltip('食物库'),
            item == '饮食' ? findsOneWidget : findsNothing,
          );
          expect(
            find.byTooltip('动作库'),
            item == '训练计划' || item == 'AI 陪训' ? findsOneWidget : findsNothing,
          );
          expect(tester.takeException(), isNull);
        }
        await tester.tap(find.byTooltip('切换桌宠教练'));
        await tester.pumpAndSettle();
        final choose = find.text('选择小燃');
        await tester.ensureVisible(choose);
        await tester.pumpAndSettle();
        await tester.tap(choose);
        await tester.pumpAndSettle();
        expect(find.text('小燃 · AI 私教'), findsWidgets);
        await tester.enterText(find.byType(TextField), '你好');
        await tester.pumpAndSettle();
        await tester.tap(find.byTooltip('发送消息'));
        await tester.pumpAndSettle();
        expect(sent.single['coach_id'], 'energetic');
        expect(sent.single['coach_name'], '小燃');
        expect(find.text('先从一个小目标开始。'), findsOneWidget);
        final beforePrivacyChange = historyReads;
        await tester.tap(find.byTooltip('Open navigation menu'));
        await tester.pumpAndSettle();
        final healthEntry = find.widgetWithText(ListTile, '健康与恢复');
        await tester.ensureVisible(healthEntry);
        await tester.pumpAndSettle();
        await tester.tap(healthEntry);
        await tester.pumpAndSettle();
        await tester.tap(find.widgetWithText(ListTile, '授权与隐私'));
        await tester.pumpAndSettle();
        final healthSwitch = find.widgetWithText(SwitchListTile, '允许私教读取健康摘要');
        await tester.ensureVisible(healthSwitch);
        await tester.tap(healthSwitch);
        await tester.pumpAndSettle();
        expect(healthAi, isFalse);
        expect(historyReads, greaterThan(beforePrivacyChange));
        await tester.pageBack();
        await tester.pumpAndSettle();
        expect(find.text('先从一个小目标开始。'), findsNothing);
        await tester.pumpWidget(
          const SizedBox(),
        ); // Dispose periodic nutrition timer.
      },
      () => MockClient((request) async {
        dynamic body;
        switch (request.url.path) {
          case '/api/coach/reminders':
            body = {};
          case '/api/catalog':
            body = {
              'foods': [
                {'id': 'rice', 'name': '米饭'},
              ],
              'exercises': [
                {
                  'id': 'bench',
                  'name': '卧推',
                  'type': 'weighted',
                  'realtime_supported': true,
                  'view': '侧面拍摄',
                  'weight_basis': '含杠铃',
                },
              ],
            };
          case '/api/coach/profile':
            body = {
              'facts': {},
              'complete': false,
              'missing_fields': ['age'],
              'labels': {'age': '年龄'},
            };
          case '/api/health-data/settings':
            if (request.method == 'PUT') {
              healthAi = jsonDecode(request.body)['ai_context_enabled'] == true;
            }
            body = {'storage_enabled': true, 'ai_context_enabled': healthAi};
          case '/api/health-data/summary':
            body = {};
          case '/api/health-data/measurements':
            body = {'items': []};
          case '/api/agent/runs':
          case '/api/coach/messages':
            if (request.method == 'POST') {
              final input = Map<String, dynamic>.from(jsonDecode(request.body));
              sent.add(input);
              body = {
                'request_id': input['request_id'],
                'user_message': input['message'],
                'reply': '先从一个小目标开始。',
                'profile_changes': [],
                'coach_id': input['coach_id'],
                'coach_name': input['coach_name'],
              };
            } else {
              historyReads++;
              body = {'turns': []};
            }
          case '/api/coach/status':
            body = {'configured': false};
          case '/api/nutrition/today':
            body = {
              'records': [],
              'comparison': {},
              'groups': [],
              'target_status': 'missing',
            };
          default:
            body = [];
        }
        return http.Response(
          jsonEncode(body),
          200,
          headers: {'content-type': 'application/json'},
        );
      }),
    );
    debugDefaultTargetPlatformOverride = null;
  });
}
