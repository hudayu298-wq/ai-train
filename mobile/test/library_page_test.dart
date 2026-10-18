import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/library_page.dart';

void main() {
  testWidgets('searches library and adds a food using per-100g values', (
    tester,
  ) async {
    final paths = <String>[];
    Map<String, dynamic>? saved;
    await tester.pumpWidget(
      MaterialApp(
        home: LibraryPage(
          onChanged: () async {},
          request: (path, method, body) async {
            paths.add(path);
            if (method == 'POST') {
              saved = Map<String, dynamic>.from(body as Map);
              return {'id': 'custom_food', ...saved!};
            }
            return {
              'items': <dynamic>[],
              'categories': ['乳制品'],
              'total': 0,
            };
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).first, '酸奶');
    await tester.tap(find.byIcon(Icons.search));
    await tester.pumpAndSettle();
    expect(Uri.parse(paths.last).queryParameters['q'], '酸奶');
    await tester.tap(find.text('新增'));
    await tester.pumpAndSettle();
    Future<void> fill(String label, String value) async {
      final finder = find.byWidgetPredicate(
        (w) => w is TextField && w.decoration?.labelText == label,
      );
      await tester.ensureVisible(finder);
      await tester.enterText(finder, value);
    }

    await fill('食物名称', '我的酸奶');
    await fill('分类', '乳制品');
    await fill('热量 / kcal', '100');
    await fill('蛋白质 / g', '8');
    await fill('脂肪 / g', '4');
    await fill('碳水 / g', '8');
    await fill('来源（包装标签或资料名称）', '每100g包装标签');
    await tester.tap(find.text('保存'));
    await tester.pumpAndSettle();
    expect(saved?['kcal'], 100.0);
    expect(saved?['protein'], 8.0);
    expect(saved?['state'], 'prepared');
    expect(saved?['source_label'], '每100g包装标签');
    expect(tester.takeException(), isNull);
    await tester.tap(find.text('动作库'));
    await tester.pumpAndSettle();
    expect(paths.last, startsWith('/library/exercises?'));
    expect(tester.takeException(), isNull);
  });
}
