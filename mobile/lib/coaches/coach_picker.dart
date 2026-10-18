import 'package:flutter/material.dart';

import 'coach_persona.dart';
import 'coach_pet.dart';

class CoachPicker extends StatefulWidget {
  const CoachPicker({
    super.key,
    required this.selectedId,
    required this.onSelect,
    required this.onPrompt,
  });
  final String selectedId;
  final Future<void> Function(CoachPersona) onSelect;
  final void Function(String) onPrompt;
  @override
  State<CoachPicker> createState() => _CoachPickerState();
}

class _CoachPickerState extends State<CoachPicker> {
  bool busy = false;
  String? error;
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    padding: const EdgeInsets.fromLTRB(20, 0, 20, 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('选择你的桌宠教练', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 8),
        const Text('4 种形象、4 种性格。切换后，对话风格和提醒文案会一起变化，画像和记录继续保留。'),
        const SizedBox(height: 16),
        if (busy) const LinearProgressIndicator(),
        if (error != null)
          Text(error!, style: const TextStyle(color: Colors.red)),
        LayoutBuilder(
          builder: (context, box) => Wrap(
            spacing: 12,
            runSpacing: 12,
            children: [
              for (final persona in coachPersonas)
                SizedBox(
                  width: box.maxWidth < 320
                      ? box.maxWidth
                      : (box.maxWidth - 12) / 2,
                  child: Card(
                    color: persona.id == widget.selectedId
                        ? persona.accent.withValues(alpha: .12)
                        : Colors.white,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Column(
                        children: [
                          CoachPet(
                            coachId: persona.id,
                            size: 94,
                            animate: false,
                          ),
                          Text(
                            persona.name,
                            style: const TextStyle(
                              fontSize: 19,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          Text(
                            persona.style,
                            style: TextStyle(color: persona.accent),
                          ),
                          const SizedBox(height: 10),
                          Text(
                            persona.tapLine,
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 12),
                          ),
                          const SizedBox(height: 10),
                          FilledButton(
                            onPressed: busy
                                ? null
                                : () async {
                                    setState(() {
                                      busy = true;
                                      error = null;
                                    });
                                    try {
                                      await widget.onSelect(persona);
                                    } catch (e) {
                                      if (mounted) setState(() => error = '$e');
                                    } finally {
                                      if (mounted) setState(() => busy = false);
                                    }
                                  },
                            child: Text(
                              persona.id == widget.selectedId
                                  ? '继续使用${persona.name}'
                                  : '选择${persona.name}',
                            ),
                          ),
                          TextButton(
                            onPressed: busy
                                ? null
                                : () => widget.onPrompt(persona.id),
                            child: const Text('查看性格提示词'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ],
    ),
  );
}
