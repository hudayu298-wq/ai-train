import 'package:flutter/material.dart';

/// Catalog and live-session preparation both render the same server reference.
class ExerciseReference extends StatefulWidget {
  const ExerciseReference({
    super.key,
    required this.exercise,
    required this.assetBase,
    this.showDemo = true,
  });
  final Map<String, dynamic> exercise;
  final String assetBase;
  final bool showDemo;
  @override
  State<ExerciseReference> createState() => _ExerciseReferenceState();
}

class _ExerciseReferenceState extends State<ExerciseReference> {
  bool paused = false;
  Widget list(String title, dynamic values) {
    final items = values is List ? values : const [];
    if (items.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
          for (final item in items)
            Text('• $item', style: const TextStyle(height: 1.6)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final e = widget.exercise;
    final technique = e['technique'] is Map ? e['technique'] as Map : const {};
    final demo = e['demo'] is Map ? e['demo'] as Map : const {};
    final path = demo['url'];
    final still = paused || MediaQuery.disableAnimationsOf(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          '关节动作模式：${e['movement_pattern'] ?? '待补充'}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        list('关节动作', e['joint_actions']),
        list('训练部位标签', e['body_regions']),
        list('主要肌群', e['primary_muscles']),
        list('辅助肌群', e['secondary_muscles']),
        if (widget.showDemo &&
            path is String &&
            path.startsWith('/assets/exercise-demos/')) ...[
          const SizedBox(height: 12),
          AspectRatio(
            aspectRatio: 720 / 420,
            child: Image.network(
              Uri.parse('${widget.assetBase.replaceAll(RegExp(r'/+$'), '')}/')
                  .resolve(still ? path.replaceAll('.gif', '.png') : path)
                  .toString(),
              fit: BoxFit.contain,
              errorBuilder: (_, error, stack) =>
                  const Center(child: Text('示意动画加载失败，请检查服务连接')),
            ),
          ),
          Text(demo['label'] ?? '动作示意'),
          TextButton.icon(
            onPressed: () => setState(() => paused = !paused),
            icon: Icon(still ? Icons.play_arrow : Icons.pause),
            label: Text(still ? '播放示意动画' : '暂停动画'),
          ),
        ] else if (widget.showDemo)
          const Text('该条目的示意动画待补充'),
        list('准备姿势', technique['setup']),
        list('执行步骤', technique['execution']),
        list('变式细节', technique['key_points']),
        list('注意事项', technique['cautions']),
        if (technique['common_errors'] is List &&
            (technique['common_errors'] as List).isNotEmpty) ...[
          const SizedBox(height: 10),
          const Text('常见问题观察点', style: TextStyle(fontWeight: FontWeight.bold)),
          for (final cue in technique['common_errors'])
            Text(
              '• ${cue['description']}${cue['usage'] == 'reference_only' ? '（参考点，尚未用于问题识别）' : ''}',
            ),
          for (final cue in technique['common_errors'])
            if ((cue['limitation'] ?? '').toString().isNotEmpty)
              Text('判断限制：${cue['limitation']}'),
        ],
        list('影像不能直接确定', technique['not_observable']),
        const SizedBox(height: 10),
        const Text('教学草稿与示意动画尚未通过纠错验证；AI只能报告可见证据供复核。'),
        for (final source in technique['sources'] ?? [])
          Text('参考：${source['title']}'),
        Text('资料版本：${e['content_version'] ?? '未设置'}'),
      ],
    );
  }
}
