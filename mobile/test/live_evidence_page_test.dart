import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/live/live_session.dart';

void main() {
  testWidgets(
    'live page keeps trace consent off and opens replay without writing a workout',
    (tester) async {
      tester.view.physicalSize = const Size(1100, 2200);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(
            const MethodChannel('flutter_tts'),
            (call) async => 1,
          );
      addTearDown(
        () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(const MethodChannel('flutter_tts'), null),
      );
      int writes = 0;
      await tester.pumpWidget(
        MaterialApp(
          home: LiveSession(
            exerciseId: 'squat',
            onFinish: (_, _, _) async {
              writes++;
              return true;
            },
          ),
        ),
      );
      final consent = find.widgetWithText(SwitchListTile, '仅在本页缓存关键点，供本人回放');
      await tester.ensureVisible(consent);
      expect(tester.widget<SwitchListTile>(consent).value, false);
      await tester.tap(consent);
      await tester.pumpAndSettle();
      expect(tester.widget<SwitchListTile>(consent).value, true);
      await tester.tap(consent);
      await tester.pumpAndSettle();
      expect(tester.widget<SwitchListTile>(consent).value, false);
      await tester.ensureVisible(find.text('证据回放与双人标注'));
      await tester.tap(find.text('证据回放与双人标注'));
      await tester.pumpAndSettle();
      expect(find.text('伴练证据回放与标注'), findsOneWidget);
      await tester.tap(find.text('运行合成演示'));
      await tester.pumpAndSettle();
      expect(find.textContaining('检测到 2 个周期'), findsOneWidget);
      expect(writes, 0);
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
    },
  );
}
