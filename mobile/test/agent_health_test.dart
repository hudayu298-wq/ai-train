import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures/module_navigation.dart';

import 'package:liftlab/coach_chat.dart';
import 'package:liftlab/health_data_page.dart';
import 'package:liftlab/research_page.dart';

void main() {
  testWidgets('agent actions require confirmation and show persisted status', (
    tester,
  ) async {
    bool committed = false;
    int writes = 0;
    Map<String, dynamic> turn() => {
      'run_id': 'agent-test',
      'request_id': 'test-request',
      'user_message': '记录米饭150克',
      'reply': '请确认这餐。',
      'profile_changes': [],
      'actions': [
        {
          'id': 'action-test',
          'kind': 'meal',
          'status': committed ? 'committed' : 'pending',
          'preview': {
            'title': '核对这餐饮食',
            'lines': ['米饭 · 150 g · 熟'],
          },
        },
      ],
    };
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: CoachChat(
            onProfileChanged: () async {},
            request: (path, method, body) async {
              if (path == '/coach/status') {
                return {'configured': true};
              }
              if (method == 'GET') {
                return {
                  'turns': [turn()],
                };
              }
              expect(path, '/agent/actions/action-test/decision');
              expect((body as Map)['approved'], true);
              committed = true;
              writes++;
              return {'status': 'committed'};
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(writes, 0);
    await tester.ensureVisible(find.text('确认保存'));
    await tester.tap(find.text('确认保存'));
    await tester.pumpAndSettle();
    expect(writes, 1);
    expect(find.text('已保存'), findsOneWidget);
    expect(find.text('确认保存'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'health storage and AI permissions are separate and can be revoked',
    (tester) async {
      Map<String, dynamic> settings = {
        'storage_enabled': false,
        'ai_context_enabled': false,
      };
      await tester.pumpWidget(
        MaterialApp(
          home: HealthDataPage(
            request: (path, method, body) async {
              if (path.endsWith('/settings')) {
                if (method == 'PUT') {
                  settings = Map<String, dynamic>.from(body as Map);
                }
                return settings;
              }
              if (path.endsWith('/summary')) {
                return {'metrics': {}, 'recent_checkins': []};
              }
              return {'items': []};
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('保存测量'), findsNothing);
      await openSection(tester, '授权与隐私');
      await tester.tap(find.text('保存测量与恢复反馈'));
      await tester.pumpAndSettle();
      expect(settings['storage_enabled'], true);
      expect(settings['ai_context_enabled'], false);
      await tester.tap(find.text('允许私教读取健康摘要'));
      await tester.pumpAndSettle();
      expect(settings['ai_context_enabled'], true);
      await tester.tap(find.text('保存测量与恢复反馈'));
      await tester.pumpAndSettle();
      expect(settings, {'storage_enabled': false, 'ai_context_enabled': false});
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('ordinary account sees only published research knowledge', (
    tester,
  ) async {
    final paths = <String>[];
    await tester.pumpWidget(
      MaterialApp(
        home: ResearchPage(
          request: (path, method, body) async {
            paths.add(path);
            return {'release_id': 'baseline', 'items': []};
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(paths, ['/research/knowledge']);
    expect(find.textContaining('尚无已发布证据'), findsOneWidget);
    expect(find.text('获取研究 · 管理员'), findsNothing);
    expect(tester.takeException(), isNull);
  });
}
