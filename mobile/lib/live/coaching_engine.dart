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
  });
  final bool ready;
  final String message;
  final int reps;
  final String? cue;
}

/// Development thresholds, not validated form assessment. Angles use pixel-space
/// points (normalised x/y must be scaled to the same aspect before measuring).
class CoachingEngine {
  CoachingEngine(this.guide);
  final CaptureGuide guide;
  int reps = 0;
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
  }

  void startSet() {
    reps = 0;
    resetMotion();
  }

  CoachingResult process(
    Map<String, Joint> points,
    int timestamp, {
    required bool active,
    required double aspect,
    bool tempoFeedback = false,
  }) {
    if (lastTimestamp != null && timestamp <= lastTimestamp!) {
      return CoachingResult(ready: false, message: '等待新画面', reps: reps);
    }
    if (lastTimestamp != null && timestamp - lastTimestamp! > 500) {
      validSince = null;
      resetMotion();
    }
    lastTimestamp = timestamp;
    final requiredNames = guide.id == 'bench'
        ? ['shoulder', 'elbow', 'wrist', 'hip', 'knee', 'ankle']
        : ['shoulder', 'hip', 'knee', 'ankle'];
    double score(String s) => requiredNames
        .map((n) => points['$s$n']?.confidence ?? 0)
        .reduce(math.min);
    final best = side != null && score(side!) >= .7
        ? side!
        : (score('left') >= score('right') ? 'left' : 'right');
    if (side != best) {
      side = best;
      validSince = null;
      resetMotion();
    }
    final joints = requiredNames.map((n) => points['$best$n']).toList();
    final valid = joints.every(
      (p) =>
          p != null &&
          p.confidence >= .7 &&
          p.x.isFinite &&
          p.y.isFinite &&
          p.x >= .08 &&
          p.x <= .92 &&
          p.y >= (guide.horizontal ? .20 : .08) &&
          p.y <= (guide.horizontal ? .80 : .92),
    );
    if (!valid) {
      validSince = null;
      resetMotion();
      return CoachingResult(
        ready: false,
        message: '关键部位未稳定入框：调整支架或遮挡后再开始',
        reps: reps,
      );
    }
    validSince ??= timestamp;
    if (timestamp - validSince! < 800) {
      return CoachingResult(
        ready: false,
        message: '请保持机位，正在检查入框稳定性',
        reps: reps,
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
      resetMotion();
      return CoachingResult(ready: false, message: '关节角度不可用', reps: reps);
    }
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
    if (armed && lowFrames >= 3) {
      lowered = true;
    }
    if (lowered && highFrames >= 3) {
      final duration = timestamp - (motionStarted ?? timestamp);
      if (duration >= 600) {
        reps++;
        cue = tempoFeedback && duration < 1200 ? '第$reps次，下一次放慢节奏' : '第$reps次';
      }
      lowered = false;
      motionStarted = null;
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
