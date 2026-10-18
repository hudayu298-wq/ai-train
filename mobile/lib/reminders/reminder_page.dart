import 'package:flutter/material.dart';

import '../coach_avatar.dart';
import 'coach_reminders.dart';
import 'reminder_settings.dart';

class ReminderPage extends StatefulWidget {
  const ReminderPage({
    super.key,
    required this.service,
    required this.sync,
    this.readSaved,
  });
  final CoachReminders service;
  final Future<void> Function(ReminderSettings) sync;
  final Future<ReminderSettings> Function()? readSaved;

  @override
  State<ReminderPage> createState() => _ReminderPageState();
}

class _ReminderPageState extends State<ReminderPage> {
  final name = TextEditingController();
  ReminderSettings draft = ReminderSettings();
  bool loaded = false, busy = false;
  String? message;

  @override
  void initState() {
    super.initState();
    widget.service.initialize().then((_) {
      if (!mounted) return;
      setState(() {
        draft = widget.service.settings.copy();
        name.text = draft.coachName;
        loaded = true;
      });
    });
  }

  @override
  void dispose() {
    name.dispose();
    super.dispose();
  }

  Future<void> time(String current, void Function(String) update) async {
    final pieces = current.split(':').map(int.parse).toList();
    final selected = await showTimePicker(
      context: context,
      initialTime: TimeOfDay(hour: pieces[0], minute: pieces[1]),
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
        child: child!,
      ),
    );
    if (selected != null && mounted) {
      setState(
        () => update(
          '${selected.hour.toString().padLeft(2, '0')}:${selected.minute.toString().padLeft(2, '0')}',
        ),
      );
    }
  }

  Future<void> save() async {
    if (busy || !loaded) return;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      draft.coachName = name.text.trim();
      await widget.service.save(draft);
      if (!mounted) return;
      setState(() => message = '设置已保存到本机。');
      try {
        await widget.sync(draft.copy());
        if (mounted) setState(() => message = '本机设置已保存，并已同步到用户画像。');
      } catch (e) {
        if (mounted) setState(() => message = '本机设置已保存；画像同步失败，连接后再次保存可重试。\n$e');
      }
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget card(String title, List<Widget> children) => Card(
    margin: const EdgeInsets.only(bottom: 18),
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    ),
  );

  Widget upcoming() {
    final now = DateTime.now();
    final events = buildReminders(
      widget.service.settings,
      goal: widget.service.goal,
    )..sort((a, b) => a.nextAfter(now).compareTo(b.nextAfter(now)));
    return card('已保存的提醒时间', [
      if (events.isEmpty) const Text('还没有开启提醒。'),
      for (final event in events.take(5))
        Builder(
          builder: (_) {
            final next = event.nextAfter(now);
            return ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.notifications_outlined),
              title: Text(event.title),
              subtitle: Text(
                '${next.month}月${next.day}日 ${weekdayLabels[next.weekday - 1]} ${next.hour.toString().padLeft(2, '0')}:${next.minute.toString().padLeft(2, '0')}',
              ),
            );
          },
        ),
    ]);
  }

  @override
  Widget build(BuildContext context) => AnimatedBuilder(
    animation: widget.service,
    builder: (_, _) => Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        card('你的虚拟私教', [
          Row(
            children: [
              const CoachAvatar(size: 88),
              const SizedBox(width: 16),
              Expanded(
                child: Text(
                  '${widget.service.settings.coachName}会按你设定的时间，提醒训练和用餐。',
                  style: const TextStyle(height: 1.5),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: name,
            maxLength: 16,
            enabled: loaded && !busy,
            decoration: const InputDecoration(
              labelText: '教练昵称',
              border: OutlineInputBorder(),
            ),
          ),
          const Text('所有时间均为北京时间（Asia/Shanghai）。'),
        ]),
        card('训练提醒', [
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('按训练日提醒'),
            value: draft.trainingEnabled,
            onChanged: loaded && !busy
                ? (v) => setState(() => draft.trainingEnabled = v)
                : null,
          ),
          Wrap(
            spacing: 8,
            children: [
              for (int day = 1; day <= 7; day++)
                FilterChip(
                  label: Text(weekdayLabels[day - 1]),
                  selected: draft.trainingDays.contains(day),
                  onSelected: loaded && !busy
                      ? (v) => setState(() {
                          if (v) {
                            draft.trainingDays.add(day);
                          } else {
                            draft.trainingDays.remove(day);
                          }
                        })
                      : null,
                ),
            ],
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            icon: const Icon(Icons.schedule),
            label: Text('训练开始时间 · ${draft.trainingTime}'),
            onPressed: loaded && !busy
                ? () => time(draft.trainingTime, (v) => draft.trainingTime = v)
                : null,
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<int>(
            key: ValueKey(draft.leadMinutes),
            initialValue: draft.leadMinutes,
            decoration: const InputDecoration(
              labelText: '训练前提前提醒',
              border: OutlineInputBorder(),
            ),
            items: [
              for (final minute in {
                ...[0, 10, 15, 30, 60],
                draft.leadMinutes,
              })
                DropdownMenuItem(
                  value: minute,
                  child: Text(minute == 0 ? '仅到点提醒' : '提前 $minute 分钟'),
                ),
            ],
            onChanged: loaded && !busy
                ? (v) => setState(() => draft.leadMinutes = v!)
                : null,
          ),
          const SizedBox(height: 12),
          const Text('保存开启的训练安排后，训练日数量和时间会同步到用户画像。'),
        ]),
        card('饮食提醒', [
          SwitchListTile(
            contentPadding: EdgeInsets.zero,
            title: const Text('按用餐时间提醒'),
            value: draft.mealsEnabled,
            onChanged: loaded && !busy
                ? (v) => setState(() => draft.mealsEnabled = v)
                : null,
          ),
          for (final entry in mealLabels.entries)
            Row(
              children: [
                Expanded(
                  child: CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(entry.value),
                    value: draft.mealTimes.containsKey(entry.key),
                    onChanged: loaded && !busy
                        ? (v) => setState(() {
                            if (v == true) {
                              draft.mealTimes[entry.key] =
                                  ReminderSettings().mealTimes[entry.key]!;
                            } else {
                              draft.mealTimes.remove(entry.key);
                            }
                          })
                        : null,
                  ),
                ),
                TextButton(
                  onPressed:
                      loaded && !busy && draft.mealTimes.containsKey(entry.key)
                      ? () => time(
                          draft.mealTimes[entry.key]!,
                          (v) => draft.mealTimes[entry.key] = v,
                        )
                      : null,
                  child: Text(draft.mealTimes[entry.key] ?? '未提醒'),
                ),
              ],
            ),
          const Text('用餐提醒每日重复；如果已经吃过，记录这一餐即可。'),
        ]),
        if (!loaded || busy) const LinearProgressIndicator(),
        FilledButton.icon(
          icon: const Icon(Icons.check),
          label: const Text('保存教练与提醒设置'),
          onPressed: loaded && !busy ? save : null,
        ),
        if (message != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(message!),
          ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Text(widget.service.status),
        ),
        if (widget.service.native)
          OutlinedButton(
            onPressed: loaded && !busy
                ? () async {
                    try {
                      await widget.service.requestPermission();
                      await widget.service.reconcile();
                      widget.service.changed();
                    } catch (e) {
                      if (mounted) setState(() => message = '$e');
                    }
                  }
                : null,
            child: const Text('允许系统通知 / 重新安排提醒'),
          ),
        OutlinedButton.icon(
          icon: const Icon(Icons.notifications_active_outlined),
          label: const Text('测试教练提醒'),
          onPressed: loaded && !busy
              ? () async {
                  try {
                    await widget.service.testNotification();
                  } catch (e) {
                    if (mounted) setState(() => message = '$e');
                  }
                }
              : null,
        ),
        const SizedBox(height: 18),
        if (widget.readSaved != null)
          OutlinedButton(
            onPressed: loaded && !busy
                ? () async {
                    setState(() => busy = true);
                    try {
                      final saved = await widget.readSaved!();
                      saved.validate();
                      if (mounted) {
                        setState(() {
                          draft = saved;
                          name.text = saved.coachName;
                          message = '已载入保存的安排；点击保存，在本机生效。';
                        });
                      }
                    } catch (e) {
                      if (mounted) setState(() => message = '$e');
                    } finally {
                      if (mounted) setState(() => busy = false);
                    }
                  }
                : null,
            child: const Text('载入已保存安排'),
          ),
        upcoming(),
        Text(
          widget.service.native
              ? '请允许通知。若锁屏后收不到提醒，检查手机对 LiftLab 的后台运行与省电限制；系统可能延后通知。'
              : '网页提醒需要保持页面在前台。关闭页面后不会发送系统通知。',
        ),
        const SizedBox(height: 18),
      ],
    ),
  );
}
