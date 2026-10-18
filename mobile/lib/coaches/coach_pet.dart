import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'coach_persona.dart';
import '../ui_theme.dart';

enum PetMood { idle, thinking, cheering, reminding, dragging, worried }

class CoachPet extends StatefulWidget {
  const CoachPet({
    super.key,
    required this.coachId,
    this.size = 140,
    this.mood = PetMood.idle,
    this.animate = true,
  });
  final String coachId;
  final double size;
  final PetMood mood;
  final bool animate;
  @override
  State<CoachPet> createState() => _CoachPetState();
}

class _CoachPetState extends State<CoachPet>
    with SingleTickerProviderStateMixin {
  late final animation = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2400),
  );
  void configure() {
    if (widget.animate &&
        !MediaQuery.disableAnimationsOf(context) &&
        TickerMode.valuesOf(context).enabled) {
      if (!animation.isAnimating) animation.repeat();
    } else {
      animation.stop();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    configure();
  }

  @override
  void didUpdateWidget(covariant CoachPet oldWidget) {
    super.didUpdateWidget(oldWidget);
    configure();
  }

  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Semantics(
    label:
        '${personaFor(widget.coachId).name}，${personaFor(widget.coachId).style}桌宠教练',
    image: true,
    child: RepaintBoundary(
      child: SizedBox(
        width: widget.size,
        height: widget.size * 1.125,
        child: AnimatedBuilder(
          animation: animation,
          builder: (_, _) => CustomPaint(
            painter: CoachPetPainter(
              personaFor(widget.coachId),
              animation.value,
              widget.mood,
            ),
          ),
        ),
      ),
    ),
  );
}

class CoachPetPainter extends CustomPainter {
  CoachPetPainter(this.persona, this.phase, this.mood);
  final CoachPersona persona;
  final double phase;
  final PetMood mood;
  static const ink = Color(0xff272d3d);
  void fill(Canvas c, Path p, Color color) =>
      c.drawPath(p, Paint()..color = color);
  void line(Canvas c, Offset a, Offset b, Color color, double width) =>
      c.drawLine(
        a,
        b,
        Paint()
          ..color = color
          ..strokeWidth = width
          ..strokeCap = StrokeCap.round,
      );
  void round(Canvas c, Rect rect, Color color, double radius) => c.drawRRect(
    RRect.fromRectAndRadius(rect, Radius.circular(radius)),
    Paint()..color = color,
  );
  @override
  void paint(Canvas c, Size size) {
    c.save();
    c.scale(size.width / 160, size.height / 180);
    final wave = math.sin(phase * math.pi * 2);
    final steady = persona.id == 'steady';
    final energetic = persona.id == 'energetic';
    final analytical = persona.id == 'analytical';
    final gentle = persona.id == 'gentle';
    final female = energetic || gentle;
    final cheer = mood == PetMood.cheering || mood == PetMood.reminding;
    final bob = cheer ? -wave.abs() * 5 : wave * 1.25;
    final skin = energetic ? const Color(0xffe9b394) : const Color(0xfff2c8ae);
    final shadowSkin = Color.lerp(skin, const Color(0xffb66b5c), .2)!;
    final hair = energetic
        ? const Color(0xff624139)
        : gentle
        ? const Color(0xff604a49)
        : const Color(0xff2d303b);
    final accent = persona.accent;
    c.drawOval(
      const Rect.fromLTWH(45, 168, 70, 7),
      Paint()..color = const Color(0x14212b42),
    );
    c.translate(0, bob);
    // Hair is layered behind the face; all four figures are adult human coaches.
    if (energetic) {
      c.save();
      c.translate(110, 34);
      c.rotate(wave * .06);
      fill(
        c,
        Path()
          ..moveTo(0, 0)
          ..cubicTo(29, -5, 30, 26, 21, 36)
          ..quadraticBezierTo(34, 56, 15, 68)
          ..quadraticBezierTo(23, 43, 6, 29)
          ..close(),
        hair,
      );
      c.restore();
      round(c, const Rect.fromLTWH(105, 29, 12, 7), accent, 3);
    }
    if (gentle) {
      fill(
        c,
        Path()
          ..moveTo(47, 38)
          ..quadraticBezierTo(34, 70, 35, 105)
          ..quadraticBezierTo(50, 118, 65, 103)
          ..lineTo(100, 107)
          ..quadraticBezierTo(126, 110, 124, 95)
          ..quadraticBezierTo(122, 49, 107, 32)
          ..close(),
        hair,
      );
    }
    // Joggers, trainers and a fitted, non-exaggerated sports outfit.
    for (final side in [-1, 1]) {
      final kick = mood == PetMood.dragging ? side * wave * 4 : 0.0;
      final x = 80 + side * 13.0;
      line(
        c,
        Offset(x, 141),
        Offset(x + kick, 160),
        const Color(0xff343b50),
        female ? 12 : 14,
      );
      round(
        c,
        Rect.fromLTWH(x - 10 + kick, 156, 24, 11),
        const Color(0xfffcfcff),
        5,
      );
      line(
        c,
        Offset(x - 7 + kick, 166),
        Offset(x + 12 + kick, 166),
        const Color(0xff56627c),
        2.3,
      );
      line(c, Offset(x + kick, 159), Offset(x + 7 + kick, 159), accent, 2);
    }
    round(
      c,
      Rect.fromLTWH(female ? 56 : 52, 99, female ? 48 : 56, 50),
      accent,
      female ? 16 : 18,
    );
    round(
      c,
      const Rect.fromLTWH(62, 98, 36, 12),
      Color.lerp(accent, Colors.black, .16)!,
      5,
    );
    round(c, const Rect.fromLTWH(74, 91, 12, 15), skin, 4);
    if (analytical) {
      line(
        c,
        const Offset(80, 109),
        const Offset(80, 146),
        const Color(0xffb9c6e0),
        1.5,
      );
      round(
        c,
        const Rect.fromLTWH(85, 118, 13, 10),
        Color.lerp(accent, Colors.white, .13)!,
        3,
      );
    } else if (gentle) {
      line(
        c,
        const Offset(70, 110),
        const Offset(69, 121),
        const Color(0xffe6def9),
        1.7,
      );
      line(
        c,
        const Offset(90, 110),
        const Offset(91, 121),
        const Color(0xffe6def9),
        1.7,
      );
      round(
        c,
        const Rect.fromLTWH(64, 129, 32, 10),
        Color.lerp(accent, Colors.white, .14)!,
        5,
      );
    } else {
      line(
        c,
        const Offset(73, 123),
        const Offset(87, 123),
        const Color(0xffeef0fa),
        2.4,
      );
      for (final x in [71.0, 89.0]) {
        line(c, Offset(x, 119), Offset(x, 127), const Color(0xffeef0fa), 4);
      }
    }
    for (final side in [-1, 1]) {
      final shoulder = Offset(80 + side * (female ? 22.0 : 25.0), 108);
      final handY = cheer
          ? 86 - wave * 3
          : mood == PetMood.dragging
          ? 111.0
          : 141 + side * wave * 1.5;
      final hand = Offset(80 + side * (cheer ? 40.0 : 32.0), handY);
      final elbow = Offset(
        80 + side * (cheer ? 36.0 : 32.0),
        cheer ? 106 : 126,
      );
      line(c, shoulder, elbow, accent, 13);
      line(c, elbow, hand, skin, 10);
      c.drawCircle(hand, 6, Paint()..color = skin);
      if (side == -1 && (steady || analytical)) {
        round(
          c,
          Rect.fromCenter(
            center: Offset(hand.dx, hand.dy - 7),
            width: 12,
            height: 5,
          ),
          ink,
          2,
        );
        round(
          c,
          Rect.fromCenter(
            center: Offset(hand.dx, hand.dy - 7),
            width: 5,
            height: 3,
          ),
          const Color(0xff9dbbff),
          1,
        );
      }
      if (side == 1 && analytical && !cheer && mood != PetMood.dragging) {
        round(
          c,
          Rect.fromLTWH(hand.dx - 4, hand.dy - 17, 17, 23),
          const Color(0xffd5deef),
          2,
        );
        round(c, Rect.fromLTWH(hand.dx + 1, hand.dy - 19, 7, 4), ink, 1);
        for (int row = 0; row < 3; row++) {
          line(
            c,
            Offset(hand.dx, hand.dy - 10 + row * 5),
            Offset(hand.dx + 8, hand.dy - 10 + row * 5),
            const Color(0xff8493af),
            1,
          );
        }
      }
    }
    // Human ears, chin, hairline, nose, eyebrows and expressive eyes.
    for (final side in [-1, 1]) {
      c.drawOval(
        Rect.fromCenter(
          center: Offset(80 + side * 33.0, 67),
          width: 12,
          height: 17,
        ),
        Paint()..color = shadowSkin,
      );
    }
    fill(
      c,
      Path()
        ..moveTo(47, 47)
        ..cubicTo(43, 16, 114, 14, 114, 47)
        ..lineTo(113, 72)
        ..cubicTo(113, 93, 96, 103, 80, 103)
        ..cubicTo(64, 103, 47, 91, 47, 72)
        ..close(),
      skin,
    );
    fill(
      c,
      Path()
        ..moveTo(49, 65)
        ..quadraticBezierTo(48, 93, 80, 101)
        ..quadraticBezierTo(102, 101, 110, 82)
        ..quadraticBezierTo(102, 103, 80, 105)
        ..quadraticBezierTo(49, 99, 49, 65)
        ..close(),
      shadowSkin.withValues(alpha: .26),
    );
    if (steady) {
      fill(
        c,
        Path()
          ..moveTo(46, 61)
          ..quadraticBezierTo(38, 36, 48, 23)
          ..lineTo(61, 16)
          ..lineTo(65, 10)
          ..lineTo(74, 16)
          ..lineTo(88, 10)
          ..lineTo(94, 17)
          ..quadraticBezierTo(125, 18, 113, 61)
          ..lineTo(105, 42)
          ..quadraticBezierTo(83, 37, 61, 43)
          ..lineTo(52, 60)
          ..close(),
        hair,
      );
    } else if (energetic) {
      fill(
        c,
        Path()
          ..moveTo(46, 65)
          ..quadraticBezierTo(33, 24, 65, 15)
          ..quadraticBezierTo(111, 4, 116, 42)
          ..lineTo(113, 64)
          ..lineTo(103, 42)
          ..quadraticBezierTo(82, 40, 72, 25)
          ..quadraticBezierTo(60, 45, 48, 49)
          ..close(),
        hair,
      );
    } else if (analytical) {
      fill(
        c,
        Path()
          ..moveTo(46, 62)
          ..quadraticBezierTo(33, 23, 62, 17)
          ..quadraticBezierTo(110, 3, 117, 38)
          ..lineTo(113, 65)
          ..lineTo(104, 46)
          ..lineTo(104, 31)
          ..quadraticBezierTo(79, 44, 51, 45)
          ..close(),
        hair,
      );
      line(
        c,
        const Offset(90, 19),
        const Offset(104, 30),
        const Color(0xff555a69),
        2,
      );
    } else {
      fill(
        c,
        Path()
          ..moveTo(45, 68)
          ..quadraticBezierTo(33, 21, 67, 15)
          ..quadraticBezierTo(116, 7, 117, 50)
          ..lineTo(115, 77)
          ..lineTo(105, 44)
          ..quadraticBezierTo(88, 44, 80, 32)
          ..quadraticBezierTo(64, 47, 51, 47)
          ..close(),
        hair,
      );
      round(c, const Rect.fromLTWH(100, 43, 12, 4), const Color(0xffbda8e5), 2);
    }
    final eyesY = mood == PetMood.thinking ? 63.0 : 66.0;
    for (final side in [-1, 1]) {
      final x = 80 + side * 13.0;
      line(
        c,
        Offset(x - 4, eyesY - 12),
        Offset(x + 4, eyesY - 13 + (mood == PetMood.worried ? side * 3 : 0)),
        hair,
        2,
      );
      if (phase > .83 && phase < .89 || cheer) {
        c.drawArc(
          Rect.fromCenter(center: Offset(x, eyesY + 2), width: 11, height: 8),
          math.pi,
          math.pi,
          false,
          Paint()
            ..color = ink
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.6
            ..strokeCap = StrokeCap.round,
        );
      } else {
        c.drawOval(
          Rect.fromCenter(center: Offset(x, eyesY), width: 12, height: 15),
          Paint()..color = const Color(0xfffffcfc),
        );
        c.drawOval(
          Rect.fromCenter(
            center: Offset(x + (mood == PetMood.thinking ? 1 : 0), eyesY),
            width: 7,
            height: 11,
          ),
          Paint()..color = hair,
        );
        c.drawCircle(
          Offset(x + 1.5, eyesY - 3),
          1.6,
          Paint()..color = Colors.white,
        );
        if (female) {
          line(
            c,
            Offset(x - 5, eyesY - 6),
            Offset(x + 4, eyesY - 6),
            hair,
            1.5,
          );
        }
      }
    }
    if (analytical) {
      for (final x in [60.0, 85.0]) {
        c.drawRRect(
          RRect.fromRectAndRadius(
            Rect.fromLTWH(x, 57, 17, 17),
            const Radius.circular(5),
          ),
          Paint()
            ..color = ink
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.8,
        );
      }
      line(c, const Offset(77, 63), const Offset(85, 63), ink, 1.5);
    }
    for (final x in [59.0, 101.0]) {
      c.drawOval(
        Rect.fromCenter(center: Offset(x, 80), width: 10, height: 5),
        Paint()..color = const Color(0x44dc837d),
      );
    }
    c.drawOval(const Rect.fromLTWH(78, 74, 5, 4), Paint()..color = shadowSkin);
    if (cheer) {
      round(c, const Rect.fromLTWH(74, 84, 13, 9), const Color(0xffa45151), 4);
      round(c, const Rect.fromLTWH(75, 84, 11, 3), Colors.white, 1);
    } else {
      c.drawArc(
        const Rect.fromLTWH(75, 81, 12, 10),
        mood == PetMood.worried ? math.pi : 0,
        math.pi,
        false,
        Paint()
          ..color = const Color(0xff995b58)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.8
          ..strokeCap = StrokeCap.round,
      );
    }
    if (mood == PetMood.thinking) {
      round(c, const Rect.fromLTWH(115, 17, 35, 17), Colors.white, 9);
      for (int i = 0; i < 3; i++) {
        c.drawCircle(
          Offset(123 + i * 9.0, 25.5),
          1.8 + ((phase * 3).floor() == i ? .7 : 0),
          Paint()..color = accent,
        );
      }
    }
    c.restore();
  }

  @override
  bool shouldRepaint(covariant CoachPetPainter oldDelegate) =>
      oldDelegate.phase != phase ||
      oldDelegate.persona.id != persona.id ||
      oldDelegate.mood != mood;
}

class CoachPetOverlay extends StatefulWidget {
  const CoachPetOverlay({
    super.key,
    required this.coachId,
    required this.name,
    required this.onChoose,
    this.mood = PetMood.idle,
    this.message,
  });
  final String coachId, name;
  final PetMood mood;
  final String? message;
  final VoidCallback onChoose;
  @override
  State<CoachPetOverlay> createState() => _CoachPetOverlayState();
}

class _CoachPetOverlayState extends State<CoachPetOverlay> {
  Offset position = const Offset(1, .95);
  bool collapsed = false, dragging = false, tapped = false;
  Timer? reaction;
  @override
  void dispose() {
    reaction?.cancel();
    super.dispose();
  }

  void greet() {
    reaction?.cancel();
    setState(() {
      collapsed = false;
      tapped = true;
    });
    reaction = Timer(const Duration(seconds: 3), () {
      if (mounted) setState(() => tapped = false);
    });
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, box) {
      final compact = collapsed || box.maxHeight < 160 || box.maxWidth < 220;
      final width = math.min(compact ? 120.0 : 158.0, box.maxWidth);
      final height = math.min(compact ? 50.0 : 250.0, box.maxHeight);
      final dx = math.max(0.0, box.maxWidth - width);
      final dy = math.max(0.0, box.maxHeight - height);
      final persona = personaFor(widget.coachId);
      return Stack(
        children: [
          Positioned(
            left: position.dx.clamp(0, 1) * dx,
            top: position.dy.clamp(0, 1) * dy,
            width: width,
            height: height,
            child: GestureDetector(
              key: const ValueKey('draggable-coach-pet'),
              onPanStart: (_) => setState(() => dragging = true),
              onPanUpdate: (event) => setState(
                () => position = Offset(
                  dx == 0 ? 0 : (position.dx + event.delta.dx / dx).clamp(0, 1),
                  dy == 0 ? 0 : (position.dy + event.delta.dy / dy).clamp(0, 1),
                ),
              ),
              onPanEnd: (_) => setState(() => dragging = false),
              onPanCancel: () => setState(() => dragging = false),
              onTap: greet,
              onLongPress: widget.onChoose,
              child: compact
                  ? Material(
                      color: AppColors.soft,
                      borderRadius: BorderRadius.circular(24),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          CoachPet(
                            coachId: widget.coachId,
                            size: 36,
                            animate: false,
                          ),
                          Flexible(
                            child: Text(
                              widget.name,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ),
                        ],
                      ),
                    )
                  : Column(
                      mainAxisAlignment: MainAxisAlignment.end,
                      children: [
                        if (tapped ||
                            widget.message != null ||
                            widget.mood != PetMood.idle)
                          Flexible(
                            child: Container(
                              padding: const EdgeInsets.all(10),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: .96),
                                borderRadius: BorderRadius.circular(14),
                                border: Border.all(
                                  color: persona.accent.withValues(alpha: .3),
                                ),
                              ),
                              child: Text(
                                tapped
                                    ? persona.tapLine
                                    : widget.message ?? persona.tapLine,
                                maxLines: 3,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(
                                  fontSize: 12,
                                  height: 1.4,
                                ),
                              ),
                            ),
                          ),
                        Flexible(
                          flex: 3,
                          child: CoachPet(
                            coachId: widget.coachId,
                            size: 128,
                            mood: dragging
                                ? PetMood.dragging
                                : tapped
                                ? PetMood.cheering
                                : widget.mood,
                          ),
                        ),
                        Material(
                          color: Colors.white.withValues(alpha: .92),
                          borderRadius: BorderRadius.circular(16),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Flexible(
                                child: TextButton(
                                  onPressed: widget.onChoose,
                                  child: Text(
                                    '换教练 · ${widget.name}',
                                    maxLines: 1,
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontSize: 11),
                                  ),
                                ),
                              ),
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                tooltip: '收起教练桌宠',
                                onPressed: () =>
                                    setState(() => collapsed = true),
                                icon: const Icon(Icons.remove, size: 16),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
            ),
          ),
        ],
      );
    },
  );
}
