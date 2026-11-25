// Run from mobile: dart run tool/evaluate_live.dart manifest.json report.json
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';

import 'package:liftlab/live/motion_replay.dart';

void main(List<String> args) {
  try {
    if (args.length != 2) {
      throw const FormatException(
        '需要输入manifest.json与输出report.json两个路径；不读取或上传录像',
      );
    }
    final inputFile = File(args[0]), outputFile = File(args[1]);
    if (inputFile.absolute.path == outputFile.absolute.path) {
      throw const FormatException('报告不能覆盖原始评测集');
    }
    if (inputFile.lengthSync() > 32 * 1024 * 1024) {
      throw const FormatException('评测集不能超过32MB');
    }
    final manifest = jsonDecode(inputFile.readAsStringSync());
    if (manifest is! Map ||
        manifest['cases'] is! List ||
        (manifest['cases'] as List).isEmpty) {
      throw const FormatException('manifest需要非空cases数组');
    }
    final cases = manifest['cases'] as List;
    final engineHash = sha256
        .convert(
          File.fromUri(
            Platform.script.resolve('../lib/live/coaching_engine.dart'),
          ).readAsBytesSync(),
        )
        .toString();
    if (cases.length > 200) throw const FormatException('最多200例');
    final subjects = <String, String>{}, clips = <String, String>{};
    final reports = <Map<String, dynamic>>[];
    for (final value in cases) {
      final replay = MotionReplay.parse(jsonEncode(value));
      final subject = replay.data['subject_id'] as String;
      final split = replay.data['split'] as String;
      if (subject == 'local-unassigned') {
        throw const FormatException('评测前需填写一致的匿名subject_id，不能使用未分配身份');
      }
      if (subjects.containsKey(subject) && subjects[subject] != split) {
        throw const FormatException('同一受试者不能跨dev/test，防止泄漏');
      }
      subjects[subject] = split;
      final hash = sha256
          .convert(utf8.encode(jsonEncode(value['frames'])))
          .toString();
      if (clips.containsKey(hash)) {
        throw const FormatException('存在重复轨迹；不能靠修改受试者ID重复计入');
      }
      clips[hash] = split;
      final reference = replay.data['video_reference'] as String;
      if (reference.trim().isNotEmpty) {
        final key = 'video:$reference';
        if (clips.containsKey(key)) {
          throw const FormatException('同一录像引用不能作为不同独立样本重复计入');
        }
        clips[key] = split;
      }
      reports.add(replay.evaluate(engineHash: engineHash));
    }
    final bySplit = <String, dynamic>{};
    for (final split in ['dev', 'test']) {
      final subset = reports.where((r) => r['split'] == split).toList();
      final comparable = subset
          .where((r) => r['eligible_for_labeled_count_comparison'] == true)
          .toList();
      bySplit[split] = {
        'cases': subset.length,
        'comparable_cases': comparable.length,
        'count_mae': comparable.isEmpty
            ? null
            : comparable
                      .map((r) => r['count_absolute_error'] as int)
                      .reduce((a, b) => a + b) /
                  comparable.length,
        'disagreement_cases': subset
            .where((r) => r['two_raters_agree'] == false)
            .length,
        'excluded_cases': subset.length - comparable.length,
      };
    }
    final output = {
      'schema': 'lianban-live-evaluation-1',
      'evaluator_source_sha256': sha256
          .convert(File.fromUri(Platform.script).readAsBytesSync())
          .toString(),
      'replay_source_sha256': sha256
          .convert(
            File.fromUri(
              Platform.script.resolve('../lib/live/motion_replay.dart'),
            ).readAsBytesSync(),
          )
          .toString(),
      'engine_source_sha256': engineHash,
      'manifest_sha256': sha256
          .convert(utf8.encode(jsonEncode(manifest)))
          .toString(),
      'summary_by_split': bySplit,
      'cases': reports,
      'release_gate': 'not_evaluated',
      'note': '标注独立性来自提交者声明；本报告只检查计次，不审核专家资格、动作纠错、安全性或发布。未标注/演示/分歧样本不计准确率。',
    };
    File(args[1])
        .writeAsStringSync(const JsonEncoder.withIndent('  ').convert(output));
    stdout.writeln(jsonEncode(bySplit));
  } catch (e) {
    stderr.writeln('未生成验收通过结论：$e');
    exitCode = 1;
  }
}
