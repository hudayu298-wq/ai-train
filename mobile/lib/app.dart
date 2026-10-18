import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:file_picker/file_picker.dart';
import 'package:http_parser/http_parser.dart';

import 'live/live_session.dart';

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

class _HomeState extends State<Home> {
  int tab = 0;
  bool busy = false;
  String? error;
  Map<String, dynamic>? catalog;
  List<dynamic> plans = [], training = [], meals = [], media = [];
  final age = TextEditingController(text: '28');
  final height = TextEditingController(text: '175');
  final weight = TextEditingController(text: '70');
  final restrictions = TextEditingController();
  final load = TextEditingController(text: '20');
  final sets = TextEditingController(text: '3');
  final reps = TextEditingController(text: '5');
  final rpe = TextEditingController(text: '7');
  final grams = TextEditingController(text: '150');
  String sex = 'male', goal = 'muscle_gain', experience = 'beginner';
  int days = 2;
  String exercise = 'bench', food = 'rice';
  bool pain = false;

  @override
  void initState() {
    super.initState();
    initialize();
  }

  @override
  void dispose() {
    for (final c in [
      age,
      height,
      weight,
      restrictions,
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

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Map<String, dynamic>? body,
  }) async {
    final req = http.Request(method, Uri.parse('$apiBase/api$path'));
    if (body != null) {
      req.headers['Content-Type'] = 'application/json';
      req.body = jsonEncode(body);
    }
    final response = await http.Response.fromStream(
      await req.send().timeout(const Duration(seconds: 20)),
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
    catalog = Map<String, dynamic>.from(await request('/catalog'));
    final p = await request('/profile');
    if (p != null) {
      age.text = '${p['age']}';
      height.text = '${p['height_cm']}';
      weight.text = '${p['weight_kg']}';
      restrictions.text = p['restrictions'];
      sex = p['sex'];
      goal = p['goal'];
      experience = p['experience'];
      days = p['days'];
    }
    await refresh();
  });
  Future<void> refresh() async {
    final result = await Future.wait([
      request('/plans'),
      request('/training'),
      request('/meals'),
      request('/media'),
    ]);
    if (!mounted) return;
    setState(() {
      plans = result[0];
      training = result[1];
      meals = result[2];
      media = result[3];
    });
  }

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
      initialValue: value,
      decoration: InputDecoration(
        labelText: title,
        border: const OutlineInputBorder(),
      ),
      items: items.entries
          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
          .toList(),
      onChanged: busy
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
    for (final e in catalog?['exercises'] ?? []) '${e['id']}': '${e['name']}',
  };
  Widget exerciseSelect() =>
      select('动作变式', exercise, exercises, (v) => exercise = v);

  Widget overview() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Container(
        padding: const EdgeInsets.all(28),
        margin: const EdgeInsets.only(bottom: 20),
        decoration: BoxDecoration(
          color: const Color(0xff244b3c),
          borderRadius: BorderRadius.circular(24),
        ),
        child: const Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('训练有据，进步有迹。', style: TextStyle(color: Color(0xffd8ed9a))),
            SizedBox(height: 14),
            Text(
              '把目标变成\n下一次进步。',
              style: TextStyle(
                color: Colors.white,
                fontSize: 32,
                fontWeight: FontWeight.bold,
              ),
            ),
            SizedBox(height: 12),
            Text('卧推 / 深蹲 / 硬拉', style: TextStyle(color: Colors.white70)),
          ],
        ),
      ),
      panel('你的训练路线', [
        Text('训练记录 ${training.length} 条 · 饮食记录 ${meals.length} 条'),
        const SizedBox(height: 12),
        const Text('负重训练已开放；自重训练将在后续版本加入。'),
        const SizedBox(height: 12),
        const Text('本机单用户开发版。AI 识别未接入，上传不生成评分。'),
      ]),
      planPanel(),
    ],
  );
  Widget planPanel() {
    if (plans.isEmpty) return panel('当前计划', [const Text('先在画像页保存资料，再生成起始计划。')]);
    final p = plans.first;
    return panel('当前起始计划', [
      Text(p['note']),
      const SizedBox(height: 12),
      Text(
        '营养目标 ${p['nutrition']['kcal']} kcal · 蛋白质 ${p['nutrition']['protein']} g',
      ),
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
                      '${e['name']} · ${e['sets']} × ${e['reps']} · 休息 ${e['rest_seconds']} 秒',
                    ),
                ],
                Text(d['rest_note']),
                const Text('选择可控重量，保留约3次余力。'),
              ],
            ),
          ),
      ],
    ]);
  }

  Widget profilePage() => panel('认识你的起点', [
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
      '2': '2 天',
      '3': '3 天',
    }, (v) => days = int.parse(v)),
    field('伤病或训练限制（填写后需专业审核）', restrictions, numeric: false),
    action('保存画像', () async {
      await request(
        '/profile',
        method: 'PUT',
        body: {
          'age': integer(age),
          'height_cm': number(height),
          'weight_kg': number(weight),
          'sex': sex,
          'goal': goal,
          'experience': experience,
          'days': days,
          'restrictions': restrictions.text,
        },
      );
      notify('画像已保存');
    }),
    action('生成起始计划', () async {
      await request('/plans', method: 'POST');
      await refresh();
      notify('已生成起始模板');
    }),
  ]);
  Widget trainingPage() => Column(
    children: [
      planPanel(),
      panel('记录负重训练', [
        exerciseSelect(),
        field('杠铃总重量 / kg', load),
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
                    title: Text(exercises[t['exercise_id']] ?? ''),
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
      panel('记录这一餐', [
        const Text('当前食物库是开发示例数据，每100克计，尚未经专业审核。'),
        select('食物', food, {
          for (final f in catalog?['foods'] ?? []) '${f['id']}': '${f['name']}',
        }, (v) => food = v),
        field('可食重量 / g', grams),
        action('保存饮食', () async {
          await request(
            '/meals',
            method: 'POST',
            body: {'food_id': food, 'grams': number(grams)},
          );
          await refresh();
          notify('饮食已记录');
        }),
        action('上传餐食照片', () => upload('meal')),
        const Text('照片仅保存，识别尚未接入。支持 JPG/PNG，最大10MB。'),
      ]),
      panel(
        '饮食记录',
        meals.isEmpty
            ? [const Text('还没有饮食记录')]
            : [
                for (final m in meals)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('${m['name']} · ${m['grams']} g'),
                    subtitle: Text(
                      '${m['day']} · ${m['nutrients']['kcal']} kcal · 蛋白质 ${m['nutrients']['protein']} g',
                    ),
                    trailing: IconButton(
                      icon: const Icon(Icons.delete_outline),
                      onPressed: busy
                          ? null
                          : () => perform(() async {
                              await request(
                                '/meals/${m['id']}',
                                method: 'DELETE',
                              );
                              await refresh();
                            }),
                    ),
                  ),
              ],
      ),
    ],
  );
  Widget analysisPage() => Column(
    children: [
      panel('实时动作训练', [
        const Text('支架取景 → 侧面角度确认 → 耳机测试 → 实时姿态计次与语音提示。'),
        exerciseSelect(),
        ...[
          for (final e in catalog?['exercises'] ?? [])
            if (e['id'] == exercise) Text(e['view']),
        ],
        const SizedBox(height: 12),
        FilledButton.icon(
          icon: const Icon(Icons.videocam),
          label: const Text('进入实时训练'),
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => LiveSession(exerciseId: exercise),
            ),
          ),
        ),
        const SizedBox(height: 12),
        const Text('实时姿态检测支持 Android / iOS；Web 展示拍摄引导。计次和节奏规则仍需真机与教练验证。'),
        const Text('请采取保护措施，不要为了录像尝试更大重量。'),
        action('上传训练录像', () => upload('video')),
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

  Future<void> upload(String kind) async {
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
      ..fields['exercise_id'] = exercise
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

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: const Text('LiftLab · 训练有据'),
      actions: [
        IconButton(
          onPressed: busy ? null : initialize,
          icon: const Icon(Icons.refresh),
        ),
      ],
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
              : SingleChildScrollView(
                  padding: const EdgeInsets.all(18),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 760),
                      child: [
                        overview,
                        profilePage,
                        trainingPage,
                        nutritionPage,
                        analysisPage,
                      ][tab](),
                    ),
                  ),
                ),
        ),
      ],
    ),
    bottomNavigationBar: NavigationBar(
      selectedIndex: tab,
      onDestinationSelected: (v) => setState(() => tab = v),
      destinations: const [
        NavigationDestination(
          icon: Icon(Icons.dashboard_outlined),
          label: '总览',
        ),
        NavigationDestination(icon: Icon(Icons.person_outline), label: '画像'),
        NavigationDestination(icon: Icon(Icons.fitness_center), label: '训练'),
        NavigationDestination(
          icon: Icon(Icons.restaurant_outlined),
          label: '饮食',
        ),
        NavigationDestination(icon: Icon(Icons.videocam_outlined), label: '动作'),
      ],
    ),
  );
}
