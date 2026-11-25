import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/live/motion_replay_page.dart';
import 'package:liftlab/live/motion_replay.dart';

void main() {
  testWidgets(
    'web-accessible demo shows actual evidence and no accuracy claim; new input clears results',
    (tester) async {
      tester.view.physicalSize = const Size(1100, 2000);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(
        const MaterialApp(home: MotionReplayPage(exerciseId: 'squat')),
      );
      await tester.tap(find.text('运行合成演示'));
      await tester.pumpAndSettle();
      expect(find.text('合成演示结果 · 无真实训练录像'), findsOneWidget);
      expect(find.textContaining('检测到 2 个周期'), findsOneWidget);
      expect(find.textContaining('未生成准确率结论'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('第1组 · 检测周期1'),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.tap(find.text('第1组 · 检测周期1'));
      await tester.pumpAndSettle();
      expect(find.textContaining('不是实际关节活动度测量'), findsWidgets);
      await tester.scrollUntilVisible(
        find.byType(TextField).first,
        -300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.enterText(find.byType(TextField).first, '{}');
      await tester.pumpAndSettle();
      expect(find.text('合成演示结果 · 无真实训练录像'), findsNothing);
      await tester.ensureVisible(find.text('回放并计算'));
      await tester.tap(find.text('回放并计算'));
      await tester.pumpAndSettle();
      expect(find.textContaining('未完成回放'), findsOneWidget);
    },
  );
  testWidgets('one rater cannot create consensus metrics', (tester) async {
    tester.view.physicalSize = const Size(1100, 2000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.pumpWidget(
      const MaterialApp(home: MotionReplayPage(exerciseId: 'bench')),
    );
    await tester.enterText(
      find.byType(TextField).first,
      jsonEncode(demoMotionTrace('bench')),
    );
    await tester.tap(find.text('可选：两位标注者独立核对本地录像'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('A已独立标注，未查看另一份答案'));
    await tester.tap(find.text('A已独立标注，未查看另一份答案'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('回放并计算'));
    await tester.tap(find.text('回放并计算'));
    await tester.pumpAndSettle();
    expect(find.textContaining('两份标注都需独立完成'), findsOneWidget);
    expect(find.textContaining('计次绝对误差'), findsNothing);
  });
}
