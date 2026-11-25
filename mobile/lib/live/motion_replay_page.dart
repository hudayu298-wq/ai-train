import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import 'coaching_engine.dart';
import 'motion_evidence_panel.dart';
import 'motion_replay.dart';

class MotionReplayPage extends StatefulWidget {
  const MotionReplayPage({super.key, required this.exerciseId});
  final String exerciseId;
  @override
  State<MotionReplayPage> createState() => _MotionReplayPageState();
}

class _MotionReplayPageState extends State<MotionReplayPage> {
  final input = TextEditingController(), video = TextEditingController();
  final raterA = TextEditingController(), raterB = TextEditingController();
  final endsA = TextEditingController(), endsB = TextEditingController();
  bool independentA = false, independentB = false, judgeA = true, judgeB = true;
  Map<String, dynamic>? report;
  String? error;
  void invalidateReport(String _) => setState(() {
    report = null;
    error = null;
  });
  void resetAnnotations() {
    independentA = false;
    independentB = false;
    judgeA = true;
    judgeB = true;
    for (final c in [video, raterA, raterB, endsA, endsB]) {
      c.clear();
    }
  }

  @override
  void dispose() {
    for (final c in [input, video, raterA, raterB, endsA, endsB]) {
      c.dispose();
    }
    super.dispose();
  }

  void runReplay() {
    try {
      final parsed = MotionReplay.parse(input.text);
      final data = Map<String, dynamic>.from(parsed.data);
      if (independentA || independentB) {
        if (!independentA || !independentB) {
          throw const FormatException('两份标注都需独立完成；不能只确认一份');
        }
        List<int> times(TextEditingController c) => c.text.trim().isEmpty
            ? []
            : c.text.trim().split(RegExp(r'[,，\s]+')).map((v) {
                final t = int.tryParse(v);
                if (t == null) throw const FormatException('标注时刻需为整数毫秒');
                return t;
              }).toList();
        data['annotations'] = [
          {
            'rater_id': raterA.text.trim(),
            'independent': true,
            'judgeable': judgeA,
            'rep_ends_ms': times(endsA),
          },
          {
            'rater_id': raterB.text.trim(),
            'independent': true,
            'judgeable': judgeB,
            'rep_ends_ms': times(endsB),
          },
        ];
        data['video_reference'] = video.text.trim();
        if (data['source'] != 'synthetic_demo' &&
            video.text.trim().isNotEmpty) {
          data['source'] = 'annotated_video_trace';
        }
      }
      final result = MotionReplay.parse(jsonEncode(data)).evaluate();
      setState(() {
        report = result;
        error = null;
      });
    } catch (e) {
      setState(() {
        error = '未完成回放：$e';
        report = null;
      });
    }
  }

  Future<void> importFile() async {
    try {
      final selected = await FilePicker.platform.pickFiles(
        type: FileType.custom,
        allowedExtensions: ['json'],
        withData: true,
      );
      if (selected == null || !mounted) return;
      final file = selected.files.single;
      if (file.size > 4 * 1024 * 1024 || file.bytes == null) {
        throw const FormatException('请选择不超过4MB的JSON');
      }
      final text = utf8.decode(file.bytes!);
      MotionReplay.parse(text);
      setState(() {
        input.text = text;
        report = null;
        error = null;
        resetAnnotations();
      });
    } catch (e) {
      if (mounted) setState(() => error = '无法读取本地轨迹：$e');
    }
  }

  void showJson(Map<String, dynamic> data) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('本地结果JSON'),
        content: SizedBox(
          width: 650,
          child: SingleChildScrollView(
            child: SelectableText(
              const JsonEncoder.withIndent('  ').convert(data),
            ),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('伴练证据回放与标注')),
    body: ListView(
      padding: const EdgeInsets.all(18),
      children: [
        const Text('本页在本机回放关键点JSON，不上传或读取录像，不写训练记录。演示仅验证流程，不能证明真实识别准确率。'),
        const SizedBox(height: 12),
        Wrap(
          spacing: 12,
          children: [
            OutlinedButton(
              onPressed: () {
                setState(() {
                  input.text = jsonEncode(demoMotionTrace(widget.exerciseId));
                  report = null;
                  error = null;
                  resetAnnotations();
                });
                runReplay();
              },
              child: const Text('运行合成演示'),
            ),
            OutlinedButton(
              onPressed: importFile,
              child: const Text('导入本地轨迹JSON'),
            ),
          ],
        ),
        TextField(
          controller: input,
          maxLines: 5,
          onChanged: (_) => setState(() {
            report = null;
            error = null;
            resetAnnotations();
          }),
          decoration: const InputDecoration(
            labelText: '轨迹JSON（也可粘贴）',
            border: OutlineInputBorder(),
          ),
        ),
        ExpansionTile(
          title: const Text('可选：两位标注者独立核对本地录像'),
          children: [
            const Text(
              '录像需另行授权、另行保存在本机。本页仅填写引用，不读取文件。结束时刻填写轨迹对应的整数毫秒，逗号分隔；0次可留空。相差超过300毫秒视为分歧，不能用平均分掩盖。',
            ),
            TextField(
              controller: video,
              onChanged: invalidateReport,
              decoration: const InputDecoration(labelText: '本地录像引用（编号或文件名）'),
            ),
            for (final a in [true, false]) ...[
              TextField(
                controller: a ? raterA : raterB,
                onChanged: invalidateReport,
                decoration: InputDecoration(
                  labelText: '标注者${a ? 'A' : 'B'}匿名编号',
                ),
              ),
              TextField(
                controller: a ? endsA : endsB,
                onChanged: invalidateReport,
                decoration: InputDecoration(
                  labelText: '${a ? 'A' : 'B'}完成时刻（毫秒）',
                ),
              ),
              SwitchListTile(
                title: Text('${a ? 'A' : 'B'}可判断次数'),
                value: a ? judgeA : judgeB,
                onChanged: (v) => setState(() {
                  report = null;
                  error = null;
                  if (a) {
                    judgeA = v;
                  } else {
                    judgeB = v;
                  }
                }),
              ),
              CheckboxListTile(
                title: Text('${a ? 'A' : 'B'}已独立标注，未查看另一份答案'),
                value: a ? independentA : independentB,
                onChanged: (v) => setState(() {
                  report = null;
                  error = null;
                  if (a) {
                    independentA = v ?? false;
                  } else {
                    independentB = v ?? false;
                  }
                }),
              ),
            ],
          ],
        ),
        FilledButton(onPressed: runReplay, child: const Text('回放并计算')),
        if (error != null)
          Text(error!, style: const TextStyle(color: Colors.red)),
        if (report != null) ...[
          const Divider(),
          Text(
            report!['source'] == 'synthetic_demo'
                ? '合成演示结果 · 无真实训练录像'
                : '本地轨迹回放结果',
          ),
          Text(
            '检测到 ${report!['detected_cycles']} 个周期；可观察帧 ${report!['observable_frame_fraction'] == null ? '无训练帧' : '${((report!['observable_frame_fraction'] as num) * 100).toStringAsFixed(1)}%'}',
          ),
          Text(
            '采集时记录的检测耗时P95：${report!['recorded_detection_p95_ms'] ?? '无'}毫秒；不代表手机端到端延迟',
          ),
          Text(
            '两位标注：${report!['two_raters_agree'] == null
                ? '未完成或无法判断'
                : report!['two_raters_agree'] == true
                ? '时间标注一致'
                : '存在分歧，需复核'}',
          ),
          if (report!['eligible_for_labeled_count_comparison'] == true)
            Text(
              '共识次数 ${report!['consensus_count']} · 计次绝对误差 ${report!['count_absolute_error']} · 事件精确率 ${report!['event_precision'] ?? '不适用'} · 召回率 ${report!['event_recall'] ?? '不适用'}',
            )
          else
            const Text('未生成准确率结论：需真实录像引用、同版本侧面轨迹及两份可判断且一致的独立标注。'),
          Text('不可用帧原因：${report!['unavailable_frames_by_reason']}'),
          Text(
            '规则 ${report!['rule_version']} · 轨迹规则 ${report!['recorded_rule_version']}',
          ),
          const Text('姿态纠错、评分与安全性未验证；本页不会激活动作规则。'),
          OutlinedButton(
            onPressed: () => showJson(report!),
            child: const Text('查看可复核报告JSON'),
          ),
          MotionEvidencePanel(
            evidence: (report!['evidence'] as List)
                .map(
                  (v) => MotionEvidence(
                    kind: v['kind'],
                    setNumber: v['set_number'],
                    timestampMs: v['timestamp_ms'],
                    message: v['message'],
                    repNumber: v['rep_number'],
                    startedMs: v['started_ms'],
                    bottomMs: v['bottom_ms'],
                    minAngle: v['min_angle_2d'],
                    maxAngle: v['max_angle_2d'],
                    minVisibility: v['min_landmark_visibility'],
                    samples: v['samples'],
                    reason: v['reason'],
                  ),
                )
                .toList(),
            dropped: report!['dropped_evidence'],
          ),
        ],
      ],
    ),
  );
}
