import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:timezone/data/latest.dart' as tzdata;

import 'reminder_settings.dart';

class CoachReminders extends ChangeNotifier {
  CoachReminders({FlutterLocalNotificationsPlugin? notifications, bool? native})
    : notifications = notifications ?? FlutterLocalNotificationsPlugin(),
      native =
          native ??
          (!kIsWeb &&
              (defaultTargetPlatform == TargetPlatform.android ||
                  defaultTargetPlatform == TargetPlatform.iOS));
  final FlutterLocalNotificationsPlugin notifications;
  final bool native;
  ReminderSettings settings = ReminderSettings();
  SharedPreferences? preferences;
  String goal = '', status = '提醒设置加载中…';
  bool ready = false, permission = false, foregroundActive = true;
  bool _disposed = false, _checking = false;
  Future<void>? _initialization;
  Future<void> _reconciliation = Future.value();
  Timer? _timer;
  final Set<String> _fired = {};
  void Function(CoachReminder)? onForegroundReminder;
  void Function(String)? onOpen;

  static const storageKey = 'liftlab.coach.reminders.v1';
  static final ownedIds = [
    for (int day = 1; day <= 7; day++) ...[1100 + day, 1200 + day],
    1301,
    1302,
    1303,
    1999,
  ];
  static const details = NotificationDetails(
    android: AndroidNotificationDetails(
      'liftlab_coach_reminders_v1',
      '私教训练与饮食提醒',
      channelDescription: '按照你设置的训练与用餐时间提醒',
      icon: 'ic_coach_notification',
      importance: Importance.defaultImportance,
      priority: Priority.defaultPriority,
    ),
    iOS: DarwinNotificationDetails(presentAlert: true, presentSound: true),
  );

  void changed() {
    if (!_disposed) notifyListeners();
  }

  Future<void> initialize() => _initialization ??= _initialize();

  Future<void> _initialize() async {
    try {
      tzdata.initializeTimeZones();
      preferences = await SharedPreferences.getInstance();
      final saved = preferences!.getString(storageKey);
      if (saved != null) {
        try {
          final restored = ReminderSettings.fromJson(jsonDecode(saved));
          restored.validate();
          settings = restored;
        } catch (_) {
          settings = ReminderSettings();
          await preferences!.remove(storageKey);
        }
      }
      goal = preferences!.getString('$storageKey.goal') ?? '';
      _fired.addAll(preferences!.getStringList('$storageKey.fired') ?? []);
      if (_disposed) return;
      if (native) {
        await notifications.initialize(
          settings: const InitializationSettings(
            android: AndroidInitializationSettings('ic_coach_notification'),
            iOS: DarwinInitializationSettings(
              requestAlertPermission: false,
              requestBadgePermission: false,
              requestSoundPermission: false,
            ),
          ),
          onDidReceiveNotificationResponse: (response) =>
              onOpen?.call(response.payload ?? ''),
        );
        final launch = await notifications.getNotificationAppLaunchDetails();
        if (launch?.didNotificationLaunchApp == true) {
          onOpen?.call(launch!.notificationResponse?.payload ?? '');
        }
        await _checkPermission();
      }
      ready = true;
      await reconcile();
      if (!_disposed && !native) {
        _timer = Timer.periodic(
          const Duration(seconds: 15),
          (_) => checkForeground(),
        );
      }
    } catch (e) {
      ready = false;
      status = '提醒尚未就绪：$e';
    }
    changed();
  }

  Future<void> _checkPermission() async {
    if (defaultTargetPlatform == TargetPlatform.android) {
      permission =
          await notifications
              .resolvePlatformSpecificImplementation<
                AndroidFlutterLocalNotificationsPlugin
              >()
              ?.areNotificationsEnabled() ??
          false;
    } else if (defaultTargetPlatform == TargetPlatform.iOS) {
      final value = await notifications
          .resolvePlatformSpecificImplementation<
            IOSFlutterLocalNotificationsPlugin
          >()
          ?.checkPermissions();
      permission = value?.isAlertEnabled ?? false;
    }
  }

  Future<bool> requestPermission() async {
    await initialize();
    if (!native) return false;
    if (defaultTargetPlatform == TargetPlatform.android) {
      permission =
          await notifications
              .resolvePlatformSpecificImplementation<
                AndroidFlutterLocalNotificationsPlugin
              >()
              ?.requestNotificationsPermission() ??
          false;
    } else {
      permission =
          await notifications
              .resolvePlatformSpecificImplementation<
                IOSFlutterLocalNotificationsPlugin
              >()
              ?.requestPermissions(alert: true, badge: false, sound: true) ??
          false;
    }
    return permission;
  }

  Future<void> save(
    ReminderSettings config, {
    bool askPermission = true,
  }) async {
    config.validate();
    await initialize();
    if (!ready || preferences == null) throw StateError('本地提醒尚未就绪，请重启应用后重试');
    if (askPermission &&
        native &&
        (config.trainingEnabled || config.mealsEnabled)) {
      await requestPermission();
    }
    final saved = await preferences!.setString(
      storageKey,
      jsonEncode(config.toJson()),
    );
    if (!saved) throw StateError('提醒设置未能保存，请重试');
    settings = config.copy();
    await reconcile();
    changed();
  }

  Future<void> updateGoal(String value) async {
    await initialize();
    if (goal == value || _disposed) return;
    goal = value;
    await preferences?.setString('$storageKey.goal', goal);
    await reconcile();
    changed();
  }

  Future<void> reconcile() {
    final task = _reconciliation
        .catchError((Object _) {})
        .then((_) => _reconcile());
    _reconciliation = task;
    return task;
  }

  Future<void> _reconcile() async {
    if (_disposed || !ready) return;
    final events = buildReminders(settings, goal: goal);
    if (!native) {
      status = events.isEmpty
          ? '提醒已关闭'
          : '已保存 ${events.length} 条循环提醒；仅在页面打开并处于前台时显示。';
      return;
    }
    // Only cancel this feature's IDs; leave unrelated notification channels alone.
    for (final id in ownedIds) {
      await notifications.cancel(id: id);
    }
    if (events.isEmpty) {
      status = '提醒已关闭，原有提醒已取消';
      return;
    }
    await _checkPermission();
    if (!permission) {
      status = '设置已保存，但系统通知未获允许。请开启通知权限后重试。';
      return;
    }
    try {
      for (final event in events) {
        await notifications.zonedSchedule(
          id: event.id,
          title: event.title,
          body: event.body,
          scheduledDate: event.nextAfter(DateTime.now()),
          notificationDetails: details,
          androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
          matchDateTimeComponents: event.weekday == null
              ? DateTimeComponents.time
              : DateTimeComponents.dayOfWeekAndTime,
          payload: event.destination,
        );
      }
      status = '已安排 ${events.length} 条循环提醒，断网后仍可提醒；省电模式可能延后通知。';
    } catch (e) {
      for (final id in ownedIds) {
        await notifications.cancel(id: id);
      }
      status = '设置已保存，但通知安排失败，请重试：$e';
      rethrow;
    }
  }

  Future<void> resume() async {
    await initialize();
    foregroundActive = true;
    if (native) {
      await _checkPermission();
      await reconcile();
      changed();
    } else {
      await checkForeground();
    }
  }

  Future<void> checkForeground({DateTime? now}) async {
    if (native || !ready || _disposed || _checking || !foregroundActive) return;
    _checking = true;
    try {
      final instant = now ?? DateTime.now();
      for (final event in buildReminders(settings, goal: goal)) {
        final key = event.occurrenceKey(instant);
        if (event.isDue(instant) && !_fired.contains(key)) {
          _fired.add(key);
          onForegroundReminder?.call(event);
        }
      }
      // Bounded deduplication cache survives page refreshes during the same minute.
      final kept = _fired.toList();
      if (kept.length > 120) {
        _fired
          ..clear()
          ..addAll(kept.skip(kept.length - 120));
      }
      await preferences?.setStringList('$storageKey.fired', _fired.toList());
    } finally {
      _checking = false;
    }
  }

  Future<void> testNotification() async {
    await initialize();
    if (!native) {
      onForegroundReminder?.call(
        CoachReminder(
          id: 1999,
          title: '${settings.coachName} · 提醒测试',
          body: '我会按你设置的时间提醒训练和饮食。',
          hour: 0,
          minute: 0,
          destination: 'chat',
        ),
      );
      return;
    }
    if (!await requestPermission()) {
      status = '系统通知未获允许，测试通知未发送。';
      changed();
      return;
    }
    await notifications.show(
      id: 1999,
      title: '${settings.coachName} · 提醒测试',
      body: '我会按你设置的时间提醒训练和饮食。',
      notificationDetails: details,
      payload: 'chat',
    );
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
