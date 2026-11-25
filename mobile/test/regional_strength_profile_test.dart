import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures/module_navigation.dart';

import 'package:liftlab/profile_setup.dart';
import 'package:liftlab/regional_strength_profile.dart';
import 'package:liftlab/ui_theme.dart';

import 'fixtures/strength_profile.dart';
import 'profile_setup_test.dart' show validFacts;

void main() {
  testWidgets(
    'incomplete regional data blocks profile completion and never submits guesses',
    (tester) async {
      final key = GlobalKey<RegionalStrengthProfileState>();
      final calls = <String>[];
      var finished = false;
      Future<dynamic> request(String p, String m, Object? b) async {
        calls.add('$m $p');
        if (p == '/strength-profile') return strengthFixture(ready: false);
        throw Exception('Unexpected write');
      }

      await tester.pumpWidget(
        MaterialApp(
          theme: buildAppTheme(),
          home: Scaffold(
            body: SingleChildScrollView(
              child: ProfileSetup(
                facts: validFacts,
                request: request,
                strength: RegionalStrengthProfile(key: key, request: request),
                beforeSave: () => key.currentState!.saveRequired(),
                onSaved: () async {
                  finished = true;
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.text('保存画像'));
      await tester.tap(find.text('保存画像'));
      await tester.pumpAndSettle();
      expect(finished, false);
      expect(
        calls.where((c) => c.startsWith('PUT') || c.startsWith('PATCH')),
        isEmpty,
      );
      expect(find.textContaining('力量画像尚未补齐'), findsWidgets);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'all three observed anchors save before profile; changing an action clears its old load',
    (tester) async {
      final key = GlobalKey<RegionalStrengthProfileState>();
      final writes = <Map>[];
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: RegionalStrengthProfile(
                key: key,
                request: (p, m, b) async {
                  if (m == 'PUT') writes.add(b as Map);
                  return strengthFixture();
                },
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await key.currentState!.saveRequired();
      expect(
        writes,
        isEmpty,
      ); // Unchanged data does not invalidate existing drafts.
      await openSection(tester, '胸部表现');
      final menu = find.byWidgetPredicate(
        (w) =>
            w is DropdownButtonFormField<String> &&
            w.decoration.labelText == '胸部 · 评估动作',
      );
      await tester.ensureVisible(menu);
      await tester.tap(menu);
      await tester.pumpAndSettle();
      await tester.tap(find.text('平板哑铃卧推').last);
      await tester.pumpAndSettle();
      final weight = find.byWidgetPredicate(
        (w) => w is TextField && w.decoration?.labelText == '胸部 · 实际重量 / kg',
      );
      expect(tester.widget<TextField>(weight).controller!.text, isEmpty);
      await expectLater(key.currentState!.saveRequired(), throwsException);
      expect(writes, isEmpty);
      expect(tester.takeException(), isNull);
    },
  );

  for (final conflict in [false, true]) {
    testWidgets(
      'changed strength save preserves all regions; conflict=$conflict',
      (tester) async {
        final key = GlobalKey<RegionalStrengthProfileState>();
        Map? body;
        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SingleChildScrollView(
                child: RegionalStrengthProfile(
                  key: key,
                  request: (p, m, b) async {
                    expect(p, '/strength-profile');
                    if (m == 'PUT') {
                      body = b as Map;
                      if (conflict) throw Exception('力量画像已在其他窗口更新，请刷新后核对');
                    }
                    return strengthFixture();
                  },
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        await openSection(tester, '胸部表现');
        final weight = find.byWidgetPredicate(
          (w) => w is TextField && w.decoration?.labelText == '胸部 · 实际重量 / kg',
        );
        await tester.ensureVisible(weight);
        await tester.enterText(weight, '55');
        if (conflict) {
          await expectLater(key.currentState!.saveRequired(), throwsException);
        } else {
          await key.currentState!.saveRequired();
        }
        await tester.pumpAndSettle();
        expect(body!['base_revision'], 'synthetic-strength-revision');
        expect((body!['items'] as List).map((e) => e['weight_kg']), [
          55,
          40,
          80,
        ]);
        expect(tester.widget<TextField>(weight).controller!.text, '55');
        if (conflict) expect(find.textContaining('其他窗口更新'), findsOneWidget);
        expect(tester.takeException(), isNull);
      },
    );
  }

  for (final width in [390.0, 768.0]) {
    testWidgets(
      'regional assessment remains usable at $width with enlarged text',
      (tester) async {
        await tester.binding.setSurfaceSize(Size(width, 844));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        await tester.pumpWidget(
          MaterialApp(
            theme: buildAppTheme(),
            builder: (c, w) => MediaQuery(
              data: MediaQuery.of(c)
                  .copyWith(textScaler: const TextScaler.linear(1.3)),
              child: w!,
            ),
            home: Scaffold(
              body: SingleChildScrollView(
                child: RegionalStrengthProfile(
                  request: (p, m, b) async => strengthFixture(),
                ),
              ),
            ),
          ),
        );
        await tester.pumpAndSettle();
        for (final label in ['胸部力量参考', '背部力量参考', '腿部力量参考']) {
          await openSection(tester, '${label.substring(0, 2)}表现');
          await tester.ensureVisible(find.text(label));
          await tester.pumpAndSettle();
          expect(tester.takeException(), isNull);
          await sectionOverview(tester, label: '选择评估部位');
        }
      },
    );
  }
}
