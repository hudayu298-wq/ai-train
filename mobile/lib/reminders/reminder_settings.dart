import 'package:timezone/timezone.dart' as tz;

import '../coaches/coach_persona.dart';

const weekdayLabels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const mealLabels = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐'};

class ReminderSettings {
  ReminderSettings({
    this.coachName = '阿衡',
    this.coachId = 'steady',
    this.trainingEnabled = false,
    List<int>? trainingDays,
    this.trainingTime = '19:00',
    this.leadMinutes = 15,
    this.mealsEnabled = false,
    Map<String, String>? mealTimes,
  }) : trainingDays = trainingDays ?? [1, 3, 5],
       mealTimes =
           mealTimes ??
           {'breakfast': '07:30', 'lunch': '12:00', 'dinner': '18:30'};

  String coachName;
  String coachId;
  bool trainingEnabled, mealsEnabled;
  List<int> trainingDays;
  String trainingTime;
  int leadMinutes;
  Map<String, String> mealTimes;

  factory ReminderSettings.fromJson(Map<String, dynamic> data) =>
      ReminderSettings(
        coachName: data['coach_name'] == '林教练'
            ? '阿衡'
            : data['coach_name'] ??
                  personaFor(data['coach_id'] ?? 'steady').name,
        coachId: data['coach_id'] ?? 'steady',
        trainingEnabled: data['training_enabled'] ?? false,
        trainingDays: (data['training_days'] as List? ?? [1, 3, 5])
            .cast<int>()
            .toList(),
        trainingTime: data['training_time'] ?? '19:00',
        leadMinutes: data['lead_minutes'] ?? 15,
        mealsEnabled: data['meals_enabled'] ?? false,
        mealTimes: Map<String, String>.from(
          data['meal_times'] ??
              mealLabels.map(
                (k, _) => MapEntry(k, switch (k) {
                  'breakfast' => '07:30',
                  'lunch' => '12:00',
                  _ => '18:30',
                }),
              ),
        ),
      );

  Map<String, dynamic> toJson() => {
    'coach_name': coachName.trim(),
    'coach_id': coachId,
    'timezone': 'Asia/Shanghai',
    'training_enabled': trainingEnabled,
    'training_days': [...trainingDays]..sort(),
    'training_time': trainingTime,
    'lead_minutes': leadMinutes,
    'meals_enabled': mealsEnabled,
    'meal_times': Map<String, String>.from(mealTimes),
  };

  ReminderSettings copy() => ReminderSettings.fromJson(toJson());

  void validate() {
    if (!coachPersonas.any((p) => p.id == coachId)) {
      throw const FormatException('请选择现有的四位教练之一');
    }
    final clock = RegExp(r'^([01]\d|2[0-3]):[0-5]\d$');
    if (coachName.trim().isEmpty || coachName.trim().length > 16) {
      throw const FormatException('教练昵称请填写1–16个字');
    }
    if (!clock.hasMatch(trainingTime) ||
        mealTimes.values.any((v) => !clock.hasMatch(v)) ||
        mealTimes.keys.any((v) => !mealLabels.containsKey(v))) {
      throw const FormatException('时间请使用有效的24小时制时间');
    }
    if (leadMinutes < 0 ||
        leadMinutes > 60 ||
        trainingDays.any((v) => v < 1 || v > 7) ||
        trainingDays.toSet().length != trainingDays.length) {
      throw const FormatException('请检查训练日和提前提醒时间');
    }
    if (trainingEnabled && trainingDays.isEmpty) {
      throw const FormatException('请至少选择一个训练日');
    }
    if (mealsEnabled && mealTimes.isEmpty) {
      throw const FormatException('请至少选择一餐');
    }
  }
}

class CoachReminder {
  const CoachReminder({
    required this.id,
    required this.title,
    required this.body,
    required this.hour,
    required this.minute,
    required this.destination,
    this.weekday,
  });
  final int id, hour, minute;
  final int? weekday;
  final String title, body, destination;

  tz.TZDateTime nextAfter(DateTime instant) {
    final location = tz.getLocation('Asia/Shanghai');
    final now = tz.TZDateTime.from(instant, location);
    for (int day = 0; day <= 7; day++) {
      final candidate = tz.TZDateTime(
        location,
        now.year,
        now.month,
        now.day + day,
        hour,
        minute,
      );
      if ((weekday == null || candidate.weekday == weekday) &&
          candidate.isAfter(now)) {
        return candidate;
      }
    }
    throw StateError('没有下次提醒时间');
  }

  bool isDue(DateTime instant) {
    final now = tz.TZDateTime.from(instant, tz.getLocation('Asia/Shanghai'));
    return (weekday == null || weekday == now.weekday) &&
        hour == now.hour &&
        minute == now.minute;
  }

  String occurrenceKey(DateTime instant) {
    final now = tz.TZDateTime.from(instant, tz.getLocation('Asia/Shanghai'));
    return '$id:${now.year}-${now.month}-${now.day}:$hour:$minute';
  }
}

List<CoachReminder> buildReminders(
  ReminderSettings settings, {
  String goal = '',
}) {
  settings.validate();
  final result = <CoachReminder>[];
  final persona = personaFor(settings.coachId);
  final encouragement = switch (goal) {
    'muscle_gain' => '为增肌目标积累一次稳定的训练。',
    'fat_loss' => '为减脂目标保持规律运动。',
    _ => '按自己的节奏，完成今天计划中的训练。',
  };
  if (settings.trainingEnabled) {
    final parts = settings.trainingTime.split(':').map(int.parse).toList();
    for (final day in settings.trainingDays) {
      result.add(
        CoachReminder(
          id: 1100 + day,
          title: '${settings.coachName} · 该训练啦',
          body: '${persona.trainingLine} $encouragement',
          weekday: day,
          hour: parts[0],
          minute: parts[1],
          destination: 'training',
        ),
      );
      if (settings.leadMinutes > 0) {
        final minutes = parts[0] * 60 + parts[1] - settings.leadMinutes;
        final shiftedDay = minutes < 0 ? (day == 1 ? 7 : day - 1) : day;
        final clock = (minutes + 1440) % 1440;
        result.add(
          CoachReminder(
            id: 1200 + day,
            title: '${settings.coachName} · 准备训练',
            body: persona.leadLine.replaceAll(
              '{minutes}',
              '${settings.leadMinutes}',
            ),
            weekday: shiftedDay,
            hour: clock ~/ 60,
            minute: clock % 60,
            destination: 'training',
          ),
        );
      }
    }
  }
  if (settings.mealsEnabled) {
    for (final entry in settings.mealTimes.entries) {
      final parts = entry.value.split(':').map(int.parse).toList();
      result.add(
        CoachReminder(
          id: 1301 + mealLabels.keys.toList().indexOf(entry.key),
          title: '${settings.coachName} · ${mealLabels[entry.key]}时间',
          body: persona.mealLine.replaceAll('{meal}', mealLabels[entry.key]!),
          hour: parts[0],
          minute: parts[1],
          destination: 'nutrition',
        ),
      );
    }
  }
  return result;
}
