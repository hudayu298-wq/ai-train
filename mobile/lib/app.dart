import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'package:http_parser/http_parser.dart';

import 'live/live_session.dart';
import 'user_plan_editor.dart';
import 'profile_setup.dart';
import 'fitness_onboarding.dart';
import 'library_page.dart';
import 'coach_chat.dart';
import 'coach_avatar.dart';
import 'reminders/coach_reminders.dart';
import 'reminders/reminder_page.dart';
import 'reminders/reminder_settings.dart';
import 'coaches/coach_picker.dart';
import 'coaches/coach_persona.dart';
import 'ui_theme.dart';
import 'workout_log.dart';
import 'auth/session.dart';
import 'auth/auth_gate.dart';
import 'auth/account_page.dart';

class LiftLab extends StatelessWidget {
  const LiftLab({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: '练伴',
    debugShowCheckedModeBanner: false,
    theme: buildAppTheme(),
    home: const AuthGate(),
  );
}

class Home extends StatefulWidget {
  const Home({super.key});
  @override
  State<Home> createState() => _HomeState();
}

class _HomeState extends State<Home> with WidgetsBindingObserver {
  int tab = 0;
  bool busy = false;
  String? error;
  Map<String, dynamic>? catalog;
  List<dynamic> plans = [], training = [], meals = [], media = [];
  List<dynamic> rmRecords = [];
  List<dynamic> workouts = [];
  Map<String, dynamic>? nutrition;
  Map<String, dynamic>? coachProfile;
  bool onboardingChecked = false;
  int chatRefreshToken = 0;
  int petReminderRevision = 0;
  String? petReminderText;
  Timer? nutritionTimer;
  late final coachReminders = CoachReminders(ownerId: authSession.user?['id']);
  String mealType = 'breakfast';
  static const mealTypes = {
    'breakfast': '早餐',
    'lunch': '午餐',
    'dinner': '晚餐',
    'snack': '加餐',
  };
  final age = TextEditingController();
  final height = TextEditingController();
  final weight = TextEditingController();
  final restrictions = TextEditingController();
  final dietaryPreferences = TextEditingController();
  final equipment = TextEditingController();
  final trainingPreferences = TextEditingController();
  final schedule = TextEditingController();
  final load = TextEditingController(text: '20');
  final sets = TextEditingController(text: '3');
  final reps = TextEditingController(text: '5');
  final rpe = TextEditingController(text: '7');
  final grams = TextEditingController(text: '150');
  String sex = '', goal = '', experience = '';
  int days = 0;
  String exercise = 'bench', food = 'rice', liveExercise = 'bench';
  bool pain = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    coachReminders.addListener(remindersChanged);
    coachReminders.onOpen = openReminderDestination;
    coachReminders.onForegroundReminder = (event) {
      if (!mounted) return;
      setState(() {
        petReminderRevision++;
        petReminderText = event.body;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 12),
          content: Row(
            children: [
              CoachAvatar(size: 40, coachId: coachReminders.settings.coachId),
              const SizedBox(width: 12),
              Expanded(child: Text('${event.title}\n${event.body}')),
            ],
          ),
          action: SnackBarAction(
            label: '查看',
            onPressed: () => openReminderDestination(event.destination),
          ),
        ),
      );
    };
    unawaited(coachReminders.initialize());
    nutritionTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      if (!busy && catalog != null) unawaited(refreshNutrition());
    });
    initialize();
  }

  @override
  void dispose() {
    nutritionTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    coachReminders.removeListener(remindersChanged);
    coachReminders.dispose();
    for (final c in [
      age,
      height,
      weight,
      restrictions,
      dietaryPreferences,
      equipment,
      trainingPreferences,
      schedule,
      load,
      sets,
      reps,
      rpe,
      grams,
    ]) {
      c.dispose();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    coachReminders.foregroundActive = state == AppLifecycleState.resumed;
    if (state == AppLifecycleState.resumed) {
      unawaited(
        coachReminders.resume().catchError((Object e) {
          if (mounted) setState(() => error = '提醒状态刷新失败：$e');
        }),
      );
    }
    if (state == AppLifecycleState.resumed && !busy && catalog != null) {
      unawaited(refreshNutrition());
    }
  }

  Future<void> refreshNutrition() async {
    try {
      final result = Map<String, dynamic>.from(
        await request('/nutrition/today'),
      );
      if (mounted) {
        setState(() {
          nutrition = result;
          meals = result['records'];
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = '当天饮食刷新失败：$e');
    }
  }

  void remindersChanged() {
    if (mounted) setState(() {});
  }

  void openReminderDestination(String destination) {
    if (mounted) {
      setState(
        () => tab = switch (destination) {
          'nutrition' => 3,
          'training' => 2,
          _ => 0,
        },
      );
    }
  }

  Future<void> syncReminderSettings(ReminderSettings settings) async {
    await request('/coach/reminders', method: 'PUT', body: settings.toJson());
    await loadCoachProfile();
    await refresh();
  }

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Object? body,
  }) async {
    final req = http.Request(method, Uri.parse('$apiBase/api$path'));
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    final response =
        await http.Response.fromStream(
          await authSession
              .send(req)
              .timeout(
                Duration(
                  seconds:
                      path == '/plans/generate' ||
                          path == '/movement/analyze' ||
                          path == '/coach/messages' ||
                          path.endsWith('/review') ||
                          path.endsWith('/progression')
                      ? 110
                      : 20,
                ),
              ),
        ).timeout(
          Duration(
            seconds:
                path == '/plans/generate' ||
                    path == '/movement/analyze' ||
                    path == '/coach/messages' ||
                    path.endsWith('/review') ||
                    path.endsWith('/progression')
                ? 110
                : 20,
          ),
        );
    final result = jsonDecode(response.body);
    if (response.statusCode >= 400) {
      throw Exception(
        result['detail'] is String ? result['detail'] : '输入不符合要求，请检查数值范围',
      );
    }
    return result;
  }

  Future<void> perform(Future<void> Function() action) async {
    if (busy) return;
    setState(() {
      busy = true;
      error = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) setState(() => error = e.toString());
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> initialize() => perform(() async {
    await coachReminders.initialize();
    final reminderSettings = Map<String, dynamic>.from(
      await request('/coach/reminders'),
    );
    await coachReminders.save(
      ReminderSettings.fromJson(reminderSettings),
      askPermission: false,
    );
    catalog = Map<String, dynamic>.from(
      await request('/catalog?extended=true'),
    );
    normalizeSelections();
    await loadCoachProfile();
    chatRefreshToken++;
    await refresh();
    if (!onboardingChecked) {
      final setup = await request('/onboarding');
      onboardingChecked = true;
      if (setup is Map && setup['required'] == true && mounted) {
        await openOnboarding();
      }
    }
  });

  Future<void> openOnboarding() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => FitnessOnboarding(
          request: (path, method, body) =>
              request(path, method: method, body: body),
          exercises: exercises,
          details: workoutExercises,
          onFinished: () async {
            await loadCoachProfile();
            await refresh();
          },
        ),
      ),
    );
    if (mounted) {
      await loadCoachProfile();
      await refresh();
    }
  }

  Future<void> loadCoachProfile() async {
    final result = Map<String, dynamic>.from(await request('/coach/profile'));
    if (!mounted) return;
    final p = result['facts'] as Map;
    setState(() {
      coachProfile = result;
      for (final e in {
        'age': age,
        'height_cm': height,
        'weight_kg': weight,
        'restrictions': restrictions,
        'dietary_preferences': dietaryPreferences,
        'equipment': equipment,
        'training_preferences': trainingPreferences,
        'schedule': schedule,
      }.entries) {
        e.value.text = '${p[e.key] ?? ''}';
      }
      sex = p['sex'] ?? '';
      goal = p['goal'] ?? '';
      experience = p['experience'] ?? '';
      days = p['days'] ?? 0;
    });
    await coachReminders.updateGoal(p['goal'] ?? '');
  }

  Future<void> profileFromChat() async {
    await loadCoachProfile();
    await refresh();
  }

  Future<void> refresh() async {
    final result = await Future.wait([
      request('/plans'),
      request('/training'),
      request('/nutrition/today'),
      request('/media'),
      request('/rm'),
      request('/workouts'),
    ]);
    if (!mounted) return;
    setState(() {
      plans = result[0];
      training = result[1];
      nutrition = Map<String, dynamic>.from(result[2]);
      meals = nutrition!['records'];
      media = result[3];
      rmRecords = result[4];
      workouts = result[5] is Map ? (result[5]['items'] as List? ?? []) : [];
    });
  }

  void normalizeSelections() {
    if (!exercises.containsKey(exercise)) {
      exercise = exercises.keys.firstOrNull ?? '';
    }
    final foods = catalog!['foods'] as List;
    if (!foods.any((e) => e['id'] == food)) {
      food = foods.isEmpty ? '' : foods.first['id'];
    }
    final live = (catalog!['exercises'] as List).where(
      (e) => e['realtime_supported'] == true,
    );
    if (!live.any((e) => e['id'] == liveExercise)) {
      liveExercise = live.firstOrNull?['id'] ?? '';
    }
  }

  Future<void> refreshCatalog() async {
    final result = Map<String, dynamic>.from(
      await request('/catalog?extended=true'),
    );
    if (!mounted) return;
    setState(() {
      catalog = result;
      normalizeSelections();
    });
    await refresh();
  }

  void openLibrary({required String kind}) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => LibraryPage(
        canManage: authSession.user?['role'] == 'admin',
        assetBase: apiBase,
        kind: kind,
        request: (path, method, body) =>
            request(path, method: method, body: body),
        onChanged: refreshCatalog,
        onSelect: (kind, entry) => setState(() {
          if (kind == 'foods') {
            food = entry['id'];
            tab = 3;
          } else {
            exercise = entry['id'];
            tab = 2;
          }
        }),
      ),
    ),
  );

  void notify(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  double number(TextEditingController c) {
    final value = double.tryParse(c.text);
    if (value == null || !value.isFinite) throw Exception('请输入有效数字');
    return value;
  }

  int integer(TextEditingController c) {
    final value = int.tryParse(c.text);
    if (value == null) throw Exception('年龄、组数和次数须为整数');
    return value;
  }

  Widget field(String title, TextEditingController c, {bool numeric = true}) =>
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: TextField(
          controller: c,
          keyboardType: numeric
              ? const TextInputType.numberWithOptions(decimal: true)
              : TextInputType.text,
          decoration: InputDecoration(
            labelText: title,
            border: const OutlineInputBorder(),
          ),
        ),
      );
  Widget select(
    String title,
    String value,
    Map<String, String> items,
    ValueChanged<String> change,
  ) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: DropdownButtonFormField<String>(
      key: ValueKey('$title-$value-${items.keys.join(',')}'),
      initialValue: items.containsKey(value) ? value : null,
      isExpanded: true,
      decoration: InputDecoration(
        labelText: title,
        border: const OutlineInputBorder(),
      ),
      items: items.entries
          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
          .toList(),
      onChanged: busy || items.isEmpty
          ? null
          : (v) {
              if (v != null) setState(() => change(v));
            },
    ),
  );
  Widget panel(String title, List<Widget> children) => Card(
    margin: const EdgeInsets.only(bottom: 16),
    child: Padding(
      padding: const EdgeInsets.all(18),
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
  Widget action(String title, Future<void> Function() work) => Padding(
    padding: const EdgeInsets.only(top: 12),
    child: FilledButton(
      onPressed: busy ? null : () => perform(work),
      child: Text(title),
    ),
  );
  Map<String, String> get exercises => {
    for (final e in catalog?['exercises'] ?? [])
      if (e['type'] == 'weighted') '${e['id']}': '${e['name']}',
  };
  Widget exerciseSelect() =>
      select('动作变式', exercise, exercises, (v) => exercise = v);

  Widget planPanel() {
    if (plans.isEmpty) {
      return panel('我的训练计划', [const Text('先通过私教对话或“我”补齐画像，再生成 AI 计划并确认保存。')]);
    }
    final p = plans.first;
    return panel('我的计划 · ${p['name']}', [
      Text(p['note']),
      Text(
        '当前版本 ${p['version'] ?? 1} · 第${p['cycle_week'] ?? 1}/${p['cycle_weeks'] ?? 4}周 · 每周${(p['days'] as List).length}次',
      ),
      if (p['cycle_complete'] == true) const Text('本周期已完成，可根据最新画像生成下一周期。'),
      if (p['latest_change'] != null)
        PlanChangeCard(
          event: Map<String, dynamic>.from(p['latest_change']),
          onUndo: () => perform(() async {
            await request(
              '/plans/changes/${p['latest_change']['id']}/undo',
              method: 'POST',
              body: {},
            );
            await refresh();
          }),
        ),
      for (final week in p['weeks'] ?? []) Text('$week'),
      for (final warning in p['risk_warnings'] ?? []) Text('风险提示：$warning'),
      if (p['rationale'] != null) ...[
        Text('制定理由：${p['rationale']}'),
        Text('热身：${p['warmup']}'),
        Text('恢复：${p['recovery']}'),
        Text('调整建议：${p['progression']}'),
      ],
      const SizedBox(height: 12),
      ...[
        for (final d in p['days'])
          Padding(
            padding: const EdgeInsets.only(top: 18),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${d['name']}${d['start_time'] == null ? '' : ' · ${d['start_time']}'}${d['duration_minutes'] == null ? '' : ' · ${d['duration_minutes']}分钟'}',
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                ...[
                  for (final e in d['exercises'])
                    Text(
                      '${e['name']} · ${e['weight_kg'] == null ? '重量待确认' : '${e['weight_kg']} kg'} · ${e['sets']} × ${e['reps']} · 休息 ${e['rest_seconds']} 秒',
                    ),
                ],
              ],
            ),
          ),
      ],
      for (final item in p['assessment']['items'])
        Padding(
          padding: const EdgeInsets.only(top: 12),
          child: Text(
            '${item['day']} · ${exercises[item['exercise_id']]}：${item['load_percent'] == null ? '暂无RM评估' : '${item['load_percent']}% 1RM参考'}\n${item['message']}${item['risk_warning'] == null ? '' : '\n风险提示：${item['risk_warning']}'}',
          ),
        ),
    ]);
  }

  Widget profilePage() => Column(
    children: [
      panel('我的用户画像', [
        trainingMemoryPanel(),
        TextButton.icon(
          onPressed: openOnboarding,
          icon: const Icon(Icons.auto_awesome),
          label: const Text('重新配置画像并生成计划'),
        ),
        if (coachProfile != null)
          ProfileSetup(
            key: ValueKey(jsonEncode(coachProfile!['facts'])),
            facts: Map<String, dynamic>.from(coachProfile!['facts']),
            request: (path, method, body) =>
                request(path, method: method, body: body),
            onSaved: () async {
              await loadCoachProfile();
              await refresh();
              notify('画像已保存');
            },
          ),
      ]),
      StrengthProfile(
        request: (path, method, body) =>
            request(path, method: method, body: body),
        exercises: exercises,
        records: rmRecords,
        onSaved: () async {
          await loadCoachProfile();
          await refresh();
        },
      ),
    ],
  );
  Map<String, Map<String, dynamic>> get workoutExercises => {
    for (final e in catalog?['exercises'] ?? [])
      if (e['type'] == 'weighted') '${e['id']}': Map<String, dynamic>.from(e),
  };

  Future<bool> openWorkoutLog({
    String? liveId,
    List<int> detected = const [],
    int? minutes,
    String? captureId,
  }) async {
    final result = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => WorkoutLogPage(
          request: (path, method, body) =>
              request(path, method: method, body: body),
          exercises: workoutExercises,
          coachId: coachReminders.settings.coachId,
          currentPlan: plans.isEmpty
              ? null
              : Map<String, dynamic>.from(plans.first),
          liveExerciseId: liveId,
          detectedSets: detected,
          liveDurationMinutes: minutes,
          liveCaptureId: captureId,
          initialExerciseId: exercise,
          onSaved: () async {
            final previousPlan = plans.isEmpty ? null : plans.first['id'];
            await loadCoachProfile();
            await refresh();
            if (plans.isNotEmpty &&
                plans.first['id'] != previousPlan &&
                plans.first['source'] == 'progression') {
              notify('下次训练计划已更新，训练计划页可查看差异或撤销');
            }
          },
        ),
      ),
    );
    return result == true;
  }

  Widget trainingMemoryPanel() {
    final memory = coachProfile?['training_memory'] as Map?;
    final count = memory?['session_count'] ?? 0;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('训练档案', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              count == 0
                  ? '确认完成训练后，表现和复盘会持续沉淀到这里。'
                  : '累计 $count 条训练记录 · 近28天训练 ${memory?['training_days_last_28']} 天',
            ),
            if (count > 0) ...[
              Text(
                '最近训练：${memory?['last_training_day']} · 累计 ${memory?['total_sets']} 组',
              ),
              for (final e
                  in (memory?['exercise_progress'] as List? ?? []).take(5))
                Text(
                  '${e['name']} · ${e['last_day']} · ${e['sets']}组 · 平均 RPE ${e['average_rpe']}',
                ),
              if ((memory?['recent_discomfort'] as List? ?? []).isNotEmpty)
                const Text('近期有训练不适记录；下次先确认当前状态，暂停引起不适的动作。'),
            ],
            TextButton(
              onPressed: () => setState(() => tab = 6),
              child: const Text('查看记录与复盘'),
            ),
          ],
        ),
      ),
    );
  }

  Widget trainingPage() => Column(
    children: [
      planPanel(),
      UserPlanEditor(
        key: ValueKey(
          'current-plan-${plans.isEmpty ? 'none' : plans.first['id']}',
        ),
        compact: true,
        post: (path, body) => request(path, method: 'POST', body: body),
        onSaved: refresh,
        exercises: exercises,
        exerciseDetails: {
          for (final e in catalog?['exercises'] ?? [])
            if (e['type'] == 'weighted')
              '${e['id']}': Map<String, dynamic>.from(e),
        },
        rmRecords: rmRecords,
        currentPlan: plans.isEmpty
            ? null
            : Map<String, dynamic>.from(plans.first),
      ),
    ],
  );

  Widget historyPage() => Column(
    children: [
      panel('训练记录与复盘', [
        const Text('每次训练完成后确认实际组次与感受，私教会据此了解你的表现并给出下次建议。'),
        FilledButton.icon(
          onPressed: () => openWorkoutLog(),
          icon: const Icon(Icons.task_alt),
          label: const Text('记录本次训练'),
        ),
      ]),
      panel(
        '训练历史',
        workouts.isEmpty
            ? [const Text('还没有确认的训练记录')]
            : [
                for (final w in workouts)
                  ExpansionTile(
                    tilePadding: EdgeInsets.zero,
                    title: Text(
                      '${w['day']} · ${(w['exercises'] as List).map((e) => e['name']).join('、')}',
                    ),
                    subtitle: Text(
                      w['source'] == 'legacy'
                          ? '旧版动作记录'
                          : '${w['summary']?['summary'] ?? ''}${w['ai_review'] == null ? ' · 基础复盘' : ' · 已有 AI 复盘'}',
                    ),
                    children: [
                      for (final e in w['exercises']) ...[
                        Text('${e['name']} · ${e['weight_basis'] ?? ''}'),
                        for (int i = 0; i < (e['sets'] as List).length; i++)
                          Text(
                            '第 ${i + 1} 组：${e['sets'][i]['weight_kg']} kg × ${e['sets'][i]['reps']} · RPE ${e['sets'][i]['rpe']}${e['sets'][i]['pain'] == true ? ' · 有不适' : ''}',
                          ),
                        if ('${e['notes'] ?? ''}'.isNotEmpty)
                          Text('动作感受：${e['notes']}'),
                      ],
                      if (w['duration_minutes'] != null)
                        Text('本次用时 ${w['duration_minutes']} 分钟'),
                      if ('${w['notes'] ?? ''}'.isNotEmpty)
                        Text('整体感受：${w['notes']}'),
                      WorkoutReview(record: Map<String, dynamic>.from(w)),
                      if (w['source'] != 'legacy' && w['ai_review'] == null)
                        TextButton(
                          onPressed: busy
                              ? null
                              : () => perform(() async {
                                  await request(
                                    '/workouts/${w['id']}/review',
                                    method: 'POST',
                                    body: {
                                      'coach_id':
                                          coachReminders.settings.coachId,
                                    },
                                  );
                                  await loadCoachProfile();
                                  await refresh();
                                }),
                          child: const Text('生成 AI 私教复盘'),
                        ),
                    ],
                  ),
              ],
      ),
    ],
  );
  Widget nutritionPage() => Column(
    children: [
      panel('当天营养 · ${nutrition?['day'] ?? ''}', [
        const Text('按北京时间计算当天摄入，营养目标根据当前画像估算。'),
        if (nutrition?['target_status'] != 'ready')
          Text(
            nutrition?['target_status'] == 'stale'
                ? '请刷新以更新营养目标。'
                : '先保存画像，才能估算每日营养目标。',
          ),
        const SizedBox(height: 12),
        LayoutBuilder(
          builder: (context, box) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final entry in {
                'kcal': '热量',
                'protein': '蛋白质',
                'fat': '脂肪',
                'carbs': '碳水',
              }.entries)
                SizedBox(
                  width: (box.maxWidth - 12) / 2,
                  child: nutrientProgress(entry.key, entry.value),
                ),
            ],
          ),
        ),
      ]),
      panel('记录当天这一餐', [
        const Text('营养按每100克可食部分计算，请核对生熟状态与来源。品牌食品可按包装标签新增。'),
        OutlinedButton.icon(
          onPressed: () => openLibrary(kind: 'foods'),
          icon: const Icon(Icons.search),
          label: const Text('打开食物库'),
        ),
        select('餐次', mealType, mealTypes, (v) => mealType = v),
        select('食物', food, {
          for (final f in catalog?['foods'] ?? []) '${f['id']}': '${f['name']}',
        }, (v) => food = v),
        field('可食重量 / g', grams),
        action('保存饮食', () async {
          await request(
            '/meals',
            method: 'POST',
            body: {
              'food_id': food,
              'grams': number(grams),
              'meal_type': mealType,
            },
          );
          await refresh();
          notify('饮食已记录');
        }),
        action('上传餐食照片', () => upload('meal')),
        const Text('照片仅保存，识别尚未接入。支持 JPG/PNG，最大10MB。'),
      ]),
      for (final group in nutrition?['groups'] ?? [])
        panel('${group['label']} · ${group['totals']['kcal']} kcal', [
          Text(
            '蛋白质 ${group['totals']['protein']} g · 脂肪 ${group['totals']['fat']} g · 碳水 ${group['totals']['carbs']} g',
          ),
          if ((group['items'] as List).isEmpty) const Text('这餐还没有记录'),
          for (final m in group['items'])
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: Text('${m['name']} · ${m['grams']} g'),
              subtitle: Text(
                '${m['nutrients']['kcal']} kcal · 蛋白质 ${m['nutrients']['protein']} g · 脂肪 ${m['nutrients']['fat']} g · 碳水 ${m['nutrients']['carbs']} g',
              ),
              trailing: IconButton(
                icon: const Icon(Icons.delete_outline),
                onPressed: busy
                    ? null
                    : () => perform(() async {
                        await request('/meals/${m['id']}', method: 'DELETE');
                        await refresh();
                      }),
              ),
            ),
        ]),
    ],
  );
  Widget nutrientProgress(String key, String label) {
    final metric = nutrition?['comparison'][key];
    if (metric == null) return const SizedBox.shrink();
    final unit = key == 'kcal' ? 'kcal' : 'g';
    final target = metric['target'];
    final excess = (metric['excess'] as num?)?.toDouble() ?? 0;
    final ratio = ((metric['percent'] as num?)?.toDouble() ?? 0) / 100;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xfff8f9fc),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(fontSize: 12, color: AppColors.muted),
          ),
          const SizedBox(height: 4),
          Text(
            '${metric['consumed']} $unit',
            style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600),
          ),
          Text(
            target == null ? '目标待设置' : '目标 $target $unit',
            style: const TextStyle(fontSize: 11, color: AppColors.muted),
          ),
          const SizedBox(height: 6),
          if (target != null) ...[
            LinearProgressIndicator(
              value: ratio.clamp(0.0, 1.0),
              minHeight: 4,
              color: excess > 0 ? Colors.orange.shade700 : null,
            ),
            const SizedBox(height: 6),
            Text(
              excess > 0
                  ? '超出目标 $excess $unit'
                  : '距目标还差 ${metric['remaining']} $unit',
              style: const TextStyle(fontSize: 11, color: AppColors.muted),
            ),
          ],
        ],
      ),
    );
  }

  Widget analysisPage() => Column(
    children: [
      panel('动作分类与动作库', [
        const Text('按关节动作和训练部位查找，查看示范与要点。'),
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.menu_book_outlined),
          label: const Text('浏览动作分类'),
          onPressed: () => openLibrary(kind: 'exercises'),
        ),
      ]),
      panel('实时动作训练', [
        const Text('支架取景 → 侧面角度确认 → 耳机测试 → 实时姿态计次与语音提示。'),
        select('实时检测动作', liveExercise, {
          for (final e in catalog?['exercises'] ?? [])
            if (e['realtime_supported'] == true) e['id']: e['name'],
        }, (v) => liveExercise = v),
        ...[
          for (final e in catalog?['exercises'] ?? [])
            if (e['id'] == liveExercise) Text(e['view']),
        ],
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.videocam),
          label: const Text('进入实时训练'),
          onPressed: liveExercise.isEmpty
              ? null
              : () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => LiveSession(
                      exerciseId: liveExercise,
                      onFinish: (sets, minutes, captureId) => openWorkoutLog(
                        liveId: liveExercise,
                        detected: sets,
                        captureId: captureId,
                        minutes: minutes,
                      ),
                      assetBase: apiBase,
                      exerciseDetails: Map<String, dynamic>.from(
                        (catalog!['exercises'] as List).firstWhere(
                          (e) => e['id'] == liveExercise,
                        ),
                      ),
                    ),
                  ),
                ),
        ),
        const SizedBox(height: 12),
        const Text('实时姿态检测支持 Android / iOS；Web 展示拍摄引导。计次和节奏规则仍需真机与教练验证。'),
        const Text('请采取保护措施，不要为了录像尝试更大重量。'),
        action('上传训练录像', () => upload('video', exerciseId: liveExercise)),
        const Text('支持 MP4/MOV，最大100MB。'),
      ]),
      panel(
        '上传记录',
        media.isEmpty
            ? [const Text('还没有上传记录')]
            : [
                for (final m in media)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(m['kind'] == 'video' ? '训练录像' : '餐食照片'),
                    subtitle: Text(m['message']),
                  ),
              ],
      ),
    ],
  );

  Future<void> upload(String kind, {String? exerciseId}) async {
    final picked = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: kind == 'meal'
          ? ['jpg', 'jpeg', 'png']
          : ['mp4', 'mov'],
      withData: true,
    );
    if (picked == null) return;
    final file = picked.files.single;
    final limit = (kind == 'meal' ? 10 : 100) * 1024 * 1024;
    if (file.size > limit) throw Exception('文件超过大小限制');
    if (file.bytes == null) throw Exception('无法读取文件');
    final ext = file.extension?.toLowerCase();
    final mime = kind == 'meal'
        ? (ext == 'png' ? 'image/png' : 'image/jpeg')
        : (ext == 'mov' ? 'video/quicktime' : 'video/mp4');
    final req = http.MultipartRequest('POST', Uri.parse('$apiBase/api/media'))
      ..fields['kind'] = kind
      ..fields['exercise_id'] = exerciseId ?? exercise
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          file.bytes!,
          filename: file.name,
          contentType: MediaType.parse(mime),
        ),
      );
    final response = await http.Response.fromStream(
      await authSession.send(req).timeout(const Duration(minutes: 3)),
    );
    final result = jsonDecode(response.body);
    if (response.statusCode >= 400) throw Exception(result['detail']);
    await refresh();
    notify(result['message']);
  }

  static const pageTitles = [
    'AI 私教',
    '我',
    '训练计划',
    '饮食',
    'AI 陪训',
    '私教提醒',
    '训练记录与复盘',
  ];

  void navigate(int destination) {
    Navigator.of(context).pop();
    setState(() => tab = destination);
  }

  Future<void> showCoachPrompt({String? coachId}) => perform(() async {
    final result = await request(
      '/coach/prompt?coach_id=${coachId ?? coachReminders.settings.coachId}',
    );
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${result['coach']['name']} · 性格与私教提示词'),
        content: SizedBox(
          width: 640,
          child: SingleChildScrollView(child: SelectableText(result['prompt'])),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  });

  Future<void> chooseCoach() async {
    await coachReminders.initialize();
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      useSafeArea: true,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (sheetContext) => ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(sheetContext).height * .86,
        ),
        child: CoachPicker(
          selectedId: coachReminders.settings.coachId,
          onPrompt: (id) => showCoachPrompt(coachId: id),
          onSelect: (CoachPersona persona) async {
            final config = coachReminders.settings.copy();
            if (config.coachId != persona.id) {
              config.coachId = persona.id;
              config.coachName = persona.name;
            }
            await coachReminders.save(config, askPermission: false);
            String? syncError;
            try {
              await syncReminderSettings(config);
            } catch (e) {
              syncError = '已在本机切换教练；服务器同步失败，请连接后保存设置重试。';
            }
            if (sheetContext.mounted) Navigator.of(sheetContext).pop();
            if (mounted && syncError != null) notify(syncError);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(pageTitles[tab]),
      actions: [
        IconButton(
          onPressed: chooseCoach,
          tooltip: '切换桌宠教练',
          icon: const Icon(Icons.groups_outlined),
        ),
        if (tab == 2 || tab == 3 || tab == 4)
          IconButton(
            onPressed: () =>
                openLibrary(kind: tab == 3 ? 'foods' : 'exercises'),
            tooltip: tab == 3 ? '食物库' : '动作库',
            icon: Icon(tab == 3 ? Icons.restaurant_menu : Icons.fitness_center),
          ),
        IconButton(
          onPressed: busy ? null : initialize,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    drawer: Drawer(
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 24, 20, 20),
              child: Row(
                children: [
                  CoachAvatar(
                    size: 52,
                    coachId: coachReminders.settings.coachId,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          '练伴',
                          style: TextStyle(
                            fontSize: 21,
                            fontWeight: FontWeight.w700,
                            letterSpacing: -.5,
                          ),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          '${coachReminders.settings.coachName} · ${personaFor(coachReminders.settings.coachId).style}',
                          style: const TextStyle(
                            fontSize: 12,
                            color: AppColors.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            for (final item in const [
              (0, Icons.chat_bubble_outline, 'AI 私教'),
              (3, Icons.restaurant_outlined, '饮食'),
              (2, Icons.fitness_center, '训练计划'),
              (6, Icons.history, '训练记录与复盘'),
              (4, Icons.videocam_outlined, 'AI 陪训'),
              (1, Icons.person_outline, '我'),
              (5, Icons.notifications_outlined, '私教提醒'),
            ])
              ListTile(
                leading: Icon(item.$2),
                title: Text(item.$3),
                selected: tab == item.$1,
                selectedTileColor: AppColors.selected,
                onTap: () => navigate(item.$1),
              ),
            const Divider(height: 32),
            ListTile(
              leading: const Icon(Icons.manage_accounts_outlined),
              title: const Text('账号与安全'),
              onTap: () {
                Navigator.of(context).pop();
                Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => const AccountPage()),
                );
              },
            ),
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: const Text('私教提示词'),
              onTap: () {
                Navigator.of(context).pop();
                showCoachPrompt();
              },
            ),
            const SizedBox(height: 16),
          ],
        ),
      ),
    ),
    body: Column(
      children: [
        if (busy) const LinearProgressIndicator(),
        if (error != null)
          MaterialBanner(
            content: Text(error!),
            actions: [
              TextButton(
                onPressed: () => setState(() => error = null),
                child: const Text('关闭'),
              ),
            ],
          ),
        Expanded(
          child: IndexedStack(
            index: tab,
            children: [
              TickerMode(
                enabled: tab == 0,
                child: CoachChat(
                  request: (path, method, body) =>
                      request(path, method: method, body: body),
                  onProfileChanged: profileFromChat,
                  refreshToken: chatRefreshToken,
                  coachName: coachReminders.settings.coachName,
                  coachId: coachReminders.settings.coachId,
                  onChooseCoach: chooseCoach,
                  reminderText: petReminderText,
                  reminderRevision: petReminderRevision,
                ),
              ),
              for (final page in [
                profilePage,
                trainingPage,
                nutritionPage,
                analysisPage,
              ])
                SingleChildScrollView(
                  padding: const EdgeInsets.all(18),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 760),
                      child: catalog == null
                          ? const Text('连接服务中；连接失败时请启动后端并点击刷新。')
                          : page(),
                    ),
                  ),
                ),
              SingleChildScrollView(
                padding: const EdgeInsets.all(18),
                child: Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 760),
                    child: ReminderPage(
                      service: coachReminders,
                      sync: syncReminderSettings,
                      onChooseCoach: chooseCoach,
                      readSaved: () async => ReminderSettings.fromJson(
                        Map<String, dynamic>.from(
                          await request('/coach/reminders'),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
              SingleChildScrollView(
                padding: const EdgeInsets.all(18),
                child: catalog == null ? const Text('连接服务中…') : historyPage(),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}
