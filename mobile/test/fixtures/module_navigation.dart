import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> openSection(WidgetTester tester, String title) async {
  final row = find.widgetWithText(ListTile, title);
  await tester.ensureVisible(row);
  await tester.pumpAndSettle();
  await tester.tap(row);
  await tester.pumpAndSettle();
}

Future<void> sectionOverview(
  WidgetTester tester, {
  String label = '查看全部分组',
}) async {
  final back = find.text(label).last;
  await tester.ensureVisible(back);
  await tester.pumpAndSettle();
  await tester.tap(back);
  await tester.pumpAndSettle();
}
