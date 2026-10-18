import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:liftlab/auth/login_page.dart';
import 'package:liftlab/auth/auth_gate.dart';
import 'package:liftlab/auth/session.dart';
import 'package:shared_preferences/shared_preferences.dart';

Map<String, dynamic> token({String access = 'access', int expires = 900}) => {
  'access_token': access,
  'refresh_token': 'refresh-$access',
  'expires_in': expires,
  'user': {'id': 'one-user', 'email': 'me@example.test'},
};

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  testWidgets('startup plugin failure shows retry and can recover to login', (
    tester,
  ) async {
    AndroidFlutterLocalNotificationsPlugin.registerWith();
    SharedPreferences.setMockInitialValues({});
    const channel = MethodChannel('dexterous.com/flutter/local_notifications');
    var failing = true;
    var cancellations = 0;
    final methods = <String>[];
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(channel, (
      call,
    ) async {
      methods.add(call.method);
      if (call.method == 'initialize' && failing) {
        throw PlatformException(code: 'invalid_icon');
      }
      if (call.method == 'cancel') cancellations++;
      return call.method == 'initialize' ? true : null;
    });
    addTearDown(() {
      tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        channel,
        null,
      );
    });
    await http.runWithClient(
      () async {
        authSession = AuthSession();
        await tester.pumpWidget(const MaterialApp(home: AuthGate()));
        await tester.pumpAndSettle();
        expect(find.text('启动准备失败，请重试'), findsOneWidget);
        expect(methods, contains('initialize'));
        expect(find.byType(CircularProgressIndicator), findsNothing);
        expect(tester.takeException(), isNull);
        failing = false;
        await tester.tap(find.text('重试'));
        await tester.pumpAndSettle();
        expect(find.text('欢迎回来'), findsOneWidget);
        expect(cancellations, greaterThan(0));
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox());
      },
      () => MockClient(
        (_) async => http.Response(
          jsonEncode({'policy_version': '2026-10-18', 'wechat_enabled': false}),
          200,
        ),
      ),
    );
  });

  test(
    'concurrent requests share one refresh and all carry bearer credentials',
    () async {
      var rotations = 0;
      final session = AuthSession(
        client: MockClient((request) async {
          if (request.url.path.endsWith('/refresh')) {
            rotations++;
            await Future<void>.delayed(const Duration(milliseconds: 20));
            return http.Response(jsonEncode(token(access: 'rotated')), 200);
          }
          expect(request.headers['Authorization'], 'Bearer rotated');
          return http.Response('{}', 200);
        }),
      );
      await session.accept(token(expires: 1));
      await Future.wait(List.generate(5, (_) => session.request('/me')));
      expect(rotations, 1);
      final multipart = http.MultipartRequest(
        'POST',
        Uri.parse('$apiBase/api/media'),
      );
      await session.send(multipart);
      expect(multipart.headers['Authorization'], 'Bearer rotated');
    },
  );

  test(
    'revoked session clears local identity and does not replay mutations',
    () async {
      var calls = 0;
      final session = AuthSession(
        client: MockClient((request) async {
          calls++;
          return http.Response('{"detail":"revoked"}', 401);
        }),
      );
      await session.accept(token());
      await expectLater(
        session.request(
          '/coach/messages',
          method: 'POST',
          body: {'message': 'test'},
        ),
        throwsException,
      );
      expect(session.user, isNull);
      expect(calls, 1);
    },
  );

  testWidgets('login requires policy consent and accepts a server session', (
    tester,
  ) async {
    var calls = 0;
    await http.runWithClient(
      () async {
        authSession = AuthSession();
        await tester.pumpWidget(const MaterialApp(home: LoginPage()));
        await tester.pumpAndSettle();
        expect(find.text('微信登录'), findsNothing);
        await tester.enterText(find.byType(TextField).at(0), 'me@example.test');
        await tester.enterText(
          find.byType(TextField).at(1),
          'long password for login',
        );
        await tester.tap(find.widgetWithText(FilledButton, '登录'));
        await tester.pumpAndSettle();
        expect(find.textContaining('请先阅读并同意'), findsOneWidget);
        expect(calls, 0);
        await tester.tap(find.byType(Checkbox));
        await tester.ensureVisible(find.widgetWithText(FilledButton, '登录'));
        await tester.tap(find.widgetWithText(FilledButton, '登录'));
        await tester.pumpAndSettle();
        expect(calls, 1);
        expect(authSession.user?['id'], 'one-user');
        await tester.pumpWidget(const SizedBox());
      },
      () => MockClient((request) async {
        if (request.url.path.endsWith('/config')) {
          return http.Response(
            jsonEncode({
              'policy_version': '2026-10-18',
              'registration_open': true,
              'wechat_enabled': false,
            }),
            200,
          );
        }
        calls++;
        expect(request.url.path, '/api/auth/login');
        return http.Response(jsonEncode(token()), 200);
      }),
    );
  });
}
