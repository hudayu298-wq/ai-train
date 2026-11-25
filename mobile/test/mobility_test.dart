import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/mobility_page.dart';

const protocol = {
  'id': 'wblt-knee-wall-cm',
  'version': '1',
  'steps': ['每侧练习3次，再正式测3次。'],
};

Future<void> show(
  WidgetTester tester,
  Future<dynamic> Function(String, String, dynamic) request,
) async {
  tester.view.physicalSize = const Size(1000, 1600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(home: MobilityPage(request: request)));
  await tester.pumpAndSettle();
}

Future<void> reveal(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(
    finder,
    300,
    scrollable: find.byType(Scrollable).first,
  );
  await tester.pumpAndSettle();
}

Finder field(String label) => find.byWidgetPredicate(
  (v) => v is TextField && v.decoration?.labelText == label,
);

void main() {
  testWidgets(
    'AI summary consent is independent and revoked when storage is disabled',
    (tester) async {
      var settings = {'storage_enabled': true, 'ai_context_enabled': false};
      final writes = <Map>[];
      await show(tester, (path, method, body) async {
        if (path.endsWith('/protocol')) return protocol;
        if (path.endsWith('/settings')) {
          if (method == 'PUT') {
            writes.add(Map.from(body as Map));
            settings = Map<String, bool>.from(body);
          }
          return settings;
        }
        if (path.endsWith('/summary')) return {'sides': {}};
        return {'items': []};
      });
      final consent = find.widgetWithText(SwitchListTile, '允许AI使用活动度摘要');
      expect(tester.widget<SwitchListTile>(consent).value, false);
      await reveal(tester, consent);
      await tester.tap(consent);
      await tester.pumpAndSettle();
      expect(writes.last, {
        'storage_enabled': true,
        'ai_context_enabled': true,
      });
      final storage = find.widgetWithText(SwitchListTile, '保存我的活动度记录');
      await reveal(tester, storage);
      await tester.tap(storage);
      await tester.pumpAndSettle();
      expect(writes.last, {
        'storage_enabled': false,
        'ai_context_enabled': false,
      });
      expect(tester.widget<SwitchListTile>(consent).onChanged, isNull);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'manual cm measurements preserve protocol, side and three trials',
    (tester) async {
      Map? posted;
      await show(tester, (path, method, body) async {
        if (path.endsWith('/protocol')) return protocol;
        if (path.endsWith('/settings')) return {'storage_enabled': true};
        if (path.endsWith('/summary')) return {'sides': {}};
        if (method == 'POST') {
          posted = body as Map;
          return {'id': 'saved'};
        }
        return {'items': []};
      });
      expect(find.textContaining('摄像头测角尚未校准开放'), findsOneWidget);
      await reveal(tester, find.text('该侧已练习3次'));
      await tester.tap(find.text('该侧已练习3次'));
      for (var i = 0; i < 3; i++) {
        await reveal(tester, field('第${i + 1}次距离（cm）'));
        await tester.enterText(field('第${i + 1}次距离（cm）'), '${8 + i / 10}');
      }
      await reveal(tester, find.text('3次均脚跟贴地、膝轻触墙且沿第二趾方向'));
      await tester.tap(find.text('3次均脚跟贴地、膝轻触墙且沿第二趾方向'));
      await tester.tap(find.text('保存3次手动测量'));
      await tester.pumpAndSettle();
      expect(posted?['protocol_version'], '1');
      expect(posted?['side'], 'left');
      expect(posted?['source_method'], 'manual_tape');
      expect(posted?['unit'], 'cm');
      expect((posted?['trials'] as List).length, 3);
      expect(posted?['loading'], 'weight_bearing');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'pain changes flow to a stop record without requiring more trials',
    (tester) async {
      Map? posted;
      await show(tester, (path, method, body) async {
        if (path.endsWith('/protocol')) return protocol;
        if (path.endsWith('/settings')) return {'storage_enabled': true};
        if (path.endsWith('/summary')) return {'sides': {}};
        if (method == 'POST') {
          posted = body as Map;
          return {'id': 'stopped'};
        }
        return {'items': []};
      });
      await reveal(tester, find.text('0 · 无疼痛'));
      await tester.tap(find.text('0 · 无疼痛'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('3 · 停止测量').last);
      await tester.pumpAndSettle();
      await reveal(tester, field('疼痛位置'));
      await tester.enterText(field('疼痛位置'), '踝前');
      await tester.tap(find.text('保存停止记录'));
      await tester.pumpAndSettle();
      expect(posted?['stopped_due_to_pain'], true);
      expect(posted?['pain_score'], 3);
      expect(posted?['trials'], isEmpty);
      expect(posted?['pain_location'], '踝前');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('record deletion is explicit and updates history', (
    tester,
  ) async {
    var deletes = 0;
    var records = <Map>[
      {
        'id': 'manual-001',
        'side': 'left',
        'mean_cm': 8.1,
        'protocol_version': '1',
        'observed_at': '2026-01-01T08:00:00+08:00',
        'trials': [],
        'quality_notes': [],
        'comparable': true,
      },
    ];
    await show(tester, (path, method, body) async {
      if (path.endsWith('/protocol')) return protocol;
      if (path.endsWith('/settings')) return {'storage_enabled': false};
      if (path.endsWith('/summary')) return {'sides': {}};
      if (method == 'DELETE') {
        deletes++;
        records = [];
        return {'deleted': true};
      }
      return {'items': records};
    });
    await reveal(tester, find.text('删除记录'));
    await tester.tap(find.text('删除记录'));
    await tester.pumpAndSettle();
    expect(deletes, 0);
    await tester.tap(find.text('删除').last);
    await tester.pumpAndSettle();
    expect(deletes, 1);
    expect(find.text('暂无记录。'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
