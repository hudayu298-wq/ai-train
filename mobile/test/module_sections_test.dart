import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/ui_components.dart';
import 'package:liftlab/ui_theme.dart';
import 'package:liftlab/profile_setup.dart';

import 'fixtures/module_navigation.dart';
import 'profile_setup_test.dart' show validFacts;

void main() {
  testWidgets(
    'profile groups retain edits and save together only on explicit save',
    (tester) async {
      final writes = <Map>[];
      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: AppContent(
              child: ProfileSetup(
                facts: validFacts,
                request: (p, m, b) async {
                  writes.add(b as Map);
                  return {};
                },
                onSaved: () async {},
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TextFormField), findsNothing);
      await openSection(tester, '基础资料');
      await tester.enterText(
        find.widgetWithText(TextFormField, '年龄（18–90岁）'),
        '29',
      );
      await sectionOverview(tester);
      await openSection(tester, '训练安排');
      await tester.ensureVisible(find.text('周二'));
      await tester.tap(find.text('周二'));
      await tester.enterText(
        find.widgetWithText(TextFormField, '通常开始时间 / HH:MM'),
        '18:30',
      );
      await sectionOverview(tester);
      await openSection(tester, '饮食习惯');
      await tester.enterText(
        find.widgetWithText(TextFormField, '食物过敏与禁忌（可选）'),
        '花生',
      );
      await sectionOverview(tester);
      await openSection(tester, '基础资料');
      expect(
        tester
            .widget<TextFormField>(
              find.widgetWithText(TextFormField, '年龄（18–90岁）'),
            )
            .controller!
            .text,
        '29',
      );
      expect(writes, isEmpty);
      await tester.ensureVisible(find.text('保存画像'));
      await tester.tap(find.text('保存画像'));
      await tester.pumpAndSettle();
      expect(writes.single['age'], 29);
      expect(writes.single['preferred_time'], '18:30');
      expect(writes.single['training_weekdays'], [1, 2, 3, 5]);
      expect(writes.single['food_allergies'], '花生');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('switching and resizing preserves uncontrolled field state', (
    tester,
  ) async {
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.binding.setSurfaceSize(const Size(768, 900));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AppContent(
            child: ModuleSections(
              sections: [
                ModuleSection(
                  title: '第一组',
                  description: '输入',
                  child: TextFormField(
                    initialValue: 'initial',
                    decoration: const InputDecoration(labelText: '临时内容'),
                  ),
                ),
                const ModuleSection(
                  title: '第二组',
                  description: '说明',
                  child: Text('第二组内容'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    await openSection(tester, '第一组');
    await tester.enterText(find.byType(TextFormField), '未提交内容');
    await sectionOverview(tester);
    await openSection(tester, '第二组');
    expect(find.byType(TextFormField), findsNothing);
    await tester.binding.setSurfaceSize(const Size(390, 844));
    await tester.pumpAndSettle();
    await sectionOverview(tester);
    await openSection(tester, '第一组');
    expect(find.text('未提交内容'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'changed available groups preserve identity and removed selection returns to overview',
    (tester) async {
      late StateSetter update;
      var available = true;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: AppContent(
              child: StatefulBuilder(
                builder: (c, set) {
                  update = set;
                  return ModuleSections(
                    sections: [
                      const ModuleSection(
                        title: '授权',
                        description: '独立开关',
                        child: Text('管理授权'),
                      ),
                      if (available)
                        ModuleSection(
                          title: '测量',
                          description: '需保存授权',
                          child: TextFormField(initialValue: '70'),
                        ),
                      const ModuleSection(
                        title: '记录',
                        description: '查看',
                        child: Text('历史记录'),
                      ),
                    ],
                  );
                },
              ),
            ),
          ),
        ),
      );
      await openSection(tester, '测量');
      update(() => available = false);
      await tester.pumpAndSettle();
      expect(find.widgetWithText(ListTile, '授权'), findsOneWidget);
      expect(find.widgetWithText(ListTile, '记录'), findsOneWidget);
      expect(find.widgetWithText(ListTile, '测量'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );
}
