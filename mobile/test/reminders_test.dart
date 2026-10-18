import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;
import 'package:liftlab/reminders/coach_reminders.dart';
import 'package:liftlab/reminders/reminder_settings.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() {
    SharedPreferences.setMockInitialValues({});
    tzdata.initializeTimeZones();
  });

  test('training lead crosses midnight onto Sunday and next dates use Beijing time', () {
    final settings = ReminderSettings(
      trainingEnabled: true,
      trainingDays: [1],
      trainingTime: '00:05',
      leadMinutes: 15,
    );
    final events = buildReminders(settings);
    final before = events.singleWhere((e) => e.id == 1201);
    expect(before.weekday, 7);
    expect([before.hour, before.minute], [23, 50]);
    final now = DateTime.utc(2026, 10, 18, 15, 49);
    expect(
      before.nextAfter(now),
      tz.TZDateTime(tz.getLocation('Asia/Shanghai'), 2026, 10, 18, 23, 50),
    );
    expect(events.singleWhere((e) => e.id == 1101).nextAfter(now).weekday, 1);
    expect(
      buildReminders(
        ReminderSettings(
          trainingEnabled: true,
          trainingDays: [1],
          leadMinutes: 0,
        ),
      ).length,
      1,
    );
  });

  test(
    'foreground reminders persist and do not fire twice or while hidden',
    () async {
      final service = CoachReminders(native: false);
      final events = <CoachReminder>[];
      service.onForegroundReminder = events.add;
      await service.initialize();
      await service.save(
        ReminderSettings(mealsEnabled: true, mealTimes: {'lunch': '12:00'}),
      );
      final lunch = DateTime.utc(2026, 10, 15, 4);
      service.foregroundActive = false;
      await service.checkForeground(now: lunch);
      expect(events, isEmpty);
      service.foregroundActive = true;
      await service.checkForeground(now: lunch);
      await service.checkForeground(
        now: lunch.add(const Duration(seconds: 20)),
      );
      expect(events.length, 1);
      service.dispose();
      final restored = CoachReminders(native: false);
      restored.onForegroundReminder = events.add;
      await restored.initialize();
      expect(restored.settings.mealTimes, {'lunch': '12:00'});
      await restored.checkForeground(now: lunch);
      expect(events.length, 1);
      await restored.checkForeground(now: lunch.add(const Duration(days: 1)));
      expect(events.length, 2);
      await restored.save(ReminderSettings());
      await restored.checkForeground(now: lunch.add(const Duration(days: 2)));
      expect(events.length, 2);
      restored.dispose();
    },
  );

  test('Android schedules recurring notifications, restores offline and cancels on disable', () async {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;
    AndroidFlutterLocalNotificationsPlugin.registerWith();
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
    const channel = MethodChannel('dexterous.com/flutter/local_notifications');
    final scheduled = <Map<dynamic, dynamic>>[];
    final cancelled = <int>[];
    int requests = 0;
    bool allowed = true;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
          switch (call.method) {
            case 'initialize':
              return true;
            case 'getNotificationAppLaunchDetails':
              return {'notificationLaunchedApp': false};
            case 'areNotificationsEnabled':
              return allowed;
            case 'requestNotificationsPermission':
              requests++;
              return allowed;
            case 'zonedSchedule':
              scheduled.add(call.arguments as Map);
              return null;
            case 'cancel':
              cancelled.add((call.arguments as Map)['id']);
              return null;
            default:
              return null;
          }
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );
    final service = CoachReminders(native: true);
    await service.initialize();
    expect(service.ready, isTrue, reason: service.status);
    expect(requests, 0);
    await service.save(
      ReminderSettings(
        trainingEnabled: true,
        trainingDays: [1, 3],
        mealsEnabled: true,
      ),
    );
    expect(scheduled.length, 7);
    expect(scheduled.map((e) => e['id']).toSet().length, 7);
    expect(
      scheduled.every((e) => e['timeZoneName'] == 'Asia/Shanghai'),
      isTrue,
    );
    expect(
      scheduled.singleWhere((e) => e['id'] == 1101)['payload'],
      'training',
    );
    expect(
      scheduled.singleWhere((e) => e['id'] == 1301)['payload'],
      'nutrition',
    );
    service.dispose();
    scheduled.clear();
    final offline = CoachReminders(native: true);
    await offline.initialize();
    expect(scheduled.length, 7);
    expect(requests, 1);
    scheduled.clear();
    await offline.save(ReminderSettings());
    expect(scheduled, isEmpty);
    expect(cancelled.toSet(), CoachReminders.ownedIds.toSet());
    allowed = false;
    await offline.save(ReminderSettings(mealsEnabled: true));
    expect(scheduled, isEmpty);
    expect(offline.status, contains('未获允许'));
    expect(offline.settings.mealsEnabled, isTrue);
    offline.dispose();
  });

  test(
    'changing meal time can remind at the new time on the same day',
    () async {
      final service = CoachReminders(native: false);
      final events = <CoachReminder>[];
      service.onForegroundReminder = events.add;
      await service.initialize();
      await service.save(
        ReminderSettings(mealsEnabled: true, mealTimes: {'lunch': '12:00'}),
      );
      await service.checkForeground(now: DateTime.utc(2026, 10, 15, 4));
      await service.save(
        ReminderSettings(mealsEnabled: true, mealTimes: {'lunch': '13:00'}),
      );
      await service.checkForeground(now: DateTime.utc(2026, 10, 15, 5));
      expect(events.length, 2);
      service.dispose();
    },
  );
}
