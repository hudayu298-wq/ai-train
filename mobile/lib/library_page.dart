import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:file_picker/file_picker.dart';

import 'exercise_reference.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({
    super.key,
    required this.request,
    required this.onChanged,
    this.onSelect,
    this.assetBase = 'http://127.0.0.1:8000',
  });
  final Future<dynamic> Function(String, String, Object?) request;
  final Future<void> Function() onChanged;
  final void Function(String, Map<String, dynamic>)? onSelect;
  final String assetBase;
  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  String kind = 'foods',
      category = '',
      type = '',
      bodyPart = '',
      cameraView = 'unknown';
  final query = TextEditingController();
  List<dynamic> entries = [], categories = [];
  List<dynamic> bodyParts = [];
  final Map<String, dynamic> analyses = {};
  int total = 0;
  bool busy = false;
  String? message;
  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void dispose() {
    query.dispose();
    super.dispose();
  }

  static List<String> lines(String value) => value
      .split('\n')
      .map((v) => v.trim())
      .where((v) => v.isNotEmpty)
      .toList();
  static String initialText(Map<String, dynamic>? item, String key) {
    final value = ['setup', 'execution', 'key_points', 'cautions'].contains(key)
        ? item?['technique']?[key]
        : item?[key];
    return value is List ? value.join('\n') : '${value ?? ''}';
  }

  Future<void> analyzeFrames(Map<String, dynamic> entry) async {
    if (busy) return;
    try {
      final picked = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['jpg', 'jpeg', 'png'],
        allowMultiple: true,
        withData: true,
      );
      if (picked == null) return;
      if (picked.files.length < 2 || picked.files.length > 6) {
        throw Exception('请选择同一动作的2–6张训练截图');
      }
      final frames = <Map<String, dynamic>>[];
      for (final file in picked.files) {
        if (file.bytes == null || file.size > 2 * 1024 * 1024) {
          throw Exception('每张截图需为JPG/PNG且不超过2MB');
        }
        frames.add({
          'mime_type': file.extension?.toLowerCase() == 'png'
              ? 'image/png'
              : 'image/jpeg',
          'image_base64': base64Encode(file.bytes!),
        });
      }
      if (!mounted) return;
      setState(() {
        busy = true;
        message = '正在分析选取截图；仅检查可见问题，结果供复核';
      });
      final result = await widget.request('/movement/analyze', 'POST', {
        'exercise_id': entry['id'],
        'camera_view': cameraView,
        'frames': frames,
      });
      if (mounted) {
        setState(() {
          analyses[entry['id']] = result;
          message = '截图分析完成（实验功能）';
        });
      }
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> load({bool more = false}) async {
    if (busy) return;
    bool refetch = false;
    setState(() {
      busy = true;
      message = null;
    });
    try {
      final parameters = Uri(
        queryParameters: {
          'q': query.text,
          'category': category,
          'type': type,
          'body_part': bodyPart,
          'limit': '50',
          'offset': more ? '${entries.length}' : '0',
        },
      ).query;
      final result = await widget.request(
        '/library/$kind?$parameters',
        'GET',
        null,
      );
      if (mounted) {
        setState(() {
          entries = more ? [...entries, ...result['items']] : result['items'];
          categories = result['categories'];
          bodyParts = result['body_parts'] ?? [];
          if (category.isNotEmpty && !categories.contains(category)) {
            category = '';
            refetch = true;
          }
          if (bodyPart.isNotEmpty && !bodyParts.contains(bodyPart)) {
            bodyPart = '';
            refetch = true;
          }
          total = result['total'];
        });
      }
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
    if (refetch && mounted) {
      await load();
    }
  }

  Future<void> edit([Map<String, dynamic>? item]) async {
    final food = kind == 'foods';
    final fields = food
        ? {
            'name': '食物名称',
            'category': '分类',
            'kcal': '热量 / kcal',
            'protein': '蛋白质 / g',
            'fat': '脂肪 / g',
            'carbs': '碳水 / g',
            'source_label': '来源（包装标签或资料名称）',
            'notes': '备注',
          }
        : {
            'name': '动作名称（注明变式）',
            'category': '默认训练部位',
            'movement_pattern': '关节动作模式（如水平推）',
            'joint_actions': '关节动作（每行一项）',
            'body_regions': '训练部位（每行一项）',
            'primary_muscles': '主要肌群（每行一项）',
            'secondary_muscles': '辅助肌群（每行一项）',
            'setup': '准备姿势（每行一项）',
            'execution': '执行步骤（每行一项）',
            'key_points': '变式细节（每行一项）',
            'cautions': '注意事项（每行一项）',
            'equipment': '器械',
            'summary': '动作说明',
            'weight_basis': '重量记录口径',
            'source_label': '内容来源',
          };
    final controllers = {
      for (final key in fields.keys)
        key: TextEditingController(text: initialText(item, key)),
    };
    String state = item?['state'] ?? 'prepared',
        exerciseType = item?['type'] ?? 'weighted';
    bool saving = false;
    String? error;
    final dialog = DialogRoute<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => StatefulBuilder(
        builder: (context, change) => AlertDialog(
          title: Text('${item == null ? '新增' : '编辑'}${food ? '食物' : '动作'}'),
          content: SizedBox(
            width: 480,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    food
                        ? '营养均按每100克可食部分填写。标签若按每份或每100毫升，需先换算为每100克。'
                        : '新动作支持资料与记录；不会自动获得实时检测能力。不同器械与变式分别建条目。',
                  ),
                  for (final field in fields.entries)
                    Padding(
                      padding: const EdgeInsets.only(top: 10),
                      child: TextField(
                        controller: controllers[field.key],
                        maxLines:
                            [
                              'joint_actions',
                              'body_regions',
                              'primary_muscles',
                              'secondary_muscles',
                              'setup',
                              'execution',
                              'key_points',
                              'cautions',
                            ].contains(field.key)
                            ? 3
                            : 1,
                        enabled:
                            !saving &&
                            !(item?['realtime_supported'] == true &&
                                [
                                  'name',
                                  'category',
                                  'equipment',
                                  'weight_basis',
                                ].contains(field.key)),
                        keyboardType:
                            [
                              'kcal',
                              'protein',
                              'fat',
                              'carbs',
                            ].contains(field.key)
                            ? const TextInputType.numberWithOptions(
                                decimal: true,
                              )
                            : TextInputType.text,
                        decoration: InputDecoration(
                          labelText: field.value,
                          border: const OutlineInputBorder(),
                        ),
                      ),
                    ),
                  DropdownButtonFormField<String>(
                    initialValue: food ? state : exerciseType,
                    decoration: InputDecoration(
                      labelText: food ? '食物状态' : '训练类型',
                    ),
                    items:
                        (food
                                ? {
                                    'raw': '生 / 干原料',
                                    'cooked': '熟食',
                                    'prepared': '成品 / 加工食品',
                                  }
                                : {'weighted': '负重训练', 'bodyweight': '自重资料'})
                            .entries
                            .map(
                              (e) => DropdownMenuItem(
                                value: e.key,
                                child: Text(e.value),
                              ),
                            )
                            .toList(),
                    onChanged: saving || (!food && item != null)
                        ? null
                        : (v) => change(() {
                            if (food) {
                              state = v!;
                            } else {
                              exerciseType = v!;
                            }
                          }),
                  ),
                  if (error != null)
                    Text(
                      error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  if (saving) const LinearProgressIndicator(),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: saving
                  ? null
                  : () async {
                      change(() {
                        saving = true;
                        error = null;
                      });
                      try {
                        final payload = <String, dynamic>{
                          for (final key in fields.keys)
                            key: controllers[key]!.text.trim(),
                        };
                        if (food) {
                          for (final key in [
                            'kcal',
                            'protein',
                            'fat',
                            'carbs',
                          ]) {
                            final n = double.tryParse(controllers[key]!.text);
                            if (n == null || !n.isFinite) {
                              throw Exception('营养字段需填写有效数字');
                            }
                            payload[key] = n;
                          }
                          payload['state'] = state;
                        } else {
                          payload['type'] = exerciseType;
                          for (final key in [
                            'joint_actions',
                            'body_regions',
                            'primary_muscles',
                            'secondary_muscles',
                          ]) {
                            payload[key] = lines(controllers[key]!.text);
                          }
                          final technique = item?['technique'] is Map
                              ? Map<String, dynamic>.from(item!['technique'])
                              : <String, dynamic>{};
                          for (final key in [
                            'setup',
                            'execution',
                            'key_points',
                            'cautions',
                          ]) {
                            technique[key] = lines(controllers[key]!.text);
                            payload.remove(key);
                          }
                          payload['technique'] = technique;
                        }
                        if (item != null) {
                          for (final key in ['aliases', 'difficulty', 'view']) {
                            if (item.containsKey(key)) payload[key] = item[key];
                          }
                        }
                        await widget.request(
                          '/library/$kind${item == null ? '' : '/${item['id']}'}',
                          item == null ? 'POST' : 'PUT',
                          payload,
                        );
                        if (context.mounted) Navigator.pop(context, true);
                      } catch (e) {
                        if (context.mounted) {
                          change(() {
                            saving = false;
                            error = '$e';
                          });
                        }
                      }
                    },
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );
    final saved = await Navigator.of(context, rootNavigator: true).push(dialog);
    await dialog.completed;
    for (final c in controllers.values) {
      c.dispose();
    }
    if (saved == true) {
      await widget.onChanged();
      await load();
    }
  }

  Future<void> archive(Map<String, dynamic> item) async {
    final yes = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('停用条目'),
        content: Text('停用“${item['name']}”后不能用于新的记录，历史记录仍保留。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('停用'),
          ),
        ],
      ),
    );
    if (yes != true) return;
    try {
      await widget.request('/library/$kind/${item['id']}', 'DELETE', null);
      await widget.onChanged();
      await load();
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    }
  }

  Future<void> importJson() async {
    final input = TextEditingController();
    final dialog = DialogRoute<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('批量导入 JSON'),
        content: SizedBox(
          width: 480,
          child: TextField(
            controller: input,
            minLines: 5,
            maxLines: 12,
            decoration: const InputDecoration(
              hintText: '粘贴条目数组或导出的完整JSON；已有ID不会覆盖。',
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, input.text),
            child: const Text('导入'),
          ),
        ],
      ),
    );
    final text = await Navigator.of(context, rootNavigator: true).push(dialog);
    await dialog.completed;
    input.dispose();
    if (text == null) return;
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map && decoded['kind'] != kind) {
        throw Exception('文件类型与当前库不一致');
      }
      final items = decoded is List ? decoded : decoded['items'];
      final result = await widget.request(
        '/library/$kind/import',
        'POST',
        items,
      );
      await widget.onChanged();
      await load();
      if (mounted) setState(() => message = '已导入${result['imported']}条');
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('食物与动作库')),
    body: SingleChildScrollView(
      padding: const EdgeInsets.all(18),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 760),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(
                    value: 'foods',
                    label: Text('食物库'),
                    icon: Icon(Icons.restaurant),
                  ),
                  ButtonSegment(
                    value: 'exercises',
                    label: Text('动作库'),
                    icon: Icon(Icons.fitness_center),
                  ),
                ],
                selected: {kind},
                onSelectionChanged: busy
                    ? null
                    : (values) {
                        setState(() {
                          kind = values.first;
                          category = '';
                          type = '';
                          bodyPart = '';
                          entries = [];
                          categories = [];
                          bodyParts = [];
                          query.clear();
                        });
                        load();
                      },
              ),
              const SizedBox(height: 12),
              Text(
                kind == 'foods'
                    ? '按食物类型分类，营养为每100克可食部分；请核对生熟状态、来源和实际品牌。'
                    : '按关节动作模式分类，并标明训练部位。新增动作不自动获得实时检测能力；动图为二维示意。',
              ),
              TextField(
                controller: query,
                onSubmitted: (_) => load(),
                decoration: InputDecoration(
                  labelText: kind == 'foods' ? '搜索食物' : '搜索动作或器械',
                  suffixIcon: IconButton(
                    onPressed: busy ? null : () => load(),
                    icon: const Icon(Icons.search),
                  ),
                ),
              ),
              DropdownButtonFormField<String>(
                key: ValueKey('$kind-$category-${categories.length}'),
                initialValue: category,
                decoration: InputDecoration(
                  labelText: kind == 'foods' ? '食物类型' : '关节动作分类',
                ),
                items: [
                  const DropdownMenuItem(value: '', child: Text('全部分类')),
                  for (final c in categories)
                    DropdownMenuItem(value: c, child: Text(c)),
                ],
                onChanged: busy
                    ? null
                    : (v) {
                        setState(() => category = v!);
                        load();
                      },
              ),
              if (kind == 'exercises')
                DropdownButtonFormField<String>(
                  key: ValueKey('body-$bodyPart-${bodyParts.length}'),
                  initialValue: bodyPart,
                  decoration: const InputDecoration(labelText: '训练部位'),
                  items: [
                    const DropdownMenuItem(value: '', child: Text('全部部位')),
                    for (final part in bodyParts)
                      DropdownMenuItem(value: part, child: Text(part)),
                  ],
                  onChanged: busy
                      ? null
                      : (v) {
                          setState(() => bodyPart = v!);
                          load();
                        },
                ),
              if (kind == 'exercises')
                DropdownButtonFormField<String>(
                  key: ValueKey(type),
                  initialValue: type,
                  decoration: const InputDecoration(labelText: '训练类型'),
                  items: const [
                    DropdownMenuItem(value: '', child: Text('全部')),
                    DropdownMenuItem(value: 'weighted', child: Text('负重训练')),
                    DropdownMenuItem(value: 'bodyweight', child: Text('自重资料')),
                  ],
                  onChanged: busy
                      ? null
                      : (v) {
                          setState(() => type = v!);
                          load();
                        },
                ),
              Wrap(
                spacing: 8,
                children: [
                  FilledButton.icon(
                    onPressed: busy ? null : () => edit(),
                    icon: const Icon(Icons.add),
                    label: const Text('新增'),
                  ),
                  TextButton(
                    onPressed: busy ? null : importJson,
                    child: const Text('导入 JSON'),
                  ),
                  TextButton(
                    onPressed: busy
                        ? null
                        : () async {
                            try {
                              final result = await widget.request(
                                '/library/$kind/export',
                                'GET',
                                null,
                              );
                              await Clipboard.setData(
                                ClipboardData(
                                  text: const JsonEncoder.withIndent('  ')
                                      .convert(result),
                                ),
                              );
                              if (mounted) {
                                setState(() => message = '完整库JSON已复制，可粘贴保存到文件');
                              }
                            } catch (e) {
                              if (mounted) setState(() => message = '$e');
                            }
                          },
                    child: const Text('复制导出 JSON'),
                  ),
                ],
              ),
              if (busy) const LinearProgressIndicator(),
              if (message != null) Text(message!),
              Text('共$total条 · 已显示${entries.length}条'),
              for (final raw in entries) ...[
                Builder(
                  builder: (context) {
                    final e = Map<String, dynamic>.from(raw);
                    return Card(
                      child: ExpansionTile(
                        title: Text(e['name']),
                        subtitle: Text(
                          kind == 'foods'
                              ? '${e['category']} · ${e['kcal']} kcal / 100g'
                              : '${e['movement_pattern']} · ${(e['body_regions'] as List? ?? []).join(' / ')} · ${e['equipment']}',
                        ),
                        children: [
                          Padding(
                            padding: const EdgeInsets.all(16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                if (kind == 'foods') ...[
                                  Text(
                                    '状态：${{'raw': '生/干原料', 'cooked': '熟食', 'prepared': '成品/加工'}[e['state']]}',
                                  ),
                                  Text(
                                    '蛋白质 ${e['protein']}g · 脂肪 ${e['fat']}g · 碳水 ${e['carbs']}g / 100g',
                                  ),
                                  Text(e['notes'] ?? ''),
                                  if (e['original_name'] != null)
                                    Text('原始名称：${e['original_name']}'),
                                ] else ...[
                                  ExerciseReference(
                                    exercise: e,
                                    assetBase: widget.assetBase,
                                  ),
                                  Text(e['summary'] ?? ''),
                                  Text('重量口径：${e['weight_basis']}'),
                                  Text(
                                    e['realtime_supported'] == true
                                        ? '支持实验性实时检测'
                                        : '暂无实时检测',
                                  ),
                                  Text(e['view'] ?? ''),
                                  const SizedBox(height: 12),
                                  const Text(
                                    '实验性截图观察：选取同一动作的2–6张JPG/PNG（每张≤2MB）。图片会发送到后端及已配置的视觉模型；不能代替连续录像或实时纠错。',
                                  ),
                                  DropdownButtonFormField<String>(
                                    initialValue: cameraView,
                                    decoration: const InputDecoration(
                                      labelText: '截图拍摄角度',
                                    ),
                                    items: const [
                                      DropdownMenuItem(
                                        value: 'unknown',
                                        child: Text('未确认'),
                                      ),
                                      DropdownMenuItem(
                                        value: 'side',
                                        child: Text('正侧面'),
                                      ),
                                      DropdownMenuItem(
                                        value: 'front',
                                        child: Text('正面'),
                                      ),
                                      DropdownMenuItem(
                                        value: 'oblique',
                                        child: Text('斜侧面'),
                                      ),
                                    ],
                                    onChanged: busy
                                        ? null
                                        : (v) =>
                                              setState(() => cameraView = v!),
                                  ),
                                  OutlinedButton.icon(
                                    onPressed: busy
                                        ? null
                                        : () => analyzeFrames(e),
                                    icon: const Icon(Icons.image_search),
                                    label: const Text('上传训练截图进行 AI 观察'),
                                  ),
                                  if (analyses.containsKey(e['id'])) ...[
                                    Text(analyses[e['id']]['summary']),
                                    for (final observation
                                        in analyses[e['id']]['observations'])
                                      Text(
                                        '疑似观察：${observation['evidence']}\n复核要点：${observation['check_point']}\n建议：${observation['guidance']}\n截图索引：${observation['frame_indices']}',
                                      ),
                                    Text(
                                      '参考版本：${analyses[e['id']]['content_version']}',
                                    ),
                                  ],
                                ],
                                Text('来源：${e['source_label']}'),
                                Text(
                                  '状态：${e['review_status'] == 'source_imported'
                                      ? '官方数据导入 / 中文名称为项目翻译'
                                      : e['review_status'] == 'user_supplied'
                                      ? '用户录入，未审核'
                                      : '未审核'}',
                                ),
                                Wrap(
                                  spacing: 8,
                                  children: [
                                    if (widget.onSelect != null &&
                                        (kind == 'foods' ||
                                            e['type'] == 'weighted'))
                                      FilledButton(
                                        onPressed: busy
                                            ? null
                                            : () {
                                                widget.onSelect!(kind, e);
                                                Navigator.pop(context);
                                              },
                                        child: Text(
                                          kind == 'foods' ? '用于饮食记录' : '用于训练记录',
                                        ),
                                      ),
                                    TextButton(
                                      onPressed: busy ? null : () => edit(e),
                                      child: const Text('编辑'),
                                    ),
                                    TextButton(
                                      onPressed: busy ? null : () => archive(e),
                                      child: const Text('停用'),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ],
              if (entries.length < total)
                OutlinedButton(
                  onPressed: busy ? null : () => load(more: true),
                  child: const Text('加载更多'),
                ),
              if (!busy && entries.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(20),
                  child: Text('没有匹配条目，可修改筛选或新增。'),
                ),
            ],
          ),
        ),
      ),
    ),
  );
}
