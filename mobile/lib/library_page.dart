import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({
    super.key,
    required this.request,
    required this.onChanged,
    this.onSelect,
  });
  final Future<dynamic> Function(String, String, Object?) request;
  final Future<void> Function() onChanged;
  final void Function(String, Map<String, dynamic>)? onSelect;
  @override
  State<LibraryPage> createState() => _LibraryPageState();
}

class _LibraryPageState extends State<LibraryPage> {
  String kind = 'foods', category = '', type = '';
  final query = TextEditingController();
  List<dynamic> entries = [], categories = [];
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

  Future<void> load({bool more = false}) async {
    if (busy) return;
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
          total = result['total'];
        });
      }
    } catch (e) {
      if (mounted) setState(() => message = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
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
            'category': '主要部位',
            'equipment': '器械',
            'summary': '动作说明',
            'weight_basis': '重量记录口径',
            'source_label': '内容来源',
          };
    final controllers = {
      for (final key in fields.keys)
        key: TextEditingController(text: '${item?[key] ?? ''}'),
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
                        enabled: !saving,
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
                          entries = [];
                          categories = [];
                          query.clear();
                        });
                        load();
                      },
              ),
              const SizedBox(height: 12),
              Text(
                kind == 'foods'
                    ? '按名称、英文别名搜索。营养为每100克可食部分；请核对生熟状态、来源和实际品牌。'
                    : '负重和自重分开浏览。只有卧推、高杠深蹲和传统硬拉支持实验性实时检测；自重当前仅资料浏览。',
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
                decoration: const InputDecoration(labelText: '分类'),
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
                              : '${e['category']} · ${e['equipment']} · ${e['type'] == 'weighted' ? '负重' : '自重'}',
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
                                  Text(e['summary'] ?? ''),
                                  Text('重量口径：${e['weight_basis']}'),
                                  Text(
                                    e['realtime_supported'] == true
                                        ? '支持实验性实时检测'
                                        : '暂无实时检测',
                                  ),
                                  Text(e['view'] ?? ''),
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
                                    if (e['realtime_supported'] != true)
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
