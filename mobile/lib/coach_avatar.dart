import 'package:flutter/material.dart';

class CoachAvatar extends StatelessWidget {
  const CoachAvatar({super.key, this.size = 40});
  final double size;

  @override
  Widget build(BuildContext context) => Semantics(
    label: '虚拟 AI 健身教练形象',
    image: true,
    child: ClipOval(
      child: Image.asset(
        'assets/coach/liftlab_coach.png',
        width: size,
        height: size,
        fit: BoxFit.cover,
        excludeFromSemantics: true,
      ),
    ),
  );
}
