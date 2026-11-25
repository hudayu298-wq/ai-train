import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/training_tools_page.dart';

Finder input(String label) => find.byWidgetPredicate(
  (w) => w is TextField && w.decoration?.labelText == label,
);

void main() {
  testWidgets(
    'tools expose trends, constrained rules, translation submission and food confirmation',
    (tester) async {
      tester.view.physicalSize = const Size(900, 2000);
      tester.view.devicePixelRatio = 1;
      addTearDown(() {
        tester.view.resetPhysicalSize();
        tester.view.resetDevicePixelRatio();
      });
      final calls = <String>[];
      Map? saved;
      await tester.pumpWidget(
        MaterialApp(
          home: TrainingToolsPage(
            request: (p, m, b) async {
              calls.add('$m $p');
              if (p.startsWith('/training-trends')) {
                return {
                  'from': '2026-10-01',
                  'through': '2026-10-24',
                  'note': '同一组可归属多个肌群',
                  'weeks': [
                    {'key': '2026-10-19', 'working_sets': 3},
                  ],
                  'cycles': [],
                  'muscles': [
                    {'name': '胸大肌', 'working_sets': 3},
                  ],
                };
              }
              if (p == '/training-settings') {
                if (m == 'PUT') {
                  saved = b as Map;
                  return b;
                }
                return {
                  'enabled': true,
                  'mode': 'either',
                  'min_sessions': 2,
                  'rpe_ceiling': 8.0,
                  'max_weight_increase_fraction': .05,
                  'max_rep_change': 1,
                };
              }
              if (p == '/catalog-content') {
                return {'items': []};
              }
              if (p.startsWith('/catalog?')) {
                return {
                  'exercises': [
                    {'id': 'bench', 'name': '卧推'},
                  ],
                };
              }
              if (p.endsWith('/confirm')) {
                return {'message': '已保存到本人食物库，尚未记录任何饮食'};
              }
              if (p.startsWith('/external-foods/')) {
                return {
                  'fetched_at': '2026-10-24',
                  'food': {
                    'name': '测试食品',
                    'barcode': '12345678',
                    'kcal': 200,
                    'protein': 10,
                    'fat': 4,
                    'carbs': 30,
                    'source_url':
                        'https://world.openfoodfacts.org/product/12345678',
                  },
                };
              }
              throw Exception(p);
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('每周记录趋势'), findsOneWidget);
      expect(find.textContaining('胸大肌'), findsOneWidget);
      await tester.tap(find.text('进阶设置'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('保存进阶设置'));
      await tester.pumpAndSettle();
      expect(saved?['min_sessions'], 2);
      expect(saved?['max_weight_increase_fraction'], .05);
      await tester.tap(find.text('译文审核'));
      await tester.pumpAndSettle();
      await tester.enterText(input('动作译名'), '杠铃平板卧推');
      await tester.enterText(input('来源及翻译说明（至少5字）'), '核对原条目中文说明');
      await tester.tap(find.text('同意将本次译文作为公开资料提交审核'));
      await tester.pump();
      await tester.tap(find.text('提交公开译文'));
      await tester.pumpAndSettle();
      expect(calls, contains('POST /catalog-content'));
      expect(
        find.text('审核通过并发布译文'),
        findsNothing,
      ); // Normal user cannot review.
      await tester.tap(find.text('外部食品'));
      await tester.pumpAndSettle();
      await tester.enterText(input('商品条码（8–14位数字）'), '12345678');
      await tester.tap(find.text('按条码查询'));
      await tester.pumpAndSettle();
      expect(calls, isNot(contains('POST /external-foods/12345678/confirm')));
      await tester.tap(find.text('核对包装后保存到本人食物库'));
      await tester.pumpAndSettle();
      expect(calls, contains('POST /external-foods/12345678/confirm'));
      expect(calls.any((p) => p.contains('/meals')), false);
    },
  );
}
