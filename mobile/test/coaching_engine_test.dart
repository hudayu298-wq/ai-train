import 'dart:math' as math;

import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/live/coaching_engine.dart';

Map<String, Joint> pose(double angle, {double confidence = .95}) {
  final radians = angle * math.pi / 180;
  return {
    'leftshoulder': Joint(.5, .2, confidence),
    'lefthip': Joint(.5, .4, confidence),
    'leftknee': Joint(.5, .6, confidence),
    'leftankle': Joint(
      .5 + .2 * math.sin(radians),
      .6 - .2 * math.cos(radians),
      confidence,
    ),
  };
}

void main() {
  for (final guide in [CaptureGuide.all[0], CaptureGuide.all[2]]) {
    test('${guide.id} counts only a complete tracked cycle', () {
      final engine = CoachingEngine(guide);
      int t = 0;
      Map<String, Joint> sample(double angle) {
        final a = angle * math.pi / 180;
        if (guide.id == 'bench') {
          return {
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
          };
        }
        return {
          'leftshoulder': Joint(
            .5 + .15 * math.sin(a),
            .4 + .15 * math.cos(a),
            .95,
          ),
          'lefthip': const Joint(.5, .4, .95),
          'leftknee': const Joint(.5, .6, .95),
          'leftankle': const Joint(.5, .85, .95),
        };
      }

      void frames(double angle, int count) {
        for (int i = 0; i < count; i++) {
          engine.process(sample(angle), t, active: true, aspect: 1);
          t += 100;
        }
      }

      frames(175, 15);
      frames(90, 8);
      frames(175, 4);
      expect(engine.reps, 1);
    });
  }
  test('angle uses correct geometry and rejects zero-length joints', () {
    expect(
      jointAngle(
        const Joint(0, 0, 1),
        const Joint(1, 0, 1),
        const Joint(1, 1, 1),
      ),
      closeTo(90, .001),
    );
    expect(
      jointAngle(
        const Joint(0, 0, 1),
        const Joint(0, 0, 1),
        const Joint(1, 1, 1),
      ),
      isNull,
    );
  });
  test('requires stable visible landmarks before ready', () {
    final engine = CoachingEngine(CaptureGuide.all[1]);
    expect(
      engine.process(pose(175), 0, active: false, aspect: 1).ready,
      isFalse,
    );
    for (int t = 100; t <= 800; t += 100) {
      engine.process(pose(175), t, active: false, aspect: 1);
    }
    expect(
      engine.process(pose(175), 900, active: false, aspect: 1).ready,
      isTrue,
    );
    expect(
      engine
          .process(pose(175, confidence: .2), 1000, active: false, aspect: 1)
          .ready,
      isFalse,
    );
  });
  test('complete top-bottom-top counts once; static or jitter does not', () {
    final engine = CoachingEngine(CaptureGuide.all[1]);
    int t = 0;
    void frames(double angle, int count) {
      for (int i = 0; i < count; i++) {
        engine.process(pose(angle), t, active: true, aspect: 1);
        t += 100;
      }
    }

    frames(175, 15);
    expect(engine.reps, 0);
    frames(90, 8);
    frames(175, 4);
    expect(engine.reps, 1);
    frames(175, 10);
    expect(engine.reps, 1);
    frames(90, 1);
    frames(175, 4);
    expect(engine.reps, 1);
  });
  test('tracking loss cannot complete a movement across missing frames', () {
    final engine = CoachingEngine(CaptureGuide.all[1]);
    for (int t = 0; t < 1600; t += 100) {
      engine.process(pose(175), t, active: true, aspect: 1);
    }
    for (int t = 1600; t < 2200; t += 100) {
      engine.process(pose(90), t, active: true, aspect: 1);
    }
    engine.process({}, 2200, active: true, aspect: 1);
    for (int t = 2300; t < 4000; t += 100) {
      engine.process(pose(175), t, active: true, aspect: 1);
    }
    expect(engine.reps, 0);
  });
  test('speech drops busy cues and enforces cooldown without queueing', () {
    final gate = CueGate();
    expect(gate.accept('调整取景', 0), isTrue);
    expect(gate.accept('调整取景', 9000), isFalse);
    gate.speaking = false;
    expect(gate.accept('调整取景', 9000), isFalse);
    expect(gate.accept('调整取景', 13000), isTrue);
  });
}
