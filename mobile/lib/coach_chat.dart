import 'dart:math';

import 'package:flutter/material.dart';

import 'coach_avatar.dart';

class CoachChat extends StatefulWidget {
  const CoachChat({
    super.key,
    required this.request,
    required this.onProfileChanged,
    this.refreshToken = 0,
    this.coachName = '林教练',
  });
  final Future<dynamic> Function(String, String, Object?) request;
  final Future<void> Function() onProfileChanged;
  final int refreshToken;
  final String coachName;

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

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void didUpdateWidget(covariant CoachChat oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshToken != widget.refreshToken && !sending) load();
  }

  @override
  void dispose() {
    composer.dispose();
    scroll.dispose();
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
      if ((result['profile_changes'] as List).isNotEmpty) {
        await widget.onProfileChanged();
      }
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) {
        setState(() => sending = false);
        scrollToLatest();
      }
    }
  }

  Widget bubble(String text, {bool user = false, Widget? footer}) => Align(
    alignment: user ? Alignment.centerRight : Alignment.centerLeft,
    child: Container(
      constraints: const BoxConstraints(maxWidth: 620),
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: user ? const Color(0xff244b3c) : Colors.white,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (!user) ...[
                const CoachAvatar(size: 36),
                const SizedBox(width: 10),
              ],
              Flexible(
                child: Text(
                  user ? '你' : '${widget.coachName} · AI 私教',
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: user ? Colors.white70 : const Color(0xff537164),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SelectableText(
            text,
            style: TextStyle(
              color: user ? Colors.white : const Color(0xff21372d),
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
      style: const TextStyle(fontSize: 13, color: Color(0xff537164)),
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
        child: ListView(
          controller: scroll,
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
          children: [
            Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 780),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    bubble(
                      '你好，我是你的 AI 私教${widget.coachName}。你可以聊训练目标、饮食或训练中的困惑。\n先告诉我：你目前最想达成什么目标？',
                      footer: const Text(
                        '你明确提供的画像信息会自动记录；对话及相关健身资料会发送到已配置的 AI 服务。',
                        style: TextStyle(
                          fontSize: 12,
                          color: Color(0xff64786d),
                        ),
                      ),
                    ),
                    if (configured == false)
                      bubble(
                        '私教模型尚未配置。请在电脑后端的 .env 中填写 AI_API_KEY、AI_BASE_URL 和 AI_MODEL，配置后即可开始对话。',
                      ),
                    for (final turn in turns) ...[
                      bubble(turn['user_message'], user: true),
                      bubble(
                        turn['reply'],
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
                        fillColor: Colors.white,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(20),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
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
