import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/knowledge_page.dart';

void main() {
  testWidgets(
    'bone landmarks expose phase guidance and source type without internal keys',
    (tester) async {
      final paths = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: KnowledgePage(
            request: (path, method, body) async {
              paths.add(path);
              if (path == '/knowledge') {
                return {
                  'name': '练伴基础知识',
                  'counts': {'bone_landmark': 1},
                };
              }
              if (path.startsWith('/knowledge/search')) {
                return {
                  'items': [
                    {
                      'id': 'guide_squat',
                      'kind': 'exercise_guide',
                      'title': '高杠深蹲阶段',
                      'summary': '按阶段解释负重动作',
                    },
                  ],
                };
              }
              return {
                'version': 'foundation-test',
                'items': [
                  {
                    'title': '高杠深蹲阶段',
                    'summary': '按阶段解释负重动作',
                    'evidence_status': 'product_default',
                    'facts': {
                      'phase_notes': ['下降时髋膝屈曲；起身时共同伸展'],
                      'landmark_ids': ['iliac_crest'],
                      'numeric_guidance': ['default_target_rir = 3'],
                      'rule_ids': ['default_target_rir'],
                      'governing_service': 'backend/periodization.py',
                    },
                    'population': ['一般成人'],
                    'limitations': ['不是伤病诊断'],
                  },
                ],
                'related_items': [
                  {'id': 'iliac_crest', 'title': '髂嵴'},
                ],
                'citations': [
                  {
                    'sources': [
                      {
                        'title': '训练执行产品策略',
                        'edition': '1',
                        'locator': '周期参数',
                        'accessed_on': '2026-10-22',
                        'evidence_type': 'product_policy',
                        'content_use': 'product_policy',
                        'publisher': '练伴',
                        'url': 'https://example.com/policy',
                        'licensing_note': '自主制定产品策略，未宣称临床验证',
                      },
                    ],
                  },
                ],
              };
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(ChoiceChip, '骨性标志'));
      await tester.pumpAndSettle();
      expect(paths.last, contains('kind=bone_landmark'));
      await tester.ensureVisible(find.text('高杠深蹲阶段'));
      await tester.tap(find.text('高杠深蹲阶段'));
      await tester.pumpAndSettle();
      expect(find.text('各阶段作用与提示'), findsOneWidget);
      expect(find.text('相关骨性标志'), findsOneWidget);
      expect(find.text('髂嵴'), findsWidgets);
      await tester.scrollUntilVisible(
        find.textContaining('训练执行产品策略'),
        250,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.textContaining('练伴产品策略'), findsWidgets);
      expect(find.textContaining('default_target_rir'), findsNothing);
      expect(find.text('规则编号'), findsNothing);
      expect(find.textContaining('backend/periodization.py'), findsNothing);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'admin can register builtins, prepare index and compare retrieval on phone layout',
    (tester) async {
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final writes = <String>[];
      var registered = false;
      await tester.pumpWidget(
        MaterialApp(
          home: KnowledgePage(
            admin: true,
            request: (path, method, body) async {
              if (method == 'POST') {
                writes.add(path);
                if (path == '/knowledge/builtin-candidate') registered = true;
                return {};
              }
              if (path == '/knowledge') {
                return {
                  'version': 'foundation-test-v2',
                  'counts': {},
                  'retrieval': {
                    'assets_present': true,
                    'runtime_installed': true,
                  },
                };
              }
              if (path == '/knowledge/admin') {
                return {
                  'available_builtin': {
                    'version': 'foundation-test-v2',
                    'registered': registered,
                  },
                  'bundles': [
                    {'id': 'foundation-test-v2', 'status': 'reviewed'},
                  ],
                  'retrieval_evaluations': [
                    {
                      'version': 'foundation-test-v2',
                      'status': 'failed',
                      'passed': false,
                      'variants': {
                        'hybrid_rerank': {
                          'test': {
                            'recall_at_5': 0.9,
                            'mrr': 0.8,
                            'ndcg_at_5': 0.85,
                            'cases': 60,
                            'latency_ms': {'p50': 100, 'p95': 230},
                            'fallback_cases': ['case-1'],
                          },
                        },
                      },
                    },
                  ],
                };
              }
              return {
                'items': [],
                'retrieval': {
                  'effective_mode': 'bm25',
                  'fallback_reason': 'model_missing',
                },
              };
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.textContaining('已改用可用的检索方式'), findsOneWidget);
      Future<void> reveal(String label) async {
        await tester.scrollUntilVisible(
          find.text(label),
          200,
          scrollable: find.byType(Scrollable).first,
        );
        await tester.pumpAndSettle();
      }

      await reveal('知识审核与评测');
      await tester.tap(find.text('知识审核与评测'));
      await tester.pumpAndSettle();
      await reveal('登记新版内置知识');
      await tester.tap(find.text('登记新版内置知识'));
      await tester.pumpAndSettle();
      await reveal('准备当前知识索引');
      await tester.tap(find.text('准备当前知识索引'));
      await tester.pumpAndSettle();
      await reveal('对比当前检索');
      await tester.tap(find.text('对比当前检索'));
      await tester.pumpAndSettle();
      expect(
        writes,
        isNot(
          contains('/knowledge/bundles/foundation-test-v2/retrieval-evaluate'),
        ),
      );
      await tester.tap(find.text('确认'));
      await tester.pumpAndSettle();
      expect(
        writes,
        containsAll([
          '/knowledge/builtin-candidate',
          '/knowledge/index',
          '/knowledge/bundles/foundation-test-v2/retrieval-evaluate',
        ]),
      );
      await reveal('foundation-test-v2 · 检索对比');
      await tester.tap(find.text('foundation-test-v2 · 检索对比'));
      await tester.pumpAndSettle();
      await reveal('召回率 90.0% · MRR 80.0% · nDCG 85.0%');
      expect(find.text('未通过或尚未完成全部门槛'), findsOneWidget);
      expect(find.textContaining('包含降级运行'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'knowledge filtering, attachments, related nodes and provenance',
    (tester) async {
      final paths = <String>[];
      await tester.pumpWidget(
        MaterialApp(
          home: KnowledgePage(
            request: (path, method, body) async {
              paths.add(path);
              if (path == '/knowledge') {
                return {
                  'name': '练伴基础知识',
                  'version': 'foundation-test',
                  'counts': {'muscle': 1},
                  'scope': '三大项',
                  'verification': '未经专业验证',
                };
              }
              if (path.startsWith('/knowledge/search')) {
                return {
                  'items': [
                    {
                      'id': 'rectus_femoris',
                      'kind': 'muscle',
                      'title': '股直肌',
                      'summary': '跨髋与膝的肌肉',
                    },
                  ],
                };
              }
              if (path == '/knowledge/items/rectus_femoris') {
                return {
                  'version': 'foundation-test',
                  'items': [
                    {
                      'title': '股直肌',
                      'summary': '主要附着概述',
                      'facts': {
                        'origin': ['髂前下棘'],
                        'joint_ids': ['hip', 'knee'],
                      },
                      'population': ['一般成人'],
                      'limitations': ['不代表肌肉激活'],
                    },
                  ],
                  'related_items': [
                    {'id': 'hip', 'title': '髋关节'},
                    {'id': 'knee', 'title': '膝关节'},
                  ],
                  'citations': [
                    {
                      'sources': [
                        {
                          'title': 'UAMS 解剖表',
                          'edition': '在线资料',
                          'locator': 'rectus femoris',
                          'accessed_on': '2026-10-22',
                          'content_use': 'paraphrased_facts',
                          'url': 'https://medicine.uams.edu/',
                        },
                      ],
                    },
                  ],
                };
              }
              throw Exception('unexpected $path');
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('未经专业验证'), findsOneWidget);
      expect(find.text('知识审核与评测'), findsNothing);
      await tester.tap(find.widgetWithText(ChoiceChip, '肌肉'));
      await tester.pumpAndSettle();
      expect(paths.last, contains('kind=muscle'));
      await tester.ensureVisible(find.text('股直肌'));
      await tester.tap(find.text('股直肌'));
      await tester.pumpAndSettle();
      expect(find.text('主要起点'), findsOneWidget);
      expect(find.text('髂前下棘'), findsOneWidget);
      expect(find.textContaining('UAMS 解剖表'), findsOneWidget);
      expect(find.widgetWithText(ActionChip, '髋关节'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
