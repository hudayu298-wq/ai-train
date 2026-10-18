import 'dart:async';

import 'package:camera/camera.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:google_mlkit_pose_detection/google_mlkit_pose_detection.dart';

import 'coaching_engine.dart';

class LiveSession extends StatefulWidget {
  const LiveSession({super.key, required this.exerciseId});
  final String exerciseId;
  @override
  State<LiveSession> createState() => _LiveSessionState();
}

class _LiveSessionState extends State<LiveSession> with WidgetsBindingObserver {
  late CaptureGuide guide;
  late CoachingEngine engine;
  final tts = FlutterTts();
  final gate = CueGate();
  CameraController? camera;
  PoseDetector? detector;
  final clock = Stopwatch()..start();
  bool opening = false, processing = false, running = false, sound = true;
  bool angleConfirmed = false,
      audioConfirmed = false,
      ready = false,
      tempo = false;
  bool closing = false;
  int lastFrame = -200, reps = 0, latency = 0;
  String status = '点击开启相机，按示意框摆放支架';
  String? failure;
  int generation = 0;
  bool get native =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);
  bool get android => defaultTargetPlatform == TargetPlatform.android;

  @override
  void initState() {
    super.initState();
    guide = CaptureGuide.all.firstWhere((g) => g.id == widget.exerciseId);
    engine = CoachingEngine(guide);
    WidgetsBinding.instance.addObserver(this);
  }

  Future<void> speak(String text, {bool repetition = false}) async {
    if (!sound ||
        closing ||
        !gate.accept(text, clock.elapsedMilliseconds, repetition: repetition)) {
      return;
    }
    try {
      await tts.speak(text);
    } catch (e) {
      if (mounted && !closing) setState(() => failure = '语音播放失败，请重新测试耳机：$e');
    } finally {
      gate.speaking = false;
    }
  }

  Future<void> openCamera() async {
    if (opening || closing || camera != null) return;
    setState(() {
      opening = true;
      failure = null;
    });
    final token = ++generation;
    CameraController? next;
    try {
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
      ]);
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw Exception('没有可用相机');
      final back = cameras.where(
        (c) => c.lensDirection == CameraLensDirection.back,
      );
      next = CameraController(
        back.isNotEmpty ? back.first : cameras.first,
        ResolutionPreset.medium,
        enableAudio: false,
        imageFormatGroup: android
            ? ImageFormatGroup.nv21
            : ImageFormatGroup.bgra8888,
      );
      await next.initialize();
      if (!mounted || closing || token != generation) {
        await next.dispose();
        return;
      }
      await next.lockCaptureOrientation(DeviceOrientation.portraitUp);
      detector ??= PoseDetector(
        options: PoseDetectorOptions(
          mode: PoseDetectionMode.stream,
          model: PoseDetectionModel.base,
        ),
      );
      await tts.setLanguage('zh-CN');
      await tts.setSpeechRate(.45);
      await tts.awaitSpeakCompletion(true);
      if (!mounted || closing || token != generation) {
        await next.dispose();
        return;
      }
      camera = next;
      await next.startImageStream(onFrame);
      if (mounted && !closing) setState(() => status = '按框摆放身体，等待关键部位稳定入框');
    } catch (e) {
      await next?.dispose();
      camera = null;
      if (mounted && !closing) setState(() => failure = '无法开启实时检测：$e');
    } finally {
      if (mounted && !closing) setState(() => opening = false);
    }
  }

  InputImage? inputImage(CameraImage image, CameraController c) {
    final rotation = InputImageRotationValue.fromRawValue(
      c.description.sensorOrientation,
    );
    final format = InputImageFormatValue.fromRawValue(image.format.raw);
    if (rotation == null ||
        image.planes.length != 1 ||
        (android && format != InputImageFormat.nv21) ||
        (!android && format != InputImageFormat.bgra8888)) {
      return null;
    }
    return InputImage.fromBytes(
      bytes: image.planes.first.bytes,
      metadata: InputImageMetadata(
        size: Size(image.width.toDouble(), image.height.toDouble()),
        rotation: rotation,
        format: format!,
        bytesPerRow: image.planes.first.bytesPerRow,
      ),
    );
  }

  Future<void> onFrame(CameraImage image) async {
    final c = camera;
    if (processing ||
        closing ||
        c == null ||
        clock.elapsedMilliseconds - lastFrame < 100) {
      return;
    }
    lastFrame = clock.elapsedMilliseconds;
    processing = true;
    final token = generation;
    final started = clock.elapsedMilliseconds;
    try {
      final input = inputImage(image, c);
      if (input == null) {
        if (mounted) {
          setState(() {
            ready = false;
            running = false;
            status = '设备帧格式不支持，请结束后更换设备测试';
          });
        }
        return;
      }
      final poses = await detector!.processImage(input);
      if (!mounted || closing || token != generation) return;
      if (clock.elapsedMilliseconds - started > 500) {
        engine.resetMotion();
        engine.validSince = null;
        setState(() {
          ready = false;
          status = '检测延迟过高，暂停判断；请在本组结束后检查设备';
        });
        return;
      }
      final rotated =
          c.description.sensorOrientation == 90 ||
          c.description.sensorOrientation == 270;
      // ML Kit Android emits rotation-corrected coordinates; iOS uses source axes.
      final w = android && rotated
          ? image.height.toDouble()
          : image.width.toDouble();
      final h = android && rotated
          ? image.width.toDouble()
          : image.height.toDouble();
      final points = <String, Joint>{};
      if (poses.length == 1) {
        for (final entry in poses.first.landmarks.entries) {
          points[entry.key.name.toLowerCase()] = Joint(
            entry.value.x / w,
            entry.value.y / h,
            entry.value.likelihood,
          );
        }
      }
      final result = engine.process(
        points,
        started,
        active: running,
        aspect: w / h,
        tempoFeedback: tempo,
      );
      setState(() {
        ready = result.ready;
        status = result.message;
        reps = result.reps;
        latency = clock.elapsedMilliseconds - started;
      });
      if (running && result.cue != null) {
        unawaited(speak(result.cue!, repetition: true));
      }
      if (running && !result.ready) {
        unawaited(speak('画面暂时不可用，已暂停判断。请在本组结束后检查机位'));
      }
    } catch (e) {
      if (mounted && !closing) {
        setState(() {
          ready = false;
          running = false;
          failure = '检测失败，请重新打开页面：$e';
        });
      }
    } finally {
      processing = false;
    }
  }

  Future<void> releaseCamera() async {
    generation++;
    running = false;
    ready = false;
    angleConfirmed = false;
    engine.resetMotion();
    engine.validSince = null;
    final old = camera;
    camera = null;
    await tts.stop();
    gate.speaking = false;
    if (old != null) {
      if (old.value.isStreamingImages) await old.stopImageStream();
      await old.dispose();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Permission dialogs may briefly inactivate the app before a camera exists.
    if (state == AppLifecycleState.inactive && camera == null) return;
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused) {
      unawaited(
        releaseCamera().then((_) {
          if (mounted && !closing) setState(() => status = '已暂停，返回后请重新开启相机');
        }),
      );
    }
  }

  @override
  void dispose() {
    closing = true;
    WidgetsBinding.instance.removeObserver(this);
    unawaited(shutdown());
    super.dispose();
  }

  Future<void> shutdown() async {
    await releaseCamera();
    while (processing) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    await detector?.close();
    if (native) {
      await SystemChrome.setPreferredOrientations(DeviceOrientation.values);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text('${guide.name} · 实时训练')),
    body: ListView(
      padding: const EdgeInsets.all(18),
      children: [
        Text(
          guide.instructions,
          style: const TextStyle(fontSize: 16, height: 1.6),
        ),
        const SizedBox(height: 12),
        AspectRatio(
          aspectRatio: camera?.value.isInitialized == true
              ? 1 / camera!.value.aspectRatio
              : .75,
          child: ClipRRect(
            borderRadius: BorderRadius.circular(18),
            child: ColoredBox(
              color: const Color(0xff182820),
              child: Stack(
                fit: StackFit.expand,
                children: [
                  if (camera?.value.isInitialized == true)
                    CameraPreview(camera!),
                  IgnorePointer(
                    child: CustomPaint(painter: GuidePainter(guide, ready)),
                  ),
                  Positioned(
                    left: 16,
                    top: 12,
                    child: Text(
                      running
                          ? '实时计次 $reps'
                          : '侧面机位 · ${guide.horizontal ? '卧姿' : '站姿'}取景',
                      style: const TextStyle(color: Colors.white),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 12),
        Text(status),
        if (!native) const Text('Web 当前展示拍摄模板；实时姿态检测需在 Android / iOS 客户端运行。'),
        if (failure != null)
          Text(failure!, style: const TextStyle(color: Colors.red)),
        if (native && camera == null)
          FilledButton(
            onPressed: opening ? null : openCamera,
            child: Text(opening ? '开启中…' : '开启相机'),
          ),
        if (native) Text('本地处理 · 最近一次检测 ${latency}ms · 开发规则，计次未经真机评测'),
        CheckboxListTile(
          value: angleConfirmed,
          title: const Text('已确认正侧面拍摄，画面主角是本人'),
          onChanged: running
              ? null
              : (v) => setState(() => angleConfirmed = v ?? false),
        ),
        SwitchListTile(
          value: sound,
          title: const Text('语音播报'),
          onChanged: (v) {
            setState(() {
              sound = v;
              audioConfirmed = false;
            });
            if (!v) unawaited(tts.stop());
          },
        ),
        if (sound) ...[
          OutlinedButton(
            onPressed: native && camera != null
                ? () => speak('耳机测试，你将听到训练次数与取景提示')
                : null,
            child: const Text('测试耳机声音'),
          ),
          CheckboxListTile(
            value: audioConfirmed,
            title: const Text('已在耳机中听到提示'),
            onChanged: (v) => setState(() => audioConfirmed = v ?? false),
          ),
        ],
        SwitchListTile(
          value: tempo,
          title: const Text('实验性节奏提示'),
          subtitle: const Text('根据动作周期提醒放慢节奏，尚未经教练验证；不判断姿态安全。'),
          onChanged: running ? null : (v) => setState(() => tempo = v),
        ),
        FilledButton(
          onPressed:
              !native ||
                  !ready ||
                  !angleConfirmed ||
                  (sound && !audioConfirmed) ||
                  running
              ? null
              : () {
                  engine.startSet();
                  setState(() {
                    running = true;
                    reps = 0;
                  });
                  unawaited(speak('开始本组训练'));
                },
          child: const Text('开始本组'),
        ),
        OutlinedButton(
          onPressed: !running
              ? null
              : () {
                  setState(() => running = false);
                  engine.resetMotion();
                  unawaited(tts.stop());
                  showDialog<void>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: const Text('本组结束'),
                      content: Text(
                        '检测到 $reps 次动作周期。\n计次为实验结果，未保存为正式训练记录；请在训练页确认重量、组次。',
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('知道了'),
                        ),
                      ],
                    ),
                  );
                },
          child: const Text('结束本组'),
        ),
        const Text(
          '取景框是摆位参考，不会自动验证拍摄角度或识别杠铃。检测可能跟踪画面中其他人，开始前请确认。视频不录制、不上传；语音使用系统音频输出，耳机需自行连接。',
        ),
      ],
    ),
  );
}

class GuidePainter extends CustomPainter {
  GuidePainter(this.guide, this.ready);
  final CaptureGuide guide;
  final bool ready;
  @override
  void paint(Canvas canvas, Size size) {
    final rect = Rect.fromLTWH(
      size.width * .08,
      size.height * (guide.horizontal ? .20 : .08),
      size.width * .84,
      size.height * (guide.horizontal ? .60 : .84),
    );
    final paint = Paint()
      ..color = ready ? const Color(0xffd8ed9a) : Colors.white70
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, const Radius.circular(16)),
      paint,
    );
    final body = Paint()
      ..color = Colors.white24
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;
    Offset at(double x, double y) => Offset(size.width * x, size.height * y);
    if (guide.horizontal) {
      canvas.drawCircle(
        at(.24, .45),
        size.width * .035,
        body..style = PaintingStyle.stroke,
      );
      canvas.drawLine(at(.29, .49), at(.65, .49), body);
      canvas.drawLine(at(.4, .49), at(.44, .33), body);
      canvas.drawLine(at(.65, .49), at(.75, .66), body);
      canvas.drawLine(at(.18, .57), at(.67, .57), body);
    } else {
      canvas.drawCircle(
        at(.5, .22),
        size.width * .04,
        body..style = PaintingStyle.stroke,
      );
      canvas.drawLine(at(.5, .28), at(.5, .55), body);
      canvas.drawLine(at(.5, .55), at(.4, .8), body);
      canvas.drawLine(at(.5, .55), at(.6, .8), body);
      canvas.drawLine(at(.5, .34), at(.37, .52), body);
      canvas.drawLine(at(.5, .34), at(.63, .52), body);
    }
  }

  @override
  bool shouldRepaint(GuidePainter old) =>
      old.ready != ready || old.guide != guide;
}
