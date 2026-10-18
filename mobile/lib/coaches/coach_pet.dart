import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'coach_persona.dart';

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
  final ink = const Color(0xff263d38);
  void shape(Canvas c, Path path, Color color) {
    c.drawPath(path, Paint()..color = color);
  }

  void line(Canvas c, Offset a, Offset b, Color color, double width) =>
      c.drawLine(
        a,
        b,
        Paint()
          ..color = color
          ..strokeWidth = width
          ..strokeCap = StrokeCap.round,
      );
  @override
  void paint(Canvas canvas, Size size) {
    final c = canvas;
    c.save();
    c.scale(size.width / 160, size.height / 180);
    final wave = math.sin(phase * math.pi * 2);
    final cheer = mood == PetMood.cheering || mood == PetMood.reminding;
    final bob = cheer ? -wave.abs() * 7 : wave * 1.7;
    final accent = persona.accent;
    final fur = Color.lerp(accent, Colors.white, .64)!;
    final cream = const Color(0xfffff2da);
    c.drawOval(
      Rect.fromCenter(
        center: const Offset(80, 171),
        width: 65 - bob.abs(),
        height: 8,
      ),
      Paint()..color = const Color(0x18263d38),
    );
    c.translate(0, bob);
    // Tail, feet and hands move independently from the body.
    if (persona.animal == 'fox') {
      shape(
        c,
        Path()
          ..moveTo(101, 144)
          ..quadraticBezierTo(151, 145, 139, 95 + wave * 4)
          ..quadraticBezierTo(117, 101, 105, 128)
          ..close(),
        accent,
      );
      shape(
        c,
        Path()
          ..moveTo(135, 97 + wave * 4)
          ..quadraticBezierTo(144, 117, 131, 130)
          ..lineTo(122, 116)
          ..close(),
        cream,
      );
    }
    for (final side in [-1, 1]) {
      final x = 80.0 + side * 16;
      final kick = mood == PetMood.dragging ? wave * side * 5 : 0.0;
      line(c, Offset(x, 137), Offset(x + kick, 157), ink, 12);
      c.drawRRect(
        RRect.fromRectAndRadius(
          Rect.fromLTWH(x - 11 + kick, 153, 23, 12),
          const Radius.circular(6),
        ),
        Paint()..color = cream,
      );
      line(c, Offset(x - 8 + kick, 163), Offset(x + 10 + kick, 163), accent, 3);
    }
    c.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(52, 91, 56, 58),
        const Radius.circular(22),
      ),
      Paint()..color = accent,
    );
    c.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(57, 95, 46, 40),
        const Radius.circular(17),
      ),
      Paint()..color = Color.lerp(accent, Colors.white, .14)!,
    );
    for (final side in [-1, 1]) {
      final raised = cheer
          ? 90.0 - wave * 4
          : mood == PetMood.dragging
          ? 105.0
          : 131.0 + wave * side * 2;
      final hand = Offset(80 + side * (cheer ? 41.0 : 34.0), raised);
      line(c, Offset(80 + side * 24.0, 105), hand, accent, 13);
      c.drawCircle(hand, 8, Paint()..color = fur);
    }
    // Each coach has its own silhouette, not just a different tint.
    switch (persona.animal) {
      case 'bear':
        for (final x in [53.0, 107.0]) {
          c.drawCircle(Offset(x, 38), 13, Paint()..color = fur);
          c.drawCircle(Offset(x, 38), 7, Paint()..color = accent);
        }
      case 'fox':
        for (final side in [-1, 1]) {
          shape(
            c,
            Path()
              ..moveTo(80 + side * 30.0, 48)
              ..lineTo(80 + side * 37.0, 9)
              ..lineTo(80 + side * 7.0, 36)
              ..close(),
            accent,
          );
          shape(
            c,
            Path()
              ..moveTo(80 + side * 28.0, 39)
              ..lineTo(80 + side * 32.0, 20)
              ..lineTo(80 + side * 16.0, 36)
              ..close(),
            cream,
          );
        }
      case 'rabbit':
        for (final side in [-1, 1]) {
          c.save();
          c.translate(80 + side * 16.0, 39);
          c.rotate(side * (.12 + wave * .035));
          c.drawRRect(
            RRect.fromRectAndRadius(
              const Rect.fromLTWH(-8, -37, 16, 46),
              const Radius.circular(9),
            ),
            Paint()..color = fur,
          );
          c.drawRRect(
            RRect.fromRectAndRadius(
              const Rect.fromLTWH(-4, -30, 8, 31),
              const Radius.circular(5),
            ),
            Paint()..color = const Color(0xffe6bdd4),
          );
          c.restore();
        }
      default:
        line(c, const Offset(80, 37), const Offset(80, 17), accent, 5);
        c.drawCircle(
          const Offset(80, 14),
          6,
          Paint()..color = const Color(0xffffcd68),
        );
        for (final side in [-1, 1]) {
          c.drawRRect(
            RRect.fromRectAndRadius(
              Rect.fromLTWH(80 + side * 34.0 - 5, 54, 10, 22),
              const Radius.circular(5),
            ),
            Paint()..color = accent,
          );
        }
    }
    c.drawRRect(
      RRect.fromRectAndRadius(
        const Rect.fromLTWH(47, 34, 66, 65),
        Radius.circular(persona.animal == 'robot' ? 19 : 31),
      ),
      Paint()..color = persona.animal == 'fox' ? accent : fur,
    );
    if (persona.animal == 'robot') {
      c.drawRRect(
        RRect.fromRectAndRadius(
          const Rect.fromLTWH(54, 47, 52, 37),
          const Radius.circular(12),
        ),
        Paint()..color = ink,
      );
    } else {
      c.drawOval(const Rect.fromLTWH(58, 66, 44, 27), Paint()..color = cream);
      c.drawCircle(const Offset(80, 74), 3, Paint()..color = ink);
      for (final x in [58.0, 102.0]) {
        c.drawOval(
          Rect.fromCenter(center: Offset(x, 74), width: 10, height: 6),
          Paint()..color = const Color(0x55ee9491),
        );
      }
    }
    final blink = phase > .83 && phase < .89;
    final eyes = persona.animal == 'robot' ? const Color(0xffa6e6df) : ink;
    for (final x in [68.0, 92.0]) {
      final y = mood == PetMood.thinking ? 60.0 : 63.0;
      if (blink || cheer) {
        c.drawArc(
          Rect.fromCenter(center: Offset(x, y + 1), width: 9, height: 7),
          math.pi,
          math.pi,
          false,
          Paint()
            ..color = eyes
            ..style = PaintingStyle.stroke
            ..strokeWidth = 2.8
            ..strokeCap = StrokeCap.round,
        );
      } else {
        c.drawOval(
          Rect.fromCenter(center: Offset(x, y), width: 5, height: 7),
          Paint()..color = eyes,
        );
      }
    }
    c.drawArc(
      const Rect.fromLTWH(74, 74, 12, 10),
      mood == PetMood.worried ? math.pi : 0,
      math.pi,
      false,
      Paint()
        ..color = eyes
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round,
    );
    // A small dumbbell badge identifies the companion as a fitness coach.
    line(c, const Offset(72, 118), const Offset(88, 118), cream, 3);
    for (final x in [71.0, 89.0]) {
      line(c, Offset(x, 113), Offset(x, 123), cream, 5);
    }
    if (mood == PetMood.thinking) {
      c.drawRRect(
        RRect.fromRectAndRadius(
          const Rect.fromLTWH(111, 22, 37, 18),
          const Radius.circular(9),
        ),
        Paint()..color = Colors.white,
      );
      for (int i = 0; i < 3; i++) {
        c.drawCircle(
          Offset(120 + i * 10.0, 31),
          2.0 + ((phase * 3).floor() == i ? 1 : 0),
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
  Offset position = const Offset(1, .7);
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
                      color: const Color(0xffe5eddf),
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
                      children: [
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
                              style: const TextStyle(fontSize: 12, height: 1.4),
                            ),
                          ),
                        ),
                        Flexible(
                          flex: 3,
                          child: CoachPet(
                            coachId: widget.coachId,
                            size: 112,
                            mood: dragging
                                ? PetMood.dragging
                                : tapped
                                ? PetMood.cheering
                                : widget.mood,
                          ),
                        ),
                        Material(
                          color: Colors.white.withValues(alpha: .94),
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
