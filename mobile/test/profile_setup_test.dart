import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/profile_setup.dart';

const validFacts = <String, dynamic>{
  'age': 28,
  'height_cm': 175,
  'weight_kg': 70,
  'sex': 'male',
  'goal': 'muscle_gain',
  'experience': 'beginner',
  'training_weekdays': [1, 3, 5],
  'preferred_time': '19:00',
  'session_minutes': 45,
  'equipment': '杠铃、哑铃',
};

Future<void> mount(
  WidgetTester tester,
  Map<String, dynamic> facts,
  FitnessRequest request,
  Future<void> Function() saved,
) async {
  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ProfileSetup(facts: facts, request: request, onSaved: saved),
        ),
      ),
    ),
  );
}

Future<void> save(WidgetTester tester) async {
  await tester.ensureVisible(find.text('保存画像'));
  await tester.pumpAndSettle();
  await tester.tap(find.text('保存画像'));
  await tester.pumpAndSettle();
}

void main() {
  testWidgets(
    'missing fields show actionable save summary without sending a request',
    (tester) async {
      var called = false;
      await mount(tester, {}, (path, method, body) async {
        called = true;
        return {};
      }, () async {});
      await save(tester);
      expect(called, false);
      final message = tester.widget<Text>(find.textContaining('画像尚未保存：')).data!;
      expect(message, contains('请填写年龄'));
      expect(message, contains('请选择训练目标'));
      expect(message, contains('请至少选择一个每周训练日'));
    },
  );

  testWidgets('valid profile normalizes time and saves all facts', (
    tester,
  ) async {
    Map<String, dynamic>? submitted;
    var saved = false;
    await mount(
      tester,
      {...validFacts, 'preferred_time': '9：00'},
      (path, method, body) async {
        expect(path, '/coach/profile');
        expect(method, 'PATCH');
        submitted = Map<String, dynamic>.from(body as Map);
        return {};
      },
      () async {
        saved = true;
      },
    );
    await save(tester);
    expect(submitted?['preferred_time'], '09:00');
    expect(submitted?['training_weekdays'], [1, 3, 5]);
    expect(submitted?['days'], 3);
    expect(submitted?['age'], 28);
    expect(saved, true);
    expect(find.text('画像已保存'), findsOneWidget);
  });

  testWidgets('out of range and malformed values are reported next to save', (
    tester,
  ) async {
    var called = false;
    await mount(
      tester,
      {
        ...validFacts,
        'height_cm': 1.75,
        'session_minutes': 181,
        'preferred_time': '25:00',
      },
      (path, method, body) async {
        called = true;
        return {};
      },
      () async {},
    );
    await save(tester);
    expect(called, false);
    final message = tester.widget<Text>(find.textContaining('画像尚未保存：')).data!;
    expect(message, contains('身高 / cm需在120–230之间'));
    expect(message, contains('15–180之间'));
    expect(message, contains('00:00–23:59'));
    // Validation must not clear the user's pending input.
    final height = tester.widget<TextFormField>(
      find.widgetWithText(TextFormField, '身高 / cm', skipOffstage: false),
    );
    expect(height.controller!.text, '1.75');
  });
}
