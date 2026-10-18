import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/library_page.dart';

void main() {
  testWidgets(
    'filters by joint movement and body region and shows shared details',
    (tester) async {
      final calls = <String>[];
      final entry = {
        'id': 'dumbbell_curl',
        'name': '哑铃弯举',
        'equipment': '哑铃',
        'type': 'weighted',
        'movement_pattern': '肘屈曲',
        'joint_actions': ['肘屈伸'],
        'body_regions': ['手臂'],
        'primary_muscles': ['肱二头肌'],
        'secondary_muscles': ['肱肌'],
        'weight_basis': '单只重量',
        'source_label': '教学草稿',
        'content_version': 'movement-1.0',
        'technique': {
          'setup': ['站稳'],
          'execution': ['控制屈肘'],
          'key_points': ['保持上臂相对稳定'],
          'cautions': ['不靠明显躯干摆动'],
          'common_errors': [],
          'not_observable': ['疼痛'],
          'sources': [],
        },
      };
      await tester.pumpWidget(
        MaterialApp(
          home: LibraryPage(
            initialKind: 'exercises',
            onChanged: () async {},
            request: (path, method, body) async {
              calls.add(path);
              final exercises = path.startsWith('/library/exercises');
              return {
                'items': exercises ? [entry] : <dynamic>[],
                'categories': exercises ? ['肘屈曲'] : ['乳制品'],
                'body_parts': exercises ? ['手臂'] : [],
                'total': exercises ? 1 : 0,
              };
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(calls.first, startsWith('/library/exercises'));
      await tester.tap(find.text('全部分类'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('肘屈曲').last);
      await tester.pumpAndSettle();
      expect(Uri.parse(calls.last).queryParameters['category'], '肘屈曲');
      await tester.tap(find.text('全部部位'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('手臂').last);
      await tester.pumpAndSettle();
      expect(Uri.parse(calls.last).queryParameters['body_part'], '手臂');
      await tester.ensureVisible(find.text('哑铃弯举'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('哑铃弯举'));
      await tester.pumpAndSettle();
      expect(find.text('关节动作模式：肘屈曲'), findsOneWidget);
      expect(find.text('• 保持上臂相对稳定'), findsOneWidget);
      expect(find.text('主要肌群'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
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
