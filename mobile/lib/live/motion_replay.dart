import 'dart:convert';
import 'dart:math' as math;

import 'package:crypto/crypto.dart';

import 'coaching_engine.dart';

const replaySchema = 'lianban-pose-replay-1';
const maxReplayFrames = 6000;

class ReplayFrame {
  ReplayFrame(
    this.timestamp,
    this.aspect,
    this.active,
    this.poseCount,
    this.detectionMs,
    this.points, {
    this.externalReason,
  });
  final int timestamp, poseCount, detectionMs;
  final double aspect;
  final bool active;
  final Map<String, Joint> points;
  final String? externalReason;
  Map<String, dynamic> toJson() => {
    'timestamp_ms': timestamp,
    'aspect': aspect,
    'active': active,
    'pose_count': poseCount,
    'detection_ms': detectionMs,
    'points': points.map((k, v) => MapEntry(k, [v.x, v.y, v.confidence])),
    if (externalReason != null) 'external_reason': externalReason,
  };
}

/// Explicit, page-memory-only capture. Never contains camera pixels or audio.
class MotionTrace {
  MotionTrace(this.exerciseId);
  final String exerciseId;
  final frames = <ReplayFrame>[];
  bool enabled = false, full = false;
  String? failure;
  int _bytes = 0;
  void clear() {
    frames.clear();
    full = false;
    enabled = false;
    _bytes = 0;
    failure = null;
  }

  void add(ReplayFrame frame) {
    if (!enabled) return;
    if (frame.points.values.any(
      (p) =>
          !p.x.isFinite ||
          !p.y.isFinite ||
          !p.confidence.isFinite ||
          p.x.abs() > 5 ||
          p.y.abs() > 5 ||
          p.confidence < 0 ||
          p.confidence > 1,
    )) {
      enabled = false;
      failure = '关键点数值无效，缓存已停止；此前轨迹仍可查看。';
      return;
    }
    final bytes = utf8.encode(jsonEncode(frame.toJson())).length + 1;
    if (frames.length >= maxReplayFrames ||
        _bytes + bytes > 4 * 1024 * 1024 - 16384) {
      full = true;
      enabled = false;
      return;
    }
    _bytes += bytes;
    frames.add(frame);
  }

  Map<String, dynamic> toJson({required bool viewConfirmed}) => {
    'schema': replaySchema,
    'exercise_id': exerciseId,
    'source': 'user_capture',
    'subject_id': 'local-unassigned',
    'split': 'dev',
    'video_reference': '',
    'camera_view': viewConfirmed ? 'side' : 'unknown',
    'rule_version': CoachingEngine.ruleVersion,
    'engine_source_sha256': CoachingEngine.buildFingerprint,
    'estimator': CoachingEngine.estimator,
    'frames': frames.map((f) => f.toJson()).toList(),
    'annotations': [],
    'capture_truncated': full || failure != null,
    'notice': '本机关键点轨迹；不是录像、训练事实或动作质量验证。真实录像须另外授权采集和标注。',
  };
}

class MotionReplay {
  MotionReplay(this.data, this.frames);
  final Map<String, dynamic> data;
  final List<ReplayFrame> frames;
  static int integer(dynamic value, int low, int high, String name) {
    if (value is! int || value < low || value > high) {
      throw FormatException('$name 必须为$low至$high的整数');
    }
    return value;
  }

  static double number(dynamic value, double low, double high, String name) {
    if (value is! num || !value.isFinite || value < low || value > high) {
      throw FormatException('$name 数值无效');
    }
    return value.toDouble();
  }

  static MotionReplay parse(String text) {
    if (utf8.encode(text).length > 4 * 1024 * 1024) {
      throw const FormatException('JSON不能超过4MB');
    }
    final value = jsonDecode(text);
    if (value is! Map<String, dynamic> || value['schema'] != replaySchema) {
      throw const FormatException('轨迹格式或版本不支持');
    }
    if (!CaptureGuide.all.any((g) => g.id == value['exercise_id'])) {
      throw const FormatException('只支持卧推、高杠深蹲、传统硬拉');
    }
    if (![
      'synthetic_demo',
      'user_capture',
      'annotated_video_trace',
    ].contains(value['source'])) {
      throw const FormatException('必须标明演示、本人采集或标注录像轨迹来源');
    }
    for (final key in ['subject_id', 'rule_version', 'estimator']) {
      if (value[key] is! String ||
          (value[key] as String).isEmpty ||
          (value[key] as String).length > 160) {
        throw FormatException('$key 缺失或过长');
      }
    }
    if (!['dev', 'test'].contains(value['split'])) {
      throw const FormatException('split只允许dev或test');
    }
    final recordedHash = value['engine_source_sha256'];
    if (recordedHash != null &&
        recordedHash != 'unrecorded' &&
        (recordedHash is! String ||
            !RegExp(r'^[0-9a-f]{64}$').hasMatch(recordedHash))) {
      throw const FormatException('engine_source_sha256格式无效');
    }
    if (!['side', 'front', 'unknown'].contains(value['camera_view'])) {
      throw const FormatException('camera_view无效');
    }
    if (value['video_reference'] is! String ||
        (value['video_reference'] as String).length > 500) {
      throw const FormatException('video_reference需为本地录像引用文字（不读取文件）');
    }
    final raw = value['frames'];
    if (raw is! List || raw.isEmpty || raw.length > maxReplayFrames) {
      throw const FormatException('需1至6000帧');
    }
    final frames = <ReplayFrame>[];
    int previous = -1;
    for (final row in raw) {
      if (row is! Map) throw const FormatException('帧格式无效');
      final timestamp = integer(row['timestamp_ms'], 0, 86400000, '帧时间');
      if (timestamp <= previous) throw const FormatException('帧时间必须严格递增');
      previous = timestamp;
      if (row['active'] is! bool ||
          row['points'] is! Map ||
          (row['points'] as Map).length > 40) {
        throw const FormatException('active或关键点格式无效');
      }
      final points = <String, Joint>{};
      for (final entry in (row['points'] as Map).entries) {
        if (entry.key is! String ||
            (entry.key as String).length > 40 ||
            entry.value is! List ||
            (entry.value as List).length != 3) {
          throw const FormatException('关键点需[x,y,可见性]');
        }
        final p = entry.value as List;
        points[entry.key] = Joint(
          number(p[0], -5, 5, 'x'),
          number(p[1], -5, 5, 'y'),
          number(p[2], 0, 1, '可见性'),
        );
      }
      final external = row['external_reason'];
      if (external != null &&
          ![
            'unsupported_format',
            'inference_error',
            'paused',
          ].contains(external)) {
        throw const FormatException('external_reason无效');
      }
      frames.add(
        ReplayFrame(
          timestamp,
          number(row['aspect'], .1, 10, '画面比例'),
          row['active'],
          integer(row['pose_count'], 0, 20, '人物数'),
          integer(row['detection_ms'], 0, 60000, '检测耗时'),
          points,
          externalReason: external,
        ),
      );
    }
    final annotations = value['annotations'];
    if (annotations is! List || annotations.length > 2) {
      throw const FormatException('需0至2份独立标注');
    }
    final raters = <String>{};
    for (final annotation in annotations) {
      if (annotation is! Map ||
          annotation['rater_id'] is! String ||
          (annotation['rater_id'] as String).trim().isEmpty ||
          !raters.add(annotation['rater_id'])) {
        throw const FormatException('标注者编号必须不同且非空');
      }
      final ends = annotation['rep_ends_ms'];
      if (ends is! List || ends.length > 500) {
        throw const FormatException('标注结束时刻需为数组');
      }
      int last = -1;
      for (final end in ends) {
        final t = integer(
          end,
          frames.first.timestamp,
          frames.last.timestamp,
          '标注时刻',
        );
        if (t <= last) throw const FormatException('标注时刻必须严格递增');
        if (!frames.any((f) => f.timestamp == t && f.active)) {
          throw const FormatException('标注时刻须对齐有效训练帧');
        }
        last = t;
      }
      if (annotation['independent'] != true ||
          annotation['judgeable'] is! bool) {
        throw const FormatException('需声明独立标注及是否可判断');
      }
      if (annotation['judgeable'] == false && ends.isNotEmpty) {
        throw const FormatException('无法判断时不能填确定次数');
      }
    }
    return MotionReplay(value, frames);
  }

  Map<String, dynamic> evaluate({String? engineHash}) {
    final effectiveHash = engineHash ?? CoachingEngine.buildFingerprint;
    final engine = CoachingEngine(
      CaptureGuide.all.firstWhere((g) => g.id == data['exercise_id']),
    );
    final reasons = <String, int>{};
    final timings = <int>[];
    int activeFrames = 0, accepted = 0, totalCycles = 0;
    bool active = false;
    for (final frame in frames) {
      if (frame.active && !active) engine.startSet();
      if (!frame.active && active) engine.endSet(frame.timestamp);
      active = frame.active;
      final before = engine.reps;
      final result = frame.externalReason != null
          ? engine.reject(
              frame.externalReason!,
              frame.timestamp,
              active: frame.active,
            )
          : engine.process(
              frame.points,
              frame.timestamp,
              active: frame.active,
              aspect: frame.aspect,
              poseCount: frame.poseCount,
              detectionMs: frame.detectionMs,
            );
      totalCycles += math.max(0, result.reps - before);
      if (frame.active) {
        activeFrames++;
        timings.add(frame.detectionMs);
        if (result.ready) accepted++;
        if (result.reason != null) {
          reasons.update(result.reason!, (n) => n + 1, ifAbsent: () => 1);
        }
      }
    }
    if (active) engine.endSet(frames.last.timestamp);
    final cycles = engine.evidence.where((e) => e.kind == 'cycle').toList();
    final annotations = data['annotations'] as List;
    final recordedHash = data['engine_source_sha256'];
    final hashMismatch =
        recordedHash != null &&
        recordedHash != 'unrecorded' &&
        effectiveHash != 'unrecorded' &&
        recordedHash != effectiveHash;
    final versionMatches =
        data['rule_version'] == CoachingEngine.ruleVersion && !hashMismatch;
    final annotated =
        annotations.length == 2 &&
        annotations.every((a) => a['judgeable'] == true);
    const tolerance = 300;
    final first = annotated
        ? List<int>.from(annotations[0]['rep_ends_ms'])
        : <int>[];
    final second = annotated
        ? List<int>.from(annotations[1]['rep_ends_ms'])
        : <int>[];
    final agreement =
        annotated &&
        first.length == second.length &&
        List.generate(
          first.length,
          (i) => (first[i] - second[i]).abs() <= tolerance,
        ).every((v) => v);
    final eligible =
        agreement &&
        versionMatches &&
        data['camera_view'] == 'side' &&
        data['video_reference'].toString().trim().isNotEmpty &&
        data['source'] == 'annotated_video_trace' &&
        data['capture_truncated'] != true &&
        engine.droppedEvidence == 0;
    int? expected, matched;
    if (agreement) {
      expected = first.length;
      matched = 0;
      final predictions = cycles.map((e) => e.timestampMs).toList();
      int i = 0, j = 0;
      while (i < predictions.length && j < first.length) {
        final truth = ((first[j] + second[j]) / 2).round();
        if ((predictions[i] - truth).abs() <= tolerance) {
          matched = matched! + 1;
          i++;
          j++;
        } else if (predictions[i] < truth) {
          i++;
        } else {
          j++;
        }
      }
    }
    timings.sort();
    return {
      'schema': replaySchema,
      'rule_version': CoachingEngine.ruleVersion,
      'recorded_rule_version': data['rule_version'],
      'engine_source_sha256': effectiveHash,
      'estimator': data['estimator'],
      'recorded_engine_source_sha256': recordedHash ?? 'unrecorded',
      'version_matches': versionMatches,
      'input_sha256': sha256.convert(utf8.encode(jsonEncode(data))).toString(),
      'source': data['source'],
      'subject_id': data['subject_id'],
      'split': data['split'],
      'detected_cycles': totalCycles,
      'active_frames': activeFrames,
      'observable_frame_fraction': activeFrames == 0
          ? null
          : accepted / activeFrames,
      'unavailable_frames_by_reason': reasons,
      'recorded_detection_p95_ms': timings.isEmpty
          ? null
          : timings[(timings.length * .95).ceil() - 1],
      'two_raters_agree': annotated ? agreement : null,
      'annotation_counts': annotations
          .map(
            (a) => a['judgeable'] == true
                ? (a['rep_ends_ms'] as List).length
                : null,
          )
          .toList(),
      'eligible_for_labeled_count_comparison': eligible,
      'consensus_count': eligible ? expected : null,
      'count_absolute_error': eligible ? (totalCycles - expected!).abs() : null,
      'event_precision': eligible && totalCycles > 0
          ? matched! / totalCycles
          : null,
      'event_recall': eligible && expected! > 0 ? matched! / expected : null,
      'event_tolerance_ms': tolerance,
      'evidence': engine.evidence
          .map(
            (e) => e.toJson()
              ..['engine_source_sha256'] = effectiveHash
              ..['estimator'] = data['estimator'],
          )
          .toList(),
      'dropped_evidence': engine.droppedEvidence,
      'quality_validation': 'not_performed',
      'note': '仅评估同一计次规则的回放；标注独立性为提交者声明。演示、缺录像/标注、分歧、版本变化均不报告准确率；没有姿态纠错或安全评分。',
    };
  }
}

/// Geometric fixture for exercising the UI and code, never training video evidence.
Map<String, dynamic> demoMotionTrace(String exerciseId) {
  final frames = <Map<String, dynamic>>[];
  int time = 0;
  void append(double angle, int count, {int people = 1}) {
    for (int i = 0; i < count; i++) {
      final a = angle * math.pi / 180;
      final points = exerciseId == 'bench'
          ? <String, Joint>{
              'leftshoulder': const Joint(.3, .4, .95),
              'leftelbow': const Joint(.5, .4, .95),
              'leftwrist': Joint(
                .5 - .15 * math.cos(a),
                .4 + .15 * math.sin(a),
                .95,
              ),
              'lefthip': const Joint(.5, .6, .95),
              'leftknee': const Joint(.7, .7, .95),
              'leftankle': const Joint(.85, .75, .95),
            }
          : exerciseId == 'deadlift'
          ? <String, Joint>{
              'leftshoulder': Joint(
                .5 + .15 * math.sin(a),
                .4 + .15 * math.cos(a),
                .95,
              ),
              'lefthip': const Joint(.5, .4, .95),
              'leftknee': const Joint(.5, .6, .95),
              'leftankle': const Joint(.5, .85, .95),
            }
          : <String, Joint>{
              'leftshoulder': const Joint(.5, .2, .95),
              'lefthip': const Joint(.5, .4, .95),
              'leftknee': const Joint(.5, .6, .95),
              'leftankle': Joint(
                .5 + .2 * math.sin(a),
                .6 - .2 * math.cos(a),
                .95,
              ),
            };
      frames.add(ReplayFrame(time, 1, true, people, 12, points).toJson());
      time += 100;
    }
  }

  append(175, 15);
  append(90, 8);
  append(175, 6);
  append(175, 1, people: 2);
  append(175, 15);
  append(90, 8);
  append(175, 6);
  return {
    'schema': replaySchema,
    'exercise_id': exerciseId,
    'source': 'synthetic_demo',
    'subject_id': 'synthetic-demo',
    'split': 'dev',
    'video_reference': '',
    'camera_view': 'side',
    'rule_version': CoachingEngine.ruleVersion,
    'estimator': 'synthetic geometry; not a pose model',
    'frames': frames,
    'annotations': [],
  };
}
