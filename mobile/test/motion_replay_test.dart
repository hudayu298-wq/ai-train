import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:liftlab/live/coaching_engine.dart';
import 'package:liftlab/live/motion_replay.dart';

Map<String, dynamic> trace() => demoMotionTrace('squat');
Map<String, dynamic> labeled() {
  final data = trace();
  data['source'] = 'annotated_video_trace';
  data['video_reference'] = 'test-fixture-only.mp4';
  data['subject_id'] = 'fixture-person';
  data['annotations'] = [
    {
      'rater_id': 'A',
      'independent': true,
      'judgeable': true,
      'rep_ends_ms': [2500, 5500],
    },
    {
      'rater_id': 'B',
      'independent': true,
      'judgeable': true,
      'rep_ends_ms': [2500, 5500],
    },
  ];
  return data;
}

Map<String, dynamic> run(Map<String, dynamic> data) =>
    MotionReplay.parse(jsonEncode(data)).evaluate();

void main() {
  test(
    'invalid captured numbers stop the trace without breaking live detection',
    () {
      final recorder = MotionTrace('squat')..enabled = true;
      recorder.add(
        ReplayFrame(0, 1, true, 1, 10, {'lefthip': Joint(double.nan, .4, .9)}),
      );
      expect(recorder.enabled, false);
      expect(recorder.frames, isEmpty);
      expect(recorder.failure, isNotNull);
      expect(recorder.toJson(viewConfirmed: true)['capture_truncated'], true);
      final data = labeled()..['capture_truncated'] = true;
      expect(run(data)['count_absolute_error'], isNull);
    },
  );
  test('all three demos use the real engine, retain cycles and rejection, never claim accuracy', () {
    for (final id in ['bench', 'squat', 'deadlift']) {
      final report = run(demoMotionTrace(id));
      expect(report['detected_cycles'], 2);
      expect(report['count_absolute_error'], isNull);
      expect(report['eligible_for_labeled_count_comparison'], false);
      expect(report['unavailable_frames_by_reason']['multiple_people'], 1);
      final cycles = (report['evidence'] as List)
          .where((e) => e['kind'] == 'cycle')
          .toList();
      expect(cycles.length, 2);
      expect(cycles.first['started_ms'], 1500);
      expect(cycles.first['timestamp_ms'], 2500);
      expect(cycles.first['min_landmark_visibility'], .95);
      expect(cycles.every((e) => e['validated'] == false), true);
    }
  });
  test(
    'replay is reproducible and input fingerprint changes with evidence',
    () {
      final data = trace();
      expect(run(data), equals(run(data)));
      final hash = run(data)['input_sha256'];
      data['frames'][0]['detection_ms'] = 13;
      expect(run(data)['input_sha256'], isNot(hash));
    },
  );
  test('known source fingerprint mismatch suppresses metrics and keeps estimator provenance', () {
    final data = labeled();
    data['engine_source_sha256'] = 'a' * 64;
    final report = MotionReplay.parse(jsonEncode(data))
        .evaluate(engineHash: 'b' * 64);
    expect(report['version_matches'], false);
    expect(report['count_absolute_error'], isNull);
    expect(
      (report['evidence'] as List).first['estimator'],
      contains('synthetic geometry'),
    );
  });
  test(
    'only complete, agreeing, same-version video labels yield count metrics',
    () {
      final report = run(labeled());
      expect(report['two_raters_agree'], true);
      expect(report['count_absolute_error'], 0);
      expect(report['event_precision'], 1);
      expect(report['event_recall'], 1);
      expect(report['quality_validation'], 'not_performed');
    },
  );
  test('count equality does not hide timing disagreement', () {
    final data = labeled();
    data['annotations'][1]['rep_ends_ms'] = [2900, 5500];
    final report = run(data);
    expect(report['two_raters_agree'], false);
    expect(report['annotation_counts'], [2, 2]);
    expect(report['count_absolute_error'], isNull);
  });
  test(
    'unjudgeable and different version or view never create score claims',
    () {
      for (final condition in [
        'unjudgeable',
        'version',
        'view',
        'no_video',
        'synthetic',
      ]) {
        final data = labeled();
        if (condition == 'unjudgeable') {
          data['annotations'][1]['judgeable'] = false;
          data['annotations'][1]['rep_ends_ms'] = [];
        }
        if (condition == 'version') data['rule_version'] = 'old-rule';
        if (condition == 'view') data['camera_view'] = 'front';
        if (condition == 'no_video') data['video_reference'] = '';
        if (condition == 'synthetic') data['source'] = 'synthetic_demo';
        final report = run(data);
        expect(
          report['eligible_for_labeled_count_comparison'],
          false,
          reason: condition,
        );
        expect(report['count_absolute_error'], isNull, reason: condition);
      }
    },
  );
  test('malformed, duplicate raters, invalid visibility and timestamps are rejected', () {
    final changes = <void Function(Map<String, dynamic>)>[
      (d) => d['frames'] = [],
      (d) => d['frames'][1]['timestamp_ms'] = 0,
      (d) => d['frames'][0]['points']['leftknee'][2] = 2.0,
      (d) => d['frames'][0]['active'] = 'true',
      (d) => d['frames'][0]['pose_count'] = -1,
      (d) => d['frames'][0]['external_reason'] = 'pretend_safe',
      (d) => d['annotations'][1]['rater_id'] = 'A',
      (d) => d['annotations'][1]['rep_ends_ms'] = [1, 5500],
      (d) => d['annotations'][1]['independent'] = false,
    ];
    for (final change in changes) {
      final data = labeled();
      change(data);
      expect(() => run(data), throwsFormatException);
    }
  });
  test(
    'no capture before consent; withdrawal clears and stops all new samples',
    () {
      final recorder = MotionTrace('squat');
      final f = ReplayFrame(0, 1, true, 1, 10, {
        'lefthip': const Joint(.5, .4, .9),
      });
      recorder.add(f);
      expect(recorder.frames, isEmpty);
      recorder.enabled = true;
      recorder.add(f);
      expect(recorder.frames.length, 1);
      expect(recorder.toJson(viewConfirmed: true)['annotations'], isEmpty);
      recorder.clear();
      recorder.add(f);
      expect(recorder.frames, isEmpty);
      expect(recorder.enabled, false);
    },
  );
  test(
    'buffer limit stops recording without silently removing old samples',
    () {
      final recorder = MotionTrace('squat')..enabled = true;
      for (int i = 0; i <= maxReplayFrames; i++) {
        recorder.add(ReplayFrame(i, 1, true, 0, 0, {}));
      }
      expect(recorder.full, true);
      expect(recorder.enabled, false);
      expect(recorder.frames.length, maxReplayFrames);
      expect(recorder.frames.first.timestamp, 0);
    },
  );
  test('distinct rejection codes cover missing, visibility, bounds, slow and time gap', () {
    final frame = MotionReplay.parse(jsonEncode(trace())).frames.first;
    CoachingResult check(
      Map<String, Joint> points, {
      double aspect = 1,
      int? count,
      int ms = 0,
    }) {
      return CoachingEngine(CaptureGuide.all[1]).process(
        points,
        0,
        active: true,
        aspect: aspect,
        poseCount: count,
        detectionMs: ms,
      );
    }

    expect(check({}).reason, 'no_person');
    expect(check(frame.points, count: 2).reason, 'multiple_people');
    expect(
      check({...frame.points}..remove('leftankle')).reason,
      'missing_landmarks',
    );
    expect(
      check({...frame.points, 'leftankle': const Joint(.5, .8, .2)}).reason,
      'low_visibility',
    );
    expect(
      check({...frame.points, 'leftankle': const Joint(.99, .8, .95)}).reason,
      'out_of_frame',
    );
    expect(check(frame.points, ms: 501).reason, 'slow_detection');
    expect(check(frame.points, aspect: double.nan).reason, 'invalid_geometry');
    final engine = CoachingEngine(CaptureGuide.all[1]);
    engine.process(frame.points, 0, active: true, aspect: 1);
    expect(
      engine.process(frame.points, 501, active: true, aspect: 1).reason,
      'frame_gap',
    );
    expect(
      engine.process(frame.points, 500, active: true, aspect: 1).reason,
      'out_of_order',
    );
  });
  test(
    'slow frame aborts partial cycle; end set never counts unfinished cycle',
    () {
      final frames = MotionReplay.parse(jsonEncode(trace())).frames;
      final engine = CoachingEngine(CaptureGuide.all[1])..startSet();
      for (final f in frames.take(23)) {
        engine.process(f.points, f.timestamp, active: true, aspect: 1);
      }
      engine.process(
        frames[23].points,
        2300,
        active: true,
        aspect: 1,
        detectionMs: 501,
      );
      for (final f in frames.skip(24).take(5)) {
        engine.process(f.points, f.timestamp, active: true, aspect: 1);
      }
      expect(engine.reps, 0);
      expect(engine.evidence.any((e) => e.reason == 'slow_detection'), true);
      final partial = CoachingEngine(CaptureGuide.all[1])..startSet();
      for (final f in frames.take(23)) {
        partial.process(f.points, f.timestamp, active: true, aspect: 1);
      }
      partial.endSet(2300);
      expect(partial.reps, 0);
      expect(partial.evidence.last.reason, 'incomplete_cycle');
    },
  );
  test(
    'short cycle is a rejection and set boundaries keep evidence attribution',
    () {
      final data = trace();
      final frames = MotionReplay.parse(jsonEncode(data)).frames;
      final engine = CoachingEngine(CaptureGuide.all[1])..startSet();
      for (final f in frames.take(18)) {
        engine.process(f.points, f.timestamp, active: true, aspect: 1);
      }
      CoachingResult? result;
      for (int t = 1800; t <= 2000; t += 100) {
        result = engine.process(
          frames.first.points,
          t,
          active: true,
          aspect: 1,
        );
      }
      expect(result!.reason, 'short_cycle');
      expect(result.ready, false);
      expect(engine.reps, 0);
      data['frames'][29]['active'] = false;
      final report = run(data);
      final cycles = (report['evidence'] as List)
          .where((e) => e['kind'] == 'cycle')
          .toList();
      expect(report['detected_cycles'], 2);
      expect(cycles.map((e) => e['set_number']).toList(), [1, 2]);
      expect(cycles.map((e) => e['rep_number']).toList(), [1, 1]);
    },
  );
}
