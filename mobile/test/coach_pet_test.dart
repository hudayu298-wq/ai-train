import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/coaches/coach_pet.dart';
import 'package:liftlab/coaches/coach_picker.dart';
import 'package:liftlab/reminders/reminder_settings.dart';

void main() {
  testWidgets(
    'four coach choices expose separate prompts and select identity',
    (tester) async {
      String? selected, prompt;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CoachPicker(
              selectedId: 'steady',
              onSelect: (p) async {
                selected = p.id;
              },
              onPrompt: (id) => prompt = id,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('阿衡'), findsOneWidget);
      expect(find.text('小燃'), findsOneWidget);
      expect(find.text('阿策'), findsOneWidget);
      expect(find.text('棉棉'), findsOneWidget);
      await tester.tap(find.text('选择小燃'));
      await tester.pumpAndSettle();
      expect(selected, 'energetic');
      await tester.tap(find.text('查看性格提示词').first);
      await tester.pumpAndSettle();
      expect(prompt, 'steady');
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets('pet drags within viewport, collapses and opens coach chooser', (
    tester,
  ) async {
    int choices = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: Scaffold(
            body: SizedBox(
              width: 360,
              height: 420,
              child: CoachPetOverlay(
                coachId: 'steady',
                name: '阿衡',
                onChoose: () {
                  choices++;
                },
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    final pet = find.byKey(const ValueKey('draggable-coach-pet'));
    final before = tester.getTopLeft(pet);
    await tester.drag(pet, const Offset(-130, -70));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(pet).dx, lessThan(before.dx));
    await tester.drag(pet, const Offset(-1000, -1000));
    await tester.pumpAndSettle();
    expect(tester.getTopLeft(pet).dx, greaterThanOrEqualTo(0));
    expect(tester.getTopLeft(pet).dy, greaterThanOrEqualTo(0));
    await tester.tap(find.text('换教练 · 阿衡'));
    expect(choices, 1);
    await tester.tap(find.byTooltip('收起教练桌宠'));
    await tester.pumpAndSettle();
    expect(tester.getSize(pet).height, 50);
    await tester.tap(pet);
    await tester.pump();
    expect(tester.getSize(pet).height, 250);
    await tester.pumpWidget(const SizedBox());
    expect(tester.takeException(), isNull);
  });

  test(
    'reminders follow personality and settings preserve selected identity',
    () {
      final texts = <String>{};
      for (final id in ['steady', 'energetic', 'analytical', 'gentle']) {
        final settings = ReminderSettings(
          coachId: id,
          mealsEnabled: true,
          mealTimes: {'lunch': '12:00'},
        );
        texts.add(buildReminders(settings).single.body);
        expect(ReminderSettings.fromJson(settings.toJson()).coachId, id);
      }
      expect(texts.length, 4);
      expect(ReminderSettings.fromJson({'coach_name': '林教练'}).coachName, '阿衡');
    },
  );
}
