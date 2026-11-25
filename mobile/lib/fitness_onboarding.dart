import 'package:flutter/material.dart';

import 'profile_setup.dart';
import 'ui_components.dart';
import 'regional_strength_profile.dart';
import 'user_plan_editor.dart';

class FitnessOnboarding extends StatefulWidget {
  const FitnessOnboarding({
    super.key,
    required this.request,
    required this.exercises,
    required this.details,
    required this.onFinished,
  });
  final FitnessRequest request;
  final Map<String, String> exercises;
  final Map<String, Map<String, dynamic>> details;
  final Future<void> Function() onFinished;
  @override
  State<FitnessOnboarding> createState() => _FitnessOnboardingState();
}

class _FitnessOnboardingState extends State<FitnessOnboarding> {
  final strengthKey = GlobalKey<RegionalStrengthProfileState>();
  Map<String, dynamic>? state;
  List<dynamic> rms = [];
  String? error;
  bool planStep = false;
  int profileRevision = 0;
  @override
  void initState() {
    super.initState();
    load();
  }

  Future<void> load() async {
    try {
      final results = await Future.wait([
        widget.request('/onboarding', 'GET', null),
        widget.request('/rm', 'GET', null),
      ]);
      if (mounted) {
        setState(() {
          state = Map<String, dynamic>.from(results[0]);
          rms = results[1] as List;
        });
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(planStep ? '确认你的训练计划' : '建立你的训练画像'),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('稍后继续'),
        ),
      ],
    ),
    body: state == null
        ? Center(
            child: error == null
                ? const CircularProgressIndicator()
                : Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(error!),
                      TextButton(onPressed: load, child: const Text('重试')),
                    ],
                  ),
          )
        : AppContent(
            maxWidth: 800,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  planStep ? '2 / 2 · 检查周期、训练日与负荷，确认后开始' : '1 / 2 · 画像与力量水平',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 16),
                if (!planStep)
                  ProfileSetup(
                    key: ValueKey(profileRevision),
                    facts: Map<String, dynamic>.from(state!['facts']),
                    request: widget.request,
                    buttonText: '保存画像并生成训练计划',
                    strength: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        RegionalStrengthProfile(
                          key: strengthKey,
                          request: widget.request,
                        ),
                        ExpansionTile(
                          title: const Text('已有RM记录（可选）'),
                          children: [
                            StrengthProfile(
                              request: widget.request,
                              exercises: widget.exercises,
                              records: rms,
                              onSaved: load,
                            ),
                          ],
                        ),
                      ],
                    ),
                    beforeSave: () async {
                      final form = strengthKey.currentState;
                      if (form == null) throw Exception('请等待力量评估表单加载完成');
                      await form.saveRequired();
                    },
                    onSaved: () async {
                      await load();
                      if (mounted) setState(() => planStep = true);
                    },
                  )
                else ...[
                  TextButton.icon(
                    onPressed: () => setState(() {
                      planStep = false;
                      profileRevision++;
                    }),
                    icon: const Icon(Icons.arrow_back),
                    label: const Text('返回调整画像'),
                  ),
                  UserPlanEditor(
                    compact: true,
                    onCompleteProfile: () => setState(() {
                      planStep = false;
                      profileRevision++;
                    }),
                    autoGenerate: true,
                    post: (path, body) => widget.request(path, 'POST', body),
                    exercises: widget.exercises,
                    exerciseDetails: widget.details,
                    onSaved: () async {
                      await widget.request('/onboarding/complete', 'POST', {});
                      await widget.onFinished();
                      if (context.mounted) Navigator.pop(context, true);
                    },
                  ),
                ],
              ],
            ),
          ),
  );
}
