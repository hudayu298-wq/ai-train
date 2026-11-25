import 'package:flutter/material.dart';

import 'coaching_engine.dart';

class MotionEvidencePanel extends StatelessWidget {
  const MotionEvidencePanel({
    super.key,
    required this.evidence,
    this.dropped = 0,
  });
  final List<MotionEvidence> evidence;
  final int dropped;
  static String seconds(int value) => (value / 1000).toStringAsFixed(2);
  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      const Text(
        '逐次动作证据',
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
      ),
      const Text('仅为检测过程，不是动作评分或已确认训练。二维角度是画面代理值，可见性不是判断正确率。'),
      if (evidence.isEmpty) const Text('尚无周期或拒判记录。'),
      if (dropped > 0) Text('较早的$dropped条已移出本页缓存；当前保留最近500条。'),
      if (evidence.length > 20) const Text('下方显示最近20条，完整缓存可在本人同意的轨迹回放中重新计算。'),
      for (final item in evidence.reversed.take(20))
        Card(
          child: ExpansionTile(
            key: ValueKey('${item.setNumber}-${item.kind}-${item.timestampMs}'),
            title: Text(
              item.kind == 'cycle'
                  ? '第${item.setNumber}组 · 检测周期${item.repNumber}'
                  : '第${item.setNumber}组 · 未判断',
            ),
            subtitle: Text(
              item.kind == 'cycle'
                  ? '${seconds(item.startedMs!)}–${seconds(item.timestampMs)}秒 · 周期${seconds(item.timestampMs - item.startedMs!)}秒'
                  : item.message,
            ),
            children: [
              Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item.message),
                    if (item.kind == 'cycle') ...[
                      Text(
                        '画面二维角度范围：${item.minAngle!.toStringAsFixed(1)}°–${item.maxAngle!.toStringAsFixed(1)}°；不是实际关节活动度测量',
                      ),
                      Text(
                        '周期内最低关键点可见性：${(item.minVisibility! * 100).toStringAsFixed(0)}% · ${item.samples}个样本',
                      ),
                      Text('进入低角度区间：${seconds(item.bottomMs!)}秒'),
                    ],
                    if (item.reason != null)
                      Text(
                        '拒判原因：${item.reason} · ${seconds(item.timestampMs)}秒',
                      ),
                    const Text('规则 ${CoachingEngine.ruleVersion} · 未经动作质量验证'),
                  ],
                ),
              ),
            ],
          ),
        ),
    ],
  );
}
