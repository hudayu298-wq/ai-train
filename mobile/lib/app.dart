import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'package:http_parser/http_parser.dart';

import 'live/live_session.dart';
import 'user_plan_editor.dart';
import 'library_page.dart';
import 'coach_chat.dart';

const apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://127.0.0.1:8000',
);

class LiftLab extends StatelessWidget {
  const LiftLab({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'LiftLab',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xff244b3c)),
      scaffoldBackgroundColor: const Color(0xfff5f5ef),
      useMaterial3: true,
    ),
    home: const Home(),
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
  Map<String, dynamic>? nutrition;
  Map<String, dynamic>? coachProfile;
  int chatRefreshToken = 0;
  Timer? nutritionTimer;
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
    nutritionTimer = Timer.periodic(const Duration(minutes: 1), (_) {
      if (!busy && catalog != null) unawaited(refreshNutrition());
    });
    initialize();
  }

  @override
  void dispose() {
    nutritionTimer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
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
          await req.send().timeout(
            Duration(
              seconds:
                  path == '/plans/generate' ||
                      path == '/movement/analyze' ||
                      path == '/coach/messages'
                  ? 110
                  : 20,
            ),
          ),
        ).timeout(
          Duration(
            seconds:
                path == '/plans/generate' ||
                    path == '/movement/analyze' ||
                    path == '/coach/messages'
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
    catalog = Map<String, dynamic>.from(
      await request('/catalog?extended=true'),
    );
    normalizeSelections();
    await loadCoachProfile();
    chatRefreshToken++;
    await refresh();
  });

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
    ]);
    if (!mounted) return;
    setState(() {
      plans = result[0];
      training = result[1];
      nutrition = Map<String, dynamic>.from(result[2]);
      meals = nutrition!['records'];
      media = result[3];
      rmRecords = result[4];
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

  void openLibrary({String initialKind = 'foods'}) =>
      Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => LibraryPage(
            assetBase: apiBase,
            initialKind: initialKind,
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
    margin: const EdgeInsets.only(bottom: 18),
    child: Padding(
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 14),
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
      if (p['source'] == 'ai') ...[
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
                  d['name'],
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
            '${item['day']} · ${exercises[item['exercise_id']]}：${item['load_percent'] == null ? '暂无RM评估' : '${item['load_percent']}% 1RM参考'}\n${item['message']}',
          ),
        ),
    ]);
  }

  Widget profilePage() => panel('我的用户画像', [
    const Text('对话中明确提供的信息会自动记录在这里，也可以手动修改。'),
    if (coachProfile != null) ...[
      const SizedBox(height: 12),
      Text(
        coachProfile!['complete'] == true
            ? '基础画像已完整，可用于训练计划和饮食目标。'
            : '待补充：${(coachProfile!['missing_fields'] as List).map((k) => coachProfile!['labels'][k]).join('、')}',
      ),
      const SizedBox(height: 12),
      for (final e in (coachProfile!['facts'] as Map).entries)
        Text(
          '${coachProfile!['labels'][e.key]}：${CoachChat.displayValue(e.value)}',
        ),
      const Divider(height: 28),
    ],
    field('年龄（18岁及以上）', age),
    field('身高 / cm', height),
    field('体重 / kg', weight),
    select('用于代谢估算的性别', sex, {'male': '男性', 'female': '女性'}, (v) => sex = v),
    select('目标', goal, {
      'muscle_gain': '基础增肌',
      'fat_loss': '减脂',
    }, (v) => goal = v),
    select('经验', experience, {
      'beginner': '新手',
      'intermediate': '有训练经验',
    }, (v) => experience = v),
    select('每周训练天数', '$days', {
      '1': '1 天',
      '2': '2 天',
      '3': '3 天',
      '4': '4 天',
      '5': '5 天',
      '6': '6 天',
      '7': '7 天',
    }, (v) => days = int.parse(v)),
    field('伤病或训练限制（用于评估提示）', restrictions, numeric: false),
    field('饮食偏好', dietaryPreferences, numeric: false),
    field('可用器械', equipment, numeric: false),
    field('训练偏好', trainingPreferences, numeric: false),
    field('时间安排', schedule, numeric: false),
    action('保存画像', () async {
      await request(
        '/coach/profile',
        method: 'PATCH',
        body: {
          if (age.text.trim().isNotEmpty) 'age': integer(age),
          if (height.text.trim().isNotEmpty) 'height_cm': number(height),
          if (weight.text.trim().isNotEmpty) 'weight_kg': number(weight),
          if (sex.isNotEmpty) 'sex': sex,
          if (goal.isNotEmpty) 'goal': goal,
          if (experience.isNotEmpty) 'experience': experience,
          if (days > 0) 'days': days,
          'restrictions': restrictions.text,
          'dietary_preferences': dietaryPreferences.text,
          'equipment': equipment.text,
          'training_preferences': trainingPreferences.text,
          'schedule': schedule.text,
        },
      );
      notify('画像已保存');
      await loadCoachProfile();
      await refresh();
    }),
  ]);
  Widget trainingPage() => Column(
    children: [
      planPanel(),
      UserPlanEditor(
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
      panel('记录负重训练', [
        exerciseSelect(),
        for (final e in catalog?['exercises'] ?? [])
          if (e['id'] == exercise) Text(e['weight_basis']),
        field('负重 / kg（按动作库口径）', load),
        field('组数', sets),
        field('每组次数', reps),
        field('主观用力程度 / RPE 1–10', rpe),
        CheckboxListTile(
          value: pain,
          title: const Text('出现疼痛或不适'),
          onChanged: (v) => setState(() => pain = v ?? false),
        ),
        action('保存训练', () async {
          final result = await request(
            '/training',
            method: 'POST',
            body: {
              'exercise_id': exercise,
              'weight_kg': number(load),
              'sets': integer(sets),
              'reps': integer(reps),
              'rpe': number(rpe),
              'pain': pain,
            },
          );
          await refresh();
          notify(result['feedback']);
        }),
      ]),
      panel(
        '训练历史',
        training.isEmpty
            ? [const Text('还没有训练记录')]
            : [
                for (final t in training)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(
                      t['name'] ??
                          exercises[t['exercise_id']] ??
                          t['exercise_id'],
                    ),
                    subtitle: Text(
                      '${t['day']} · ${t['weight_kg']} kg · ${t['sets']} × ${t['reps']}\n${t['feedback']}',
                    ),
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
        for (final entry in {
          'kcal': '热量',
          'protein': '蛋白质',
          'fat': '脂肪',
          'carbs': '碳水',
        }.entries)
          nutrientProgress(entry.key, entry.value),
      ]),
      panel('记录当天这一餐', [
        const Text('营养按每100克可食部分计算，请核对生熟状态与来源。品牌食品可按包装标签新增。'),
        OutlinedButton.icon(
          onPressed: openLibrary,
          icon: const Icon(Icons.search),
          label: const Text('搜索食物 / 管理资料库'),
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
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$label：已摄入 ${metric['consumed']} $unit / ${target == null ? '目标未设置' : '目标 $target $unit'}',
          ),
          const SizedBox(height: 6),
          if (target != null) ...[
            LinearProgressIndicator(
              value: ratio.clamp(0.0, 1.0),
              minHeight: 8,
              color: excess > 0 ? Colors.orange.shade700 : null,
            ),
            const SizedBox(height: 6),
            Text(
              excess > 0
                  ? '超出目标 $excess $unit'
                  : '距目标还差 ${metric['remaining']} $unit',
            ),
          ],
        ],
      ),
    );
  }

  Widget analysisPage() => Column(
    children: [
      panel('动作分类与动作库', [
        const Text('按关节动作分类浏览动作，筛选训练部位，并查看动图、准备步骤和动作要点。'),
        const SizedBox(height: 8),
        const Text('分类包括水平推、水平拉、蹲、髋铰链、肘屈曲等；也可区分负重与自重训练。'),
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.menu_book_outlined),
          label: const Text('按关节动作浏览动作库'),
          onPressed: () => openLibrary(initialKind: 'exercises'),
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
      await req.send().timeout(const Duration(minutes: 3)),
    );
    final result = jsonDecode(response.body);
    if (response.statusCode >= 400) throw Exception(result['detail']);
    await refresh();
    notify(result['message']);
  }

  static const pageTitles = ['AI 私教', '我', '训练计划', '饮食', 'AI 陪训'];

  void navigate(int destination) {
    Navigator.of(context).pop();
    setState(() => tab = destination);
  }

  Future<void> showCoachPrompt() => perform(() async {
    final result = await request('/coach/prompt');
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('AI 私教提示词'),
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

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(pageTitles[tab]),
      actions: [
        if (tab != 0)
          IconButton(
            onPressed: () => openLibrary(
              initialKind: tab == 2 || tab == 4 ? 'exercises' : 'foods',
            ),
            tooltip: '食物与动作库',
            icon: const Icon(Icons.menu_book_outlined),
          ),
        IconButton(
          onPressed: busy ? null : initialize,
          icon: const Icon(Icons.refresh),
        ),
      ],
    ),
    drawer: Drawer(
      child: SafeArea(
        child: Column(
          children: [
            const Padding(
              padding: EdgeInsets.fromLTRB(24, 28, 24, 24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.spa_outlined, color: Color(0xff244b3c), size: 32),
                  SizedBox(height: 12),
                  Text(
                    'LiftLab',
                    style: TextStyle(fontSize: 25, fontWeight: FontWeight.bold),
                  ),
                  Text('你的 AI 私教', style: TextStyle(color: Color(0xff537164))),
                ],
              ),
            ),
            for (final item in const [
              (0, Icons.chat_bubble_outline, 'AI 私教'),
              (3, Icons.restaurant_outlined, '饮食'),
              (2, Icons.fitness_center, '训练计划'),
              (4, Icons.videocam_outlined, 'AI 陪训'),
              (1, Icons.person_outline, '我'),
            ])
              ListTile(
                leading: Icon(item.$2),
                title: Text(item.$3),
                selected: tab == item.$1,
                selectedTileColor: const Color(0xffe3ebdf),
                onTap: () => navigate(item.$1),
              ),
            const Spacer(),
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
          child: catalog == null
              ? const Center(child: Text('连接服务中；连接失败时请启动后端并点击刷新。'))
              : IndexedStack(
                  index: tab,
                  children: [
                    CoachChat(
                      request: (path, method, body) =>
                          request(path, method: method, body: body),
                      onProfileChanged: profileFromChat,
                      refreshToken: chatRefreshToken,
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
                            child: page(),
                          ),
                        ),
                      ),
                  ],
                ),
        ),
      ],
    ),
  );
}
