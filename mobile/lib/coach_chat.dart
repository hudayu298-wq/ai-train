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
  final composerFocus = FocusNode();
  final scroll = ScrollController();
  final List<Map<String, dynamic>> turns = [];
  bool loading = true, sending = false;
  bool? configured;
  String? error, retryId, retryMessage;
  Timer? petReaction;
  PetMood petMood = PetMood.idle;
  String? petMessage;
  int contentEpoch = 0, loadSequence = 0;
  bool reloadAfterSend = false;

  @override
  void initState() {
    super.initState();
    load();
  }

  @override
  void didUpdateWidget(covariant CoachChat oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refreshToken != widget.refreshToken) {
      contentEpoch++;
      turns.clear();
      retryId = retryMessage = error = petMessage = null;
      petReaction?.cancel();
      petMood = PetMood.idle;
      if (sending) {
        reloadAfterSend = true;
      } else {
        load();
      }
    }
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
    composerFocus.dispose();
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
    final epoch = contentEpoch, sequence = ++loadSequence;
    setState(() {
      loading = true;
      error = null;
    });
    try {
      final results = await Future.wait([
        widget.request('/coach/messages', 'GET', null),
        widget.request('/coach/status', 'GET', null),
      ]);
      if (!mounted || epoch != contentEpoch || sequence != loadSequence) return;
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
      if (turns.isNotEmpty) scrollToLatest();
    } catch (e) {
      if (mounted && epoch == contentEpoch && sequence == loadSequence) {
        setState(() => error = '$e');
      }
    } finally {
      if (mounted && epoch == contentEpoch && sequence == loadSequence) {
        setState(() => loading = false);
      }
    }
  }

  void finishSending() {
    if (!mounted) return;
    setState(() => sending = false);
    if (reloadAfterSend) {
      reloadAfterSend = false;
      unawaited(load());
    }
  }

  Future<void> send() async {
    final epoch = contentEpoch;
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
        await widget.request('/agent/runs', 'POST', {
          'message': message,
          'request_id': requestId,
          'coach_id': widget.coachId,
          'coach_name': widget.coachName,
        }),
      );
      if (!mounted || epoch != contentEpoch) return;
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
      if (mounted && epoch == contentEpoch) {
        setState(() => error = '$e');
        react(PetMood.worried, '这次没有连接好，可以稍后重试。');
      }
    } finally {
      if (mounted) {
        finishSending();
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
      margin: const EdgeInsets.symmetric(vertical: 12),
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
              fontSize: 15,
              height: 1.65,
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

  Future<void> decide(Map action, bool approved) async {
    final epoch = contentEpoch;
    setState(() => sending = true);
    try {
      await widget.request('/agent/actions/${action['id']}/decision', 'POST', {
        'approved': approved,
      });
      if (!mounted || epoch != contentEpoch) return;
      await widget.onProfileChanged();
      await load();
    } catch (e) {
      if (mounted && epoch == contentEpoch) {
        setState(() => error = '$e');
      }
    } finally {
      finishSending();
    }
  }

  Future<void> feedback(Map turn) async {
    String category = 'helpful';
    bool share = false;
    final result = await showDialog<Map>(
      context: context,
      builder: (c) => StatefulBuilder(
        builder: (c, change) => AlertDialog(
          title: const Text('给私教反馈'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: category,
                items: [
                  for (final e in {
                    'helpful': '有帮助',
                    'wrong_fact': '事实有误',
                    'tool_failure': '操作失败',
                    'too_long': '太冗长',
                    'missing_evidence': '缺少依据',
                    'not_actionable': '建议难执行',
                  }.entries)
                    DropdownMenuItem(value: e.key, child: Text(e.value)),
                ],
                onChanged: (v) => change(() => category = v!),
              ),
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                value: share,
                title: const Text('自愿共享反馈分类用于改进'),
                subtitle: const Text('只共享分类计数，不共享原始对话'),
                onChanged: (v) => change(() => share = v == true),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(c),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(c, {
                'category': category,
                'share_for_improvement': share,
              }),
              child: const Text('提交'),
            ),
          ],
        ),
      ),
    );
    if (result != null) {
      try {
        await widget.request(
          '/agent/runs/${turn['run_id']}/feedback',
          'POST',
          result,
        );
        if (mounted) {
          ScaffoldMessenger.of(context)
              .showSnackBar(const SnackBar(content: Text('反馈已记录')));
        }
      } catch (e) {
        if (mounted) {
          setState(() => error = '$e');
        }
      }
    }
  }

  Widget agentFooter(Map turn) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if ((turn['profile_changes'] as List? ?? []).isNotEmpty)
        changes(turn['profile_changes']),
      for (final action in turn['actions'] ?? [])
        Card(
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  action['preview']['title'],
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                for (final line in action['preview']['lines']) Text(line),
                if (action['status'] == 'pending')
                  Wrap(
                    spacing: 8,
                    children: [
                      FilledButton(
                        onPressed: sending ? null : () => decide(action, true),
                        child: const Text('确认保存'),
                      ),
                      TextButton(
                        onPressed: sending ? null : () => decide(action, false),
                        child: const Text('取消'),
                      ),
                    ],
                  )
                else
                  Text(switch (action['status']) {
                    'committed' => '已保存',
                    'cancelled' => '已取消',
                    'committing' => '保存中，稍后刷新',
                    _ => '草稿已失效，请重新生成',
                  }),
                if (action['followup'] != null)
                  Text(
                    action['followup']['result']?['summary'] ??
                        action['followup']['error'] ??
                        '私教复盘排队中，可稍后刷新',
                  ),
              ],
            ),
          ),
        ),
      for (final c in turn['citations'] ?? [])
        ExpansionTile(
          tilePadding: EdgeInsets.zero,
          title: Text(c['title']),
          children: [
            Text(
              '${c['claim']}\n适用人群：${c['population']}\n局限：${c['limitations']}',
            ),
            SelectableText(c['url']),
          ],
        ),
      if (turn['status'] == 'failed')
        TextButton(
          onPressed: sending
              ? null
              : () async {
                  final epoch = contentEpoch;
                  setState(() => sending = true);
                  try {
                    final result = Map<String, dynamic>.from(
                      await widget.request(
                        '/agent/runs/${turn['run_id']}/resume',
                        'POST',
                        {},
                      ),
                    );
                    if (mounted && epoch == contentEpoch) {
                      setState(() {
                        final index = turns.indexWhere(
                          (t) => t['run_id'] == turn['run_id'],
                        );
                        if (index >= 0) {
                          turns[index] = result;
                        }
                      });
                    }
                  } catch (e) {
                    if (mounted && epoch == contentEpoch) {
                      setState(() => error = '$e');
                    }
                  } finally {
                    finishSending();
                  }
                },
          child: const Text('恢复未完成任务'),
        ),
      if (turn['run_id'] != null)
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: sending ? null : () => feedback(turn),
            icon: const Icon(Icons.rate_review_outlined, size: 16),
            label: const Text('反馈'),
          ),
        ),
      if (turn['versions'] != null)
        Text(
          '知识版本 ${turn['versions']['knowledge']} · ${turn['versions']['harness']}',
          style: const TextStyle(fontSize: 12, color: AppColors.muted),
        ),
    ],
  );

  Widget welcome() => Padding(
    padding: const EdgeInsets.only(top: 16, bottom: 24),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            CoachAvatar(size: 44, coachId: widget.coachId),
            const SizedBox(width: 12),
            Text(
              '${widget.coachName} · AI 私教',
              style: const TextStyle(fontSize: 14, color: AppColors.muted),
            ),
          ],
        ),
        const SizedBox(height: 24),
        Semantics(
          header: true,
          child: Text(
            '今天的训练，从这里开始',
            style: Theme.of(context).textTheme.headlineSmall,
          ),
        ),
        const SizedBox(height: 12),
        Text(
          personaFor(widget.coachId).greeting
              .replaceFirst(personaFor(widget.coachId).name, widget.coachName),
          style: const TextStyle(fontSize: 15, height: 1.65),
        ),
        const SizedBox(height: 24),
        for (final topic in const [
          ('安排训练', '根据我的画像，准备下一次训练', '请先查看我的画像，告诉我还需要补充哪些信息才能制定训练计划。'),
          ('看看饮食', '对照今天已记录的摄入与目标', '请根据我今天已确认的饮食记录，帮我看看营养摄入。'),
          ('训练复盘', '回顾已确认的表现与训练感受', '请查看我最近一次已确认的训练，帮我总结表现和下次需要留意的地方。'),
        ])
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Material(
              color: AppColors.surface,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8),
                side: const BorderSide(color: AppColors.line),
              ),
              clipBehavior: Clip.antiAlias,
              child: ListTile(
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
                title: Text(
                  topic.$1,
                  style: const TextStyle(fontWeight: FontWeight.w500),
                ),
                subtitle: Text(
                  topic.$2,
                  style: const TextStyle(fontSize: 12, color: AppColors.muted),
                ),
                trailing: const Icon(Icons.north_east, size: 18),
                enabled: !sending && !loading,
                onTap: () {
                  composer.text = topic.$3;
                  composer.selection = TextSelection.collapsed(
                    offset: composer.text.length,
                  );
                  composerFocus.requestFocus();
                },
              ),
            ),
          ),
        const SizedBox(height: 8),
        const Text(
          '饮食、训练记录与计划启用，都会先请你确认。',
          style: TextStyle(fontSize: 12, color: AppColors.muted),
        ),
        TextButton.icon(
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
          icon: const Icon(Icons.info_outline, size: 16),
          label: const Text('对话与画像'),
        ),
      ],
    ),
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
                    constraints: const BoxConstraints(maxWidth: 860),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (turns.isEmpty && !loading) welcome(),
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
                                        '私教服务尚未配置完成，请联系管理员连接 AI 服务后重试。你的已保存记录仍可在对应页面查看。',
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
                            footer: agentFooter(turn),
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
                child: Text(
                  error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
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
          padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 860),
              child: Container(
                padding: const EdgeInsets.fromLTRB(8, 4, 8, 4),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  border: Border.all(color: AppColors.line),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: composer,
                        focusNode: composerFocus,
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
                          fillColor: AppColors.surface,
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
      ),
    ],
  );
}
