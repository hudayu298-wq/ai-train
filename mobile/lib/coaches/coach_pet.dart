import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'coach_persona.dart';
import '../ui_theme.dart';

enum PetMood { idle, thinking, cheering, reminding, dragging, worried }

String coachArtAsset(String coachId) =>
    'assets/coach/chibi/${personaFor(coachId).id}.png';

/// Crop the full-body source in the viewport, keeping assets unmodified.
class CoachPortrait extends StatelessWidget {
  const CoachPortrait({super.key, required this.coachId, this.size = 40});
  final String coachId;
  final double size;
  @override
  Widget build(BuildContext context) => Semantics(
    label: '${personaFor(coachId).name}教练头像',
    image: true,
    child: ClipOval(
      child: SizedBox(
        width: size,
        height: size,
        child: ColoredBox(
          color: personaFor(coachId).accent.withValues(alpha: .07),
          child: Stack(
            children: [
              Positioned(
                left: -size * .14,
                top: -size * .08,
                width: size * 1.28,
                child: Image.asset(
                  coachArtAsset(coachId),
                  fit: BoxFit.fitWidth,
                  excludeFromSemantics: true,
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

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
  bool get motionEnabled =>
      widget.animate &&
      !MediaQuery.disableAnimationsOf(context) &&
      TickerMode.valuesOf(context).enabled;
  void configure() {
    if (motionEnabled) {
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
  Widget build(BuildContext context) {
    final persona = personaFor(widget.coachId);
    final badge = switch (widget.mood) {
      PetMood.thinking => Icons.more_horiz,
      PetMood.cheering => Icons.auto_awesome,
      PetMood.reminding => Icons.notifications_active_outlined,
      PetMood.worried => Icons.favorite_outline,
      _ => null,
    };
    return Semantics(
      label: '${persona.name}，${persona.style}桌宠教练',
      image: true,
      child: RepaintBoundary(
        child: SizedBox(
          width: widget.size,
          height: widget.size * 1.55,
          child: AnimatedBuilder(
            animation: animation,
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: widget.size * .02,
                vertical: widget.size * .04,
              ),
              child: Image.asset(
                coachArtAsset(widget.coachId),
                fit: BoxFit.contain,
                gaplessPlayback: true,
                excludeFromSemantics: true,
              ),
            ),
            builder: (_, child) {
              final wave = motionEnabled
                  ? math.sin(animation.value * math.pi * 2)
                  : 0.0;
              final upbeat =
                  widget.mood == PetMood.cheering ||
                  widget.mood == PetMood.reminding;
              final bounce = upbeat ? -wave.abs() * .035 : wave * .008;
              final tilt = widget.mood == PetMood.dragging
                  ? -.07
                  : widget.mood == PetMood.thinking
                  ? .025
                  : 0.0;
              return Stack(
                fit: StackFit.expand,
                children: [
                  Transform.translate(
                    offset: Offset(0, bounce * widget.size),
                    child: Transform.rotate(
                      angle: tilt,
                      alignment: Alignment.bottomCenter,
                      child: Transform.scale(
                        scaleY: 1 + wave * .004,
                        alignment: Alignment.bottomCenter,
                        child: child,
                      ),
                    ),
                  ),
                  if (badge != null && widget.size >= 80)
                    Positioned(
                      right: 0,
                      top: widget.size * .48,
                      child: DecoratedBox(
                        decoration: BoxDecoration(
                          color: Colors.white,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: persona.accent.withValues(alpha: .25),
                          ),
                        ),
                        child: Padding(
                          padding: const EdgeInsets.all(5),
                          child: Icon(
                            badge,
                            color: persona.accent,
                            size: widget.size * .13,
                          ),
                        ),
                      ),
                    ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
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
                          CoachPortrait(coachId: widget.coachId, size: 36),
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
