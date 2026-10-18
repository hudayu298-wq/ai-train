import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftlab/app.dart';
import 'package:liftlab/coach_chat.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
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
    debugDefaultTargetPlatformOverride = TargetPlatform.linux;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    await http.runWithClient(
      () async {
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
          expect(tester.takeException(), isNull);
        }
        await tester.pumpWidget(
          const SizedBox(),
        ); // Dispose periodic nutrition timer.
      },
      () => MockClient((request) async {
        dynamic body;
        switch (request.url.path) {
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
          case '/api/coach/messages':
            body = {'turns': []};
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
