import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures/module_navigation.dart';

import 'package:liftlab/nutrition_guidance_page.dart';
import 'package:liftlab/ui_theme.dart';

void main() {
  Future<void> largeView(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1100, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Map<String, dynamic> settings() => {
    'activity_factor': 1.4,
    'protein_g_per_kg': 1.6,
    'fat_g_per_kg': 0.8,
    'energy_adjustment_kcal': null,
    'eligibility': 'eligible',
    'calibration_enabled': true,
  };

  Map<String, dynamic> basis({bool applied = false}) => {
    'target': {
      'kcal': applied ? 2622 : 2522,
      'protein': 112,
      'fat': 56,
      'carbs': 392,
    },
    'target_source': applied ? 'confirmed_calibration' : 'formula_estimate',
    'version': 'nutrition-2026.10.22-v1',
    'warnings': [],
    'note': '这是估算起点；设备消耗不直接叠加。',
    'steps': [
      {'label': '静息能量估算', 'value': 1658.8, 'unit': 'kcal/日'},
    ],
    'rules': [
      {
        'label': '活动系数',
        'product_default': true,
        'value': 1.4,
        'unit': '无量纲',
        'population': '健康运动成人',
        'limitations': '产品起点',
        'source_ids': [],
      },
    ],
    'sources': [],
  };

  testWidgets('explains effective target and saves numeric settings', (
    tester,
  ) async {
    await largeView(tester);
    var config = settings();
    var writes = 0;
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: NutritionGuidancePage(
          request: (path, method, body) async {
            if (path.endsWith('/settings')) {
              if (method == 'PUT') {
                writes++;
                config = Map<String, dynamic>.from(body as Map);
              }
              return config;
            }
            if (path.endsWith('/target')) return basis();
            if (path.endsWith('/suggestions')) return {'items': []};
            return {
              'eligible': false,
              'reasons': ['需要连续14个完整饮食日'],
            };
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      find.text('2522 kcal/日\n蛋白质 112 g · 脂肪 56 g · 碳水 392 g'),
      findsOneWidget,
    );
    expect(find.text('来源：公式估算与个人设置'), findsOneWidget);
    await openSection(tester, '趋势反馈');
    expect(find.text('需要连续14个完整饮食日'), findsOneWidget);
    await sectionOverview(tester);
    await openSection(tester, '个人设置');
    expect(writes, 0);
    await tester.enterText(
      find.widgetWithText(TextField, '蛋白质（1.4–2.0 g/kg/日）'),
      '1.8',
    );
    await tester.ensureVisible(find.text('保存目标设置'));
    await tester.tap(find.text('保存目标设置'));
    await tester.pumpAndSettle();
    expect(writes, 1);
    expect(config['protein_g_per_kg'], 1.8);
    expect(config['energy_adjustment_kcal'], isNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('proposal changes current target only after confirmation', (
    tester,
  ) async {
    await largeView(tester);
    final suggestions = <Map<String, dynamic>>[];
    var applied = false;
    var creates = 0, confirmations = 0;
    final assessment = {
      'eligible': true,
      'data_signature': 'snapshot-1',
      'reasons': ['已具备完整趋势依据'],
      'proposed_target': {
        'kcal': 2622,
        'protein': 112,
        'fat': 56,
        'carbs': 418,
      },
    };
    await tester.pumpWidget(
      MaterialApp(
        theme: buildAppTheme(),
        home: NutritionGuidancePage(
          request: (path, method, body) async {
            if (path.endsWith('/settings')) return settings();
            if (path.endsWith('/target')) return basis(applied: applied);
            if (path.endsWith('/calibration')) {
              return applied
                  ? {
                      'eligible': false,
                      'reasons': ['上次调整后需至少积累14个完整日再评估'],
                    }
                  : assessment;
            }
            if (path.endsWith('/confirm')) {
              confirmations++;
              expect((body as Map)['request_id'], isNotEmpty);
              applied = true;
              suggestions[0]['status'] = 'applied';
              return suggestions[0];
            }
            if (method == 'POST') {
              creates++;
              final draft = {
                'id': 'suggestion-1',
                'status': 'pending',
                'assessment': assessment,
                'expires_at': DateTime.now()
                    .add(const Duration(hours: 48))
                    .toUtc()
                    .toIso8601String(),
              };
              suggestions.add(draft);
              return draft;
            }
            return {'items': suggestions};
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await openSection(tester, '趋势反馈');
    await tester.ensureVisible(find.text('生成待确认建议'));
    await tester.tap(find.text('生成待确认建议'));
    await tester.pumpAndSettle();
    expect(creates, 1);
    expect(confirmations, 0);
    expect(applied, false);
    await tester.ensureVisible(find.text('确认应用建议'));
    await tester.tap(find.text('确认应用建议'));
    await tester.pumpAndSettle();
    expect(confirmations, 1);
    expect(find.text('来源：已确认的趋势调整'), findsOneWidget);
    expect(find.text('确认应用建议'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('expired proposal cannot be confirmed', (tester) async {
    await largeView(tester);
    var writes = 0;
    final assessment = {
      'eligible': true,
      'data_signature': 'snapshot-1',
      'reasons': [],
      'proposed_target': {
        'kcal': 2622,
        'protein': 112,
        'fat': 56,
        'carbs': 418,
      },
    };
    await tester.pumpWidget(
      MaterialApp(
        home: NutritionGuidancePage(
          request: (path, method, body) async {
            if (method != 'GET') writes++;
            if (path.endsWith('/settings')) return settings();
            if (path.endsWith('/target')) return basis();
            if (path.endsWith('/calibration')) return assessment;
            return {
              'items': [
                {
                  'id': 'expired-1',
                  'status': 'pending',
                  'assessment': assessment,
                  'expires_at': DateTime.now()
                      .subtract(const Duration(hours: 1))
                      .toUtc()
                      .toIso8601String(),
                },
              ],
            };
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    await openSection(tester, '趋势反馈');
    await tester.ensureVisible(find.text('确认应用建议'));
    final button = tester.widget<FilledButton>(
      find.widgetWithText(FilledButton, '确认应用建议'),
    );
    expect(button.onPressed, isNull);
    expect(find.text('建议已过期或依据变化，请重新生成。'), findsOneWidget);
    expect(writes, 0);
    expect(tester.takeException(), isNull);
  });
}
