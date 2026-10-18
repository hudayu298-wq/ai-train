import 'dart:math';

import 'package:flutter/material.dart';

import 'coach_avatar.dart';
import 'coaches/coach_pet.dart';
import 'coaches/coach_persona.dart';

import 'dart:async';

import 'ui_theme.dart';

class CoachChat extends StatefulWidget {
  const CoachChat({
    super.key,
    required this.request,
    required this.onProfileChanged,
    this.refreshToken = 0,
    this.coachName = '阿衡',
    this.coachId = 'steady',
    this.onChooseCoach,
    this.reminderText,
    this.reminderRevision = 0,
  });
  final Future<dynamic> Function(String, String, Object?) request;
  final Future<void> Function() onProfileChanged;
  final int refreshToken;
  final String coachName;
  final String coachId;
  final VoidCallback? onChooseCoach;
  final String? reminderText;
  final int reminderRevision;

  static String displayValue(dynamic value) => switch (value) {
    'male' => '男性',
    'female' => '女性',
    'fat_loss' => '减脂',
    'muscle_gain' => '增肌',
    'beginner' => '新手',
    'intermediate' => '有训练经验',
    _ => '$value',
  };

  @override
  State<CoachChat> createState() => _CoachChatState();
}

class _CoachChatState extends State<CoachChat> {
  final composer = TextEditingController();
  final scroll = ScrollController();
  final List<Map<String, dynamic>> turns = [];
  bool loading = true, sending = false;
  bool? configured;
  String? error, retryId, retryMessage;
  Timer? petReaction;
  PetMood petMood = PetMood.idle;
  String? petMessage;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void didUpdateWidget(covariant CoachChat oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshToken != widget.refreshToken && !sending) load();
    if (oldWidget.coachId != widget.coachId ||
        oldWidget.coachName != widget.coachName) {
      retryId = null;
      if (!sending) retryMessage = null;
      petMessage = null;
      petMood = PetMood.idle;
    }
    if (widget.reminderRevision != oldWidget.reminderRevision) {
      react(
        PetMood.reminding,
        widget.reminderText ?? personaFor(widget.coachId).tapLine,
      );
    }
  }

  @override
  void dispose() {
    composer.dispose();
    scroll.dispose();
    petReaction?.cancel();
    super.dispose();
  }

  void scrollToLatest() => WidgetsBinding.instance.addPostFrameCallback((_) {
    if (mounted && scroll.hasClients) {
      scroll.animateTo(
        scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    }
  });

  Future<void> load() async {
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final results = await Future.wait([
        widget.request('/coach/messages', 'GET', null),
        widget.request('/coach/status', 'GET', null),
      ]);
      if (!mounted) return;
      setState(() {
        turns
          ..clear()
          ..addAll(
            (results[0]['turns'] as List).map(
              (v) => Map<String, dynamic>.from(v),
            ),
          );
        configured = results[1]['configured'] == true;
      });
      scrollToLatest();
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => loading = false);
    }
  }

  Future<void> send() async {
    final message = composer.text.trim();
    if (message.isEmpty || sending || loading) return;
    final requestId = retryMessage == message && retryId != null
        ? retryId!
        : '${DateTime.now().microsecondsSinceEpoch}_${Random.secure().nextInt(1 << 30)}';
    setState(() {
      sending = true;
      error = null;
      retryId = requestId;
      retryMessage = message;
    });
    scrollToLatest();
    try {
      final result = Map<String, dynamic>.from(
        await widget.request('/coach/messages', 'POST', {
          'message': message,
          'request_id': requestId,
          'coach_id': widget.coachId,
          'coach_name': widget.coachName,
        }),
      );
      if (!mounted) return;
      setState(() {
        if (!turns.any((v) => v['request_id'] == requestId)) turns.add(result);
        composer.clear();
        retryId = null;
        retryMessage = null;
        configured = true;
      });
      scrollToLatest();
      react(PetMood.cheering, personaFor(widget.coachId).replyLine);
      if ((result['profile_changes'] as List).isNotEmpty) {
        await widget.onProfileChanged();
      }
    } catch (e) {
      if (mounted) {
        setState(() => error = '$e');
        react(PetMood.worried, '这次没有连接好，可以稍后重试。');
      }
    } finally {
      if (mounted) {
        setState(() => sending = false);
        scrollToLatest();
      }
    }
  }

  void react(PetMood mood, String message) {
    if (widget.onChooseCoach == null) return;
    petReaction?.cancel();
    setState(() {
      petMood = mood;
      petMessage = message;
    });
    petReaction = Timer(const Duration(seconds: 6), () {
      if (mounted) {
        setState(() {
          petMood = PetMood.idle;
          petMessage = null;
        });
      }
    });
  }

  Widget bubble(
    String text, {
    bool user = false,
    Widget? footer,
    String? coachId,
    String? coachName,
  }) => Align(
    alignment: user ? Alignment.centerRight : Alignment.centerLeft,
    child: Container(
      constraints: const BoxConstraints(maxWidth: 620),
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: user ? AppColors.ink : Colors.white,
        border: user ? null : Border.all(color: AppColors.line),
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(user ? 16 : 4),
          topRight: Radius.circular(user ? 4 : 16),
          bottomLeft: const Radius.circular(16),
          bottomRight: const Radius.circular(16),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!user)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!user) ...[
                  CoachAvatar(size: 30, coachId: coachId ?? widget.coachId),
                  const SizedBox(width: 8),
                ],
                Flexible(
                  child: Text(
                    user ? '你' : '${coachName ?? widget.coachName} · AI 私教',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 12,
                      color: AppColors.muted,
                    ),
                  ),
                ),
              ],
            ),
          if (!user) const SizedBox(height: 8),
          SelectableText(
            text,
            style: TextStyle(
              color: user ? Colors.white : AppColors.ink,
              fontSize: 14,
              height: 1.55,
            ),
          ),
          if (footer != null) ...[
            const SizedBox(height: 12),
            Material(color: Colors.transparent, child: footer),
          ],
        ],
      ),
    ),
  );

  Widget changes(List<dynamic> items) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    childrenPadding: EdgeInsets.zero,
    title: Text(
      '已记录画像：${items.map((v) => v['label']).join('、')}',
      style: const TextStyle(fontSize: 12, color: AppColors.primary),
    ),
    children: [
      for (final item in items)
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(
            '${item['label']}：${CoachChat.displayValue(item['value'])}',
          ),
          subtitle: Text('你的原话：“${item['evidence']}”'),
        ),
      const Text('可在侧边栏“我”中查看和修改。'),
    ],
  );

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Expanded(
        child: Stack(
          children: [
            ListView(
              controller: scroll,
              padding: EdgeInsets.fromLTRB(
                20,
                16,
                20,
                widget.onChooseCoach == null ? 12 : 170,
              ),
              children: [
                Center(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 780),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (turns.isEmpty)
                          bubble(
                            personaFor(widget.coachId).greeting.replaceFirst(
                              personaFor(widget.coachId).name,
                              widget.coachName,
                            ),
                            footer: TextButton.icon(
                              onPressed: () => showDialog<void>(
                                context: context,
                                builder: (context) => AlertDialog(
                                  title: const Text('对话与画像'),
                                  content: const Text(
                                    '你明确提供的画像信息会自动记录，可在“我”中修改。对话及相关健身资料会发送到已配置的 AI 服务。',
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () => Navigator.pop(context),
                                      child: const Text('知道了'),
                                    ),
                                  ],
                                ),
                              ),
                              icon: const Icon(Icons.info_outline, size: 14),
                              label: const Text(
                                '对话与画像',
                                style: TextStyle(fontSize: 12),
                              ),
                            ),
                          ),
                        if (configured == false)
                          Container(
                            margin: const EdgeInsets.symmetric(vertical: 8),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 12,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.soft,
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.link_off_outlined,
                                  size: 17,
                                  color: AppColors.muted,
                                ),
                                const SizedBox(width: 8),
                                const Expanded(
                                  child: Text(
                                    'AI 私教尚未连接',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: AppColors.muted,
                                    ),
                                  ),
                                ),
                                TextButton(
                                  onPressed: () => showDialog<void>(
                                    context: context,
                                    builder: (context) => AlertDialog(
                                      title: const Text('连接 AI 私教'),
                                      content: const Text(
                                        '请在后端 .env 中配置 AI_API_KEY、AI_BASE_URL 和 AI_MODEL。密钥保留在服务端，配置完成后刷新页面即可。',
                                      ),
                                      actions: [
                                        TextButton(
                                          onPressed: () =>
                                              Navigator.pop(context),
                                          child: const Text('知道了'),
                                        ),
                                      ],
                                    ),
                                  ),
                                  child: const Text(
                                    '连接说明',
                                    style: TextStyle(fontSize: 12),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        for (final turn in turns) ...[
                          bubble(turn['user_message'], user: true),
                          bubble(
                            turn['reply'],
                            coachId: turn['coach_id'] ?? 'steady',
                            coachName: turn['coach_name'] ?? '先前教练',
                            footer: (turn['profile_changes'] as List).isEmpty
                                ? null
                                : changes(turn['profile_changes']),
                          ),
                        ],
                        if (sending && retryMessage != null) ...[
                          bubble(retryMessage!, user: true),
                          const Padding(
                            padding: EdgeInsets.all(12),
                            child: Text('私教正在回复…'),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            ),
            if (widget.onChooseCoach != null)
              Positioned.fill(
                child: CoachPetOverlay(
                  coachId: widget.coachId,
                  name: widget.coachName,
                  onChoose: widget.onChooseCoach!,
                  mood: sending ? PetMood.thinking : petMood,
                  message: sending
                      ? personaFor(widget.coachId).thinkingLine
                      : petMessage,
                ),
              ),
          ],
        ),
      ),
      if (loading) const LinearProgressIndicator(),
      if (error != null)
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
          child: Row(
            children: [
              Expanded(
                child: Text(error!, style: const TextStyle(color: Colors.red)),
              ),
              if (!sending && !loading)
                TextButton(
                  onPressed: composer.text.trim().isEmpty ? load : send,
                  child: const Text('重试'),
                ),
            ],
          ),
        ),
      SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 780),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: composer,
                      enabled: !sending,
                      minLines: 1,
                      maxLines: 4,
                      maxLength: 4000,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => send(),
                      decoration: InputDecoration(
                        hintText: '和你的 AI 私教聊聊…',
                        counterText: '',
                        filled: true,
                        fillColor: AppColors.soft,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide.none,
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(14),
                          borderSide: BorderSide.none,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    style: IconButton.styleFrom(
                      backgroundColor: AppColors.ink,
                      foregroundColor: Colors.white,
                    ),
                    tooltip: '发送消息',
                    onPressed: loading || sending ? null : send,
                    icon: const Icon(Icons.arrow_upward),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ],
  );
}
