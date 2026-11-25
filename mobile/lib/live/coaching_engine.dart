import 'dart:math' as math;

class CaptureGuide {
  const CaptureGuide(this.id, this.name, this.instructions, this.horizontal);
  final String id, name, instructions;
  final bool horizontal;
  static const all = [
    CaptureGuide(
      'bench',
      '平板杠铃卧推',
      '支架放在身体正侧面，镜头接近卧推凳高度。让头部、手臂、髋部和双脚入框，并为杠铃上下移动留出空间。',
      true,
    ),
    CaptureGuide(
      'squat',
      '高杠杠铃深蹲',
      '支架放在身体正侧面，镜头接近髋部高度。头部、双脚和杠铃全程入框，避免深蹲架遮挡。',
      false,
    ),
    CaptureGuide(
      'deadlift',
      '传统杠铃硬拉',
      '支架放在身体正侧面，镜头接近髋部高度。覆盖头部、双脚和地面杠铃，下俯时身体仍需在框内。',
      false,
    ),
  ];
}

class Joint {
  const Joint(this.x, this.y, this.confidence);
  final double x, y, confidence;
}

double? jointAngle(Joint a, Joint b, Joint c) {
  final ux = a.x - b.x, uy = a.y - b.y;
  final vx = c.x - b.x, vy = c.y - b.y;
  final length = math.sqrt((ux * ux + uy * uy) * (vx * vx + vy * vy));
  if (length < 0.000001) return null;
  return math.acos(((ux * vx + uy * vy) / length).clamp(-1.0, 1.0)) *
      180 /
      math.pi;
}

class CoachingResult {
  const CoachingResult({
    required this.ready,
    required this.message,
    required this.reps,
    this.cue,
    this.reason,
  });
  final bool ready;
  final String message;
  final int reps;
  final String? cue;
  final String? reason;
}

/// Evidence describes detection, never a diagnosis or a confirmed training fact.
class MotionEvidence {
  const MotionEvidence({
    required this.kind,
    required this.setNumber,
    required this.timestampMs,
    required this.message,
    this.repNumber,
    this.startedMs,
    this.bottomMs,
    this.minAngle,
    this.maxAngle,
    this.minVisibility,
    this.samples,
    this.reason,
  });
  final String kind, message;
  final int setNumber, timestampMs;
  final int? repNumber, startedMs, bottomMs, samples;
  final double? minAngle, maxAngle, minVisibility;
  final String? reason;
  Map<String, dynamic> toJson() => {
    'kind': kind,
    'set_number': setNumber,
    'timestamp_ms': timestampMs,
    'message': message,
    if (reason != null) 'reason': reason,
    if (repNumber != null) 'rep_number': repNumber,
    if (startedMs != null) 'started_ms': startedMs,
    if (bottomMs != null) 'bottom_ms': bottomMs,
    if (minAngle != null) 'min_angle_2d': minAngle,
    if (maxAngle != null) 'max_angle_2d': maxAngle,
    if (minVisibility != null) 'min_landmark_visibility': minVisibility,
    if (samples != null) 'samples': samples,
    'rule_version': CoachingEngine.ruleVersion,
    'engine_source_sha256': CoachingEngine.buildFingerprint,
    'estimator': CoachingEngine.estimator,
    'validated': false,
  };
}

/// Development thresholds, not validated form assessment. Angles use pixel-space
/// points (normalised x/y must be scaled to the same aspect before measuring).
class CoachingEngine {
  CoachingEngine(this.guide);
  static const ruleVersion = 'live-cycle-2';
  static const buildFingerprint = String.fromEnvironment(
    'LIVE_ENGINE_SHA',
    defaultValue: 'unrecorded',
  );
  static const estimator = 'ML Kit base / stream（底层模型构建号未提供）';
  static const rejectionMessages = {
    'no_person': '未检测到人物，请调整取景和光线',
    'multiple_people': '检测到多个人物，暂停判断；请清空取景区域',
    'missing_landmarks': '关键部位缺失或被遮挡，请调整机位',
    'low_visibility': '关键部位可见性不足，请检查遮挡和光线',
    'out_of_frame': '关键部位出框，请调整支架距离',
    'invalid_geometry': '坐标或画面比例无效，暂停判断',
    'stabilizing': '请保持机位，正在检查入框稳定性',
    'frame_gap': '画面中断超过500毫秒，已放弃未完成周期',
    'out_of_order': '帧时间未递增，已放弃未完成周期',
    'side_changed': '跟踪侧发生变化，请重新稳定入框',
    'slow_detection': '检测超过500毫秒，暂停判断并放弃未完成周期',
    'unsupported_format': '设备帧格式不支持，请结束后更换设备测试',
    'inference_error': '检测发生错误，请重新开启相机',
    'paused': '离页或切换后台，已放弃未完成周期',
    'incomplete_cycle': '本组结束时周期未完成，不计入次数',
    'short_cycle': '周期短于600毫秒，未计次；此阈值未经训练质量验证',
  };
  final CaptureGuide guide;
  int reps = 0;
  int setNumber = 0, droppedEvidence = 0;
  final _evidence = <MotionEvidence>[];
  List<MotionEvidence> get evidence => List.unmodifiable(_evidence);
  String? _lastReason;
  double? _minAngle, _maxAngle, _minVisibility;
  int _samples = 0;
  int? _bottomMs;
  String? side;
  int? lastTimestamp, validSince, motionStarted;
  bool armed = false, lowered = false;
  int highFrames = 0, lowFrames = 0;

  void resetMotion() {
    armed = false;
    lowered = false;
    highFrames = 0;
    lowFrames = 0;
    motionStarted = null;
    _minAngle = _maxAngle = _minVisibility = null;
    _samples = 0;
    _bottomMs = null;
  }

  void startSet() {
    setNumber++;
    reps = 0;
    _lastReason = null;
    resetMotion();
  }

  void _append(MotionEvidence item) {
    if (_evidence.length >= 500) {
      _evidence.removeAt(0);
      droppedEvidence++;
    }
    _evidence.add(item);
  }

  CoachingResult reject(String reason, int timestamp, {required bool active}) {
    resetMotion();
    validSince = null;
    final message = rejectionMessages[reason]!;
    if (active && reason != _lastReason) {
      _append(
        MotionEvidence(
          kind: 'rejection',
          setNumber: math.max(1, setNumber),
          timestampMs: timestamp,
          message: message,
          reason: reason,
        ),
      );
    }
    _lastReason = reason;
    return CoachingResult(
      ready: false,
      message: message,
      reps: reps,
      reason: reason,
    );
  }

  void endSet(int timestamp, {String reason = 'incomplete_cycle'}) {
    if (motionStarted != null) reject(reason, timestamp, active: true);
    resetMotion();
  }

  CoachingResult process(
    Map<String, Joint> points,
    int timestamp, {
    required bool active,
    required double aspect,
    bool tempoFeedback = false,
    int? poseCount,
    int detectionMs = 0,
  }) {
    if (lastTimestamp != null && timestamp <= lastTimestamp!) {
      return reject('out_of_order', timestamp, active: active);
    }
    final gap = lastTimestamp != null && timestamp - lastTimestamp! > 500;
    lastTimestamp = timestamp;
    if (detectionMs > 500) {
      return reject('slow_detection', timestamp, active: active);
    }
    if (!aspect.isFinite || aspect <= 0) {
      return reject('invalid_geometry', timestamp, active: active);
    }
    final count = poseCount ?? (points.isEmpty ? 0 : 1);
    if (count == 0) return reject('no_person', timestamp, active: active);
    if (count != 1) return reject('multiple_people', timestamp, active: active);
    if (gap) return reject('frame_gap', timestamp, active: active);
    final requiredNames = guide.id == 'bench'
        ? ['shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle']
        : ['shoulder', 'hip', 'knee', 'ankle'];
    double score(String s) => requiredNames
        .map((n) => points['$s$n']?.confidence ?? 0)
        .reduce(math.min);
    final best = side != null && score(side!) >= .7
        ? side!
        : (score('left') >= score('right') ? 'left' : 'right');
    if (side != null && side != best) {
      side = best;
      return reject('side_changed', timestamp, active: active);
    }
    side = best;
    final joints = requiredNames.map((n) => points['$best$n']).toList();
    if (joints.any((p) => p == null)) {
      return reject('missing_landmarks', timestamp, active: active);
    }
    if (joints.any(
      (p) =>
          !p!.x.isFinite ||
          !p.y.isFinite ||
          !p.confidence.isFinite ||
          p.confidence < 0 ||
          p.confidence > 1,
    )) {
      return reject('invalid_geometry', timestamp, active: active);
    }
    if (joints.any((p) => p!.confidence < .7)) {
      return reject('low_visibility', timestamp, active: active);
    }
    if (joints.any(
      (p) =>
          p!.x < .08 ||
          p.x > .92 ||
          p.y < (guide.horizontal ? .20 : .08) ||
          p.y > (guide.horizontal ? .80 : .92),
    )) {
      return reject('out_of_frame', timestamp, active: active);
    }
    validSince ??= timestamp;
    if (timestamp - validSince! < 800) {
      // Warming up is a status, not a new failure every frame.
      return CoachingResult(
        ready: false,
        message: rejectionMessages['stabilizing']!,
        reps: reps,
        reason: 'stabilizing',
      );
    }
    if (!active) {
      return CoachingResult(
        ready: true,
        message: '关键部位已入框；请手动确认侧面角度与人物',
        reps: reps,
      );
    }
    Joint metric(String n) {
      final p = points['$best$n']!;
      return Joint(p.x * aspect, p.y, p.confidence);
    }

    final names = switch (guide.id) {
      'bench' => ['shoulder', 'elbow', 'wrist'],
      'squat' => ['hip', 'knee', 'ankle'],
      _ => ['shoulder', 'hip', 'knee'],
    };
    final angle = jointAngle(
      metric(names[0]),
      metric(names[1]),
      metric(names[2]),
    );
    if (angle == null || !angle.isFinite) {
      return reject('invalid_geometry', timestamp, active: active);
    }
    _lastReason = null;
    final low = guide.id == 'bench' ? 100 : 115;
    final high = guide.id == 'bench' ? 150 : 160;
    highFrames = angle > high ? highFrames + 1 : 0;
    lowFrames = angle < low ? lowFrames + 1 : 0;
    String? cue;
    if (!armed && highFrames >= 3) {
      armed = true;
    }
    if (armed && !lowered && angle < high) {
      motionStarted ??= timestamp;
    }
    if (motionStarted != null) {
      _minAngle = math.min(_minAngle ?? angle, angle);
      _maxAngle = math.max(_maxAngle ?? angle, angle);
      final visibility = joints.map((p) => p!.confidence).reduce(math.min);
      _minVisibility = math.min(_minVisibility ?? visibility, visibility);
      _samples++;
    }
    if (armed && lowFrames >= 3) {
      lowered = true;
      _bottomMs ??= timestamp;
    }
    if (lowered && highFrames >= 3) {
      final duration = timestamp - (motionStarted ?? timestamp);
      if (duration >= 600) {
        reps++;
        cue = tempoFeedback && duration < 1200 ? '第$reps次，下一次放慢节奏' : '第$reps次';
        _append(
          MotionEvidence(
            kind: 'cycle',
            setNumber: math.max(1, setNumber),
            timestampMs: timestamp,
            message: '完整高角度→低角度→高角度周期；不代表动作合格',
            repNumber: reps,
            startedMs: motionStarted,
            bottomMs: _bottomMs,
            minAngle: _minAngle,
            maxAngle: _maxAngle,
            minVisibility: _minVisibility,
            samples: _samples,
          ),
        );
      } else {
        return reject('short_cycle', timestamp, active: active);
      }
      resetMotion();
    }
    return CoachingResult(
      ready: true,
      message: '实验性计次中 · 不代表动作质量合格',
      reps: reps,
      cue: cue,
    );
  }
}

/// Drops speech while busy and rate-limits repeated coaching; never queues stale cues.
class CueGate {
  int? lastSpoken;
  String? lastText;
  bool speaking = false;
  bool accept(String text, int now, {bool repetition = false}) {
    if (speaking) return false;
    if (lastSpoken != null && now - lastSpoken! < (repetition ? 1800 : 8000)) {
      return false;
    }
    if (lastText == text && lastSpoken != null && now - lastSpoken! < 12000) {
      return false;
    }
    speaking = true;
    lastSpoken = now;
    lastText = text;
    return true;
  }
}
