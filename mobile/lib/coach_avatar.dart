import 'package:flutter/material.dart';

import 'coaches/coach_pet.dart';

class CoachAvatar extends StatelessWidget {
  const CoachAvatar({super.key, this.size = 40, this.coachId = 'steady'});
  final double size;
  final String coachId;

  @override
  Widget build(BuildContext context) =>
      CoachPortrait(coachId: coachId, size: size);
}
