import 'package:flutter/material.dart';

import 'coaches/coach_pet.dart';

class CoachAvatar extends StatelessWidget {
  const CoachAvatar({super.key, this.size = 40, this.coachId = 'steady'});
  final double size;
  final String coachId;
  @override
  Widget build(BuildContext context) => SizedBox(
    width: size,
    height: size,
    child: FittedBox(
      child: CoachPet(coachId: coachId, size: size, animate: false),
    ),
  );
}
