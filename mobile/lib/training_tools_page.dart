import 'package:flutter/material.dart';

import 'profile_setup.dart';

class TrainingToolsPage extends StatefulWidget {
  const TrainingToolsPage({
    super.key,
    required this.request,
    this.admin = false,
  });
  final FitnessRequest request;
  final bool admin;
  @override
  State<TrainingToolsPage> createState() => _TrainingToolsPageState();
}

class _TrainingToolsPageState extends State<TrainingToolsPage> {
  Map<String, dynamic>? trends, settings, candidate;
  List<dynamic> proposals = [], exercises = [];
  int tab = 0, days = 84;
  bool busy = false, share = false;
  String? message, exercise;
  String language = 'zh';
  final name = TextEditingController(), description = TextEditingController();
  final source = TextEditingController(), review = TextEditingController();
  final barcode = TextEditingController();
  @override
  void initState() {
    super.initState();
    run(load);
  }

  @override
  void dispose() {
    for (final c in [name, description, source, review, barcode]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<dynamic> api(String p, [String m = 'GET', Object? body]) =>
      widget.request(p, m, body);
  Future<void> run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await action();
    } catch (e) {
      message = '$e'.replaceFirst('Exception: ', '');
    } finally {
      if (mounted) {
        setState(() => busy = false);
      }
    }
  }

  Future<void> load() async {
    if (tab == 0) {
      trends = Map<String, dynamic>.from(
        await api('/training-trends?days=$days'),
      );
    }
    if (tab == 1) {
      settings = Map<String, dynamic>.from(await api('/training-settings'));
    }
    if (tab == 2) {
      proposals = (await api('/catalog-content'))['items'];
      exercises = (await api('/catalog?extended=true'))['exercises'];
      exercise ??= exercises.isEmpty ? null : exercises.first['id'];
    }
  }

  Widget field(String label, TextEditingController c) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 7),
    child: TextField(
      controller: c,
      enabled: !busy,
      decoration: InputDecoration(labelText: label),
    ),
  );
  Widget bars(String title, List rows, String label) {
    final max = rows.fold<num>(
      1,
      (a, r) => r['working_sets'] > a ? r['working_sets'] : a,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        for (final row in rows)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  '${row[label] == 'unlinked' ? '未关联计划' : row[label]} · ${row['working_sets']}工作组',
                ),
                LinearProgressIndicator(value: row['working_sets'] / max),
              ],
            ),
          ),
      ],
    );
  }

  Widget trendBody() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      DropdownButtonFormField<int>(
        initialValue: days,
        decoration: const InputDecoration(labelText: '统计范围'),
        items: [
          for (final d in [28, 84, 180, 365])
            DropdownMenuItem(value: d, child: Text('近$d天')),
        ],
        onChanged: busy
            ? null
            : (v) {
                days = v!;
                run(load);
              },
      ),
      if (trends != null) ...[
        Text('${trends!['from']} 至 ${trends!['through']}'),
        bars('每周记录趋势', trends!['weeks'], 'key'),
        bars('按训练周期', trends!['cycles'], 'key'),
        bars('主要肌群归属', trends!['muscles'], 'name'),
        Text(trends!['note']),
      ],
    ],
  );
  Widget rulesBody() {
    if (settings == null) {
      return const SizedBox();
    }
    final s = settings!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        const Text('这些设置只收紧原有练伴策略；疼痛、恢复不足、器械和有效RM检查不能关闭。修改设置不会直接改训练计划。'),
        SwitchListTile(
          title: const Text('允许训练后自动进阶评估'),
          value: s['enabled'],
          onChanged: busy ? null : (v) => setState(() => s['enabled'] = v),
        ),
        DropdownButtonFormField<String>(
          initialValue: s['mode'],
          decoration: const InputDecoration(labelText: '允许的加量方式'),
          items: const [
            DropdownMenuItem(value: 'either', child: Text('重量或次数（每次只变一项）')),
            DropdownMenuItem(value: 'weight', child: Text('只允许增加重量')),
            DropdownMenuItem(value: 'reps', child: Text('只允许增加次数')),
          ],
          onChanged: busy ? null : (v) => setState(() => s['mode'] = v),
        ),
        Text('至少${s['min_sessions']}次不同日期的可比较完成记录'),
        Slider(
          value: (s['min_sessions'] as num).toDouble(),
          min: 2,
          max: 6,
          divisions: 4,
          onChanged: busy
              ? null
              : (v) => setState(() => s['min_sessions'] = v.round()),
        ),
        Text('加量评估RPE上限 ${s['rpe_ceiling']}'),
        Slider(
          value: (s['rpe_ceiling'] as num).toDouble(),
          min: 5,
          max: 8,
          divisions: 6,
          onChanged: busy ? null : (v) => setState(() => s['rpe_ceiling'] = v),
        ),
        Text(
          '单次加重上限 ${((s['max_weight_increase_fraction'] as num) * 100).toStringAsFixed(0)}%',
        ),
        Slider(
          value: (s['max_weight_increase_fraction'] as num).toDouble(),
          min: 0,
          max: .05,
          divisions: 5,
          onChanged: busy
              ? null
              : (v) => setState(() => s['max_weight_increase_fraction'] = v),
        ),
        SwitchListTile(
          title: const Text('允许每次最多调整1次重复'),
          value: s['max_rep_change'] == 1,
          onChanged: busy
              ? null
              : (v) => setState(() => s['max_rep_change'] = v ? 1 : 0),
        ),
        FilledButton(
          onPressed: busy
              ? null
              : () => run(() async {
                  await api('/training-settings', 'PUT', s);
                  message = '进阶设置已保存';
                }),
          child: const Text('保存进阶设置'),
        ),
      ],
    );
  }

  Widget contentBody() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text('提交的是公开动作译名/教学描述。管理员审核后显示，不会变成已审核科学知识，也不改变动作身份、器械或重量。'),
      DropdownButtonFormField<String>(
        initialValue: exercise,
        isExpanded: true,
        decoration: const InputDecoration(labelText: '动作'),
        items: [
          for (final e in exercises)
            DropdownMenuItem<String>(
              value: e['id'],
              child: Text(e['name'], overflow: TextOverflow.ellipsis),
            ),
        ],
        onChanged: busy ? null : (v) => setState(() => exercise = v),
      ),
      DropdownButtonFormField<String>(
        initialValue: language,
        decoration: const InputDecoration(labelText: '译文语言'),
        items: const [
          DropdownMenuItem(value: 'zh', child: Text('中文')),
          DropdownMenuItem(value: 'en', child: Text('英文')),
        ],
        onChanged: busy ? null : (v) => setState(() => language = v!),
      ),
      field('动作译名', name),
      field('教学描述（可选）', description),
      field('来源及翻译说明（至少5字）', source),
      CheckboxListTile(
        title: const Text('同意将本次译文作为公开资料提交审核'),
        value: share,
        onChanged: busy ? null : (v) => setState(() => share = v == true),
      ),
      FilledButton(
        onPressed: busy || !share || exercise == null
            ? null
            : () => run(() async {
                await api('/catalog-content', 'POST', {
                  'exercise_id': exercise,
                  'language': language,
                  'name': name.text,
                  'description': description.text,
                  'source_note': source.text,
                  'share_publicly': true,
                });
                await load();
                message = '已提交译文，待审核';
              }),
        child: const Text('提交公开译文'),
      ),
      if (widget.admin) field('审核理由（至少5字）', review),
      for (final p in proposals)
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('${p['language']} · ${p['name']} · ${p['status']}'),
                Text(p['description']),
                Text(p['source_note']),
                if (widget.admin && p['status'] == 'pending')
                  Wrap(
                    children: [
                      for (final approved in [true, false])
                        TextButton(
                          onPressed: busy
                              ? null
                              : () => run(() async {
                                  await api(
                                    '/catalog-content/${p['id']}/review',
                                    'POST',
                                    {
                                      'approved': approved,
                                      'notes': review.text,
                                    },
                                  );
                                  await load();
                                }),
                          child: Text(approved ? '审核通过并发布译文' : '驳回'),
                        ),
                    ],
                  ),
                if (widget.admin && p['status'] == 'approved')
                  TextButton(
                    onPressed: busy
                        ? null
                        : () => run(() async {
                            await api(
                              '/catalog-content/${p['id']}/withdraw',
                              'POST',
                              {},
                            );
                            await load();
                          }),
                    child: const Text('撤回此译文版本'),
                  ),
              ],
            ),
          ),
        ),
    ],
  );
  Widget foodBody() => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      const Text(
        'Open Food Facts 包装食品查询。只接入明确每100克、营养字段完整的数据；查询不代表已进食。社区数据需要对照包装核实。来源数据遵循ODbL / DbCL，未导入商品图片。',
      ),
      field('商品条码（8–14位数字）', barcode),
      FilledButton(
        onPressed: busy
            ? null
            : () => run(() async {
                candidate = null;
                candidate = Map<String, dynamic>.from(
                  await api('/external-foods/${barcode.text.trim()}'),
                );
              }),
        child: const Text('按条码查询'),
      ),
      if (candidate != null) ...[
        Text(
          candidate!['food']['name'],
          style: Theme.of(context).textTheme.titleLarge,
        ),
        Text(
          '每100克：${candidate!['food']['kcal']} kcal · 蛋白质${candidate!['food']['protein']}g · 脂肪${candidate!['food']['fat']}g · 碳水${candidate!['food']['carbs']}g',
        ),
        Text(candidate!['food']['source_url']),
        Text('查询时间：${candidate!['fetched_at']}'),
        OutlinedButton(
          onPressed: busy
              ? null
              : () => run(() async {
                  final result = await api(
                    '/external-foods/${candidate!['food']['barcode']}/confirm',
                    'POST',
                    {'confirmed': true},
                  );
                  message = result['message'];
                }),
          child: const Text('核对包装后保存到本人食物库'),
        ),
      ],
    ],
  );
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('训练工具与资料')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Wrap(
          spacing: 8,
          children: [
            for (var i = 0; i < 4; i++)
              ChoiceChip(
                label: Text(['趋势统计', '进阶设置', '译文审核', '外部食品'][i]),
                selected: tab == i,
                onSelected: busy
                    ? null
                    : (_) {
                        setState(() => tab = i);
                        run(load);
                      },
              ),
          ],
        ),
        if (busy) const LinearProgressIndicator(),
        if (message != null) Text(message!),
        const SizedBox(height: 16),
        if (tab == 0) trendBody(),
        if (tab == 1) rulesBody(),
        if (tab == 2) contentBody(),
        if (tab == 3) foodBody(),
      ],
    ),
  );
}
