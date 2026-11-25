import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../coach_avatar.dart';
import '../coaches/coach_pet.dart';
import '../ui_theme.dart';
import 'session.dart';
import 'wechat_login.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});
  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final email = TextEditingController(),
      password = TextEditingController(),
      code = TextEditingController(),
      invite = TextEditingController();
  String mode = 'login';
  String? challenge, error, notice;
  bool busy = false, agreed = false, obscurePassword = true;
  Map<String, dynamic>? config;

  @override
  void initState() {
    super.initState();
    loadConfig();
  }

  Future<void> loadConfig() async {
    try {
      final response = await http
          .get(Uri.parse('$apiBase/api/auth/config'))
          .timeout(const Duration(seconds: 15));
      if (response.statusCode != 200) throw Exception('服务暂不可用');
      if (mounted) setState(() => config = jsonDecode(response.body));
    } catch (_) {
      if (mounted) setState(() => error = '无法连接服务，请检查网络后重试');
    }
  }

  @override
  void dispose() {
    for (final c in [email, password, code, invite]) {
      c.dispose();
    }
    super.dispose();
  }

  Future<void> run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      error = notice = null;
    });
    try {
      await action();
    } catch (e) {
      if (mounted) {
        setState(() => error = e.toString().replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void checkAgreement() {
    if (!agreed) throw Exception('请先阅读并同意用户协议和隐私政策');
    if (config == null) throw Exception('正在连接服务，请稍后重试');
  }

  Future<void> submit() => run(() async {
    checkAgreement();
    final address = email.text.trim();
    if (mode == 'login') {
      await authSession.accept(
        await authSession.publicPost('/auth/login', {
          'email': address,
          'password': password.text,
          'device_name': '我的手机',
        }),
      );
    } else if (challenge == null) {
      final result = await authSession.publicPost(
        mode == 'register' ? '/auth/register' : '/auth/password/forgot',
        {
          'email': address,
          if (mode == 'register') ...{
            'password': password.text,
            'policy_version': config!['policy_version'],
            'invite_code': invite.text,
          },
        },
      );
      setState(() {
        challenge = result['challenge_id'];
        notice = result['message'];
      });
    } else if (mode == 'register') {
      await authSession.accept(
        await authSession.publicPost('/auth/register/verify', {
          'challenge_id': challenge,
          'code': code.text,
          'device_name': '我的手机',
        }),
      );
    } else {
      await authSession.publicPost('/auth/password/reset', {
        'challenge_id': challenge,
        'code': code.text,
        'password': password.text,
      });
      setState(() {
        mode = 'login';
        challenge = null;
        notice = '密码已重置，请登录';
        password.clear();
      });
    }
  });

  Future<void> policy(String type) async {
    await run(() async {
      final response = await http
          .get(Uri.parse('$apiBase/api/auth/policies'))
          .timeout(const Duration(seconds: 15));
      final data = authSession.decode(response);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(type == 'privacy' ? '隐私政策' : '用户协议'),
          content: SizedBox(
            width: 520,
            child: SingleChildScrollView(
              child: SelectableText(data[type] as String),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('关闭'),
            ),
          ],
        ),
      );
    });
  }

  Widget brandMark() => Row(
    children: [
      const CoachAvatar(size: 48, coachId: 'steady'),
      const SizedBox(width: 12),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('练伴', style: Theme.of(context).textTheme.headlineSmall),
          const Text(
            'AI 私教与训练记录',
            style: TextStyle(fontSize: 12, color: AppColors.muted),
          ),
        ],
      ),
    ],
  );

  Widget brandPanel() => Padding(
    padding: const EdgeInsets.only(right: 64),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        brandMark(),
        const SizedBox(height: 40),
        Text(
          '把每一次训练，\n练成自己的进步。',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 16),
        const Text(
          '和私教聊聊目标，确认适合你的计划。\n记录实际完成的每一组，再一起回顾。',
          style: TextStyle(fontSize: 16, height: 1.8, color: AppColors.muted),
        ),
        const SizedBox(height: 28),
        const CoachPet(coachId: 'steady', size: 138, animate: false),
        const SizedBox(height: 16),
        const Text('你的训练，每一次都有记录', style: TextStyle(color: AppColors.muted)),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: LayoutBuilder(
        builder: (context, box) {
          final wide = box.maxWidth >= 1000;
          return Center(
            child: SingleChildScrollView(
              padding: EdgeInsets.all(wide ? 48 : 20),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: wide ? 1000 : 440),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    if (wide) Expanded(child: brandPanel()),
                    Flexible(
                      child: Material(
                        color: AppColors.surface,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                          side: const BorderSide(color: AppColors.line),
                        ),
                        child: Padding(
                          padding: EdgeInsets.all(wide ? 32 : 24),
                          child: AutofillGroup(
                            child: loginForm(compact: !wide),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    ),
  );

  Widget loginForm({required bool compact}) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      if (compact) ...[brandMark(), const SizedBox(height: 28)],
      Text(switch (mode) {
        'register' => '创建账号',
        'reset' => '找回密码',
        _ => '欢迎回来',
      }, style: Theme.of(context).textTheme.titleLarge),
      const SizedBox(height: 18),
      TextField(
        controller: email,
        enabled: !busy && challenge == null,
        keyboardType: TextInputType.emailAddress,
        autofillHints: const [AutofillHints.email],
        decoration: const InputDecoration(labelText: '邮箱'),
      ),
      const SizedBox(height: 12),
      if (mode != 'reset' || challenge != null) ...[
        TextField(
          controller: password,
          enabled: !busy && (challenge == null || mode == 'reset'),
          obscureText: obscurePassword,
          autofillHints: [
            mode == 'login'
                ? AutofillHints.password
                : AutofillHints.newPassword,
          ],
          decoration: InputDecoration(
            suffixIcon: IconButton(
              tooltip: obscurePassword ? '显示密码' : '隐藏密码',
              onPressed: () =>
                  setState(() => obscurePassword = !obscurePassword),
              icon: Icon(
                obscurePassword
                    ? Icons.visibility_outlined
                    : Icons.visibility_off_outlined,
                size: 20,
              ),
            ),
            labelText: mode == 'reset'
                ? '新密码（至少6个字符）'
                : mode == 'register'
                ? '密码（至少6个字符）'
                : '密码',
          ),
        ),
        const SizedBox(height: 12),
      ],
      if (config?['registration_open'] == false &&
          (mode == 'register' ||
              (mode == 'login' && config?['wechat_enabled'] == true)) &&
          challenge == null) ...[
        TextField(
          controller: invite,
          enabled: !busy,
          decoration: const InputDecoration(labelText: '邀请码（新账号需要）'),
        ),
        const SizedBox(height: 12),
      ],
      if (challenge != null) ...[
        TextField(
          controller: code,
          enabled: !busy,
          keyboardType: TextInputType.number,
          maxLength: 6,
          decoration: const InputDecoration(
            labelText: '邮件验证码',
            helperText: '10分钟内有效；最多验证5次',
          ),
        ),
        TextButton(
          onPressed: busy
              ? null
              : () => setState(() {
                  challenge = null;
                  code.clear();
                }),
          child: const Text('返回修改 / 重新发送'),
        ),
      ],
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: agreed,
        onChanged: busy ? null : (v) => setState(() => agreed = v ?? false),
        title: const Text('我已阅读并同意'),
      ),
      Wrap(
        children: [
          TextButton(
            onPressed: busy ? null : () => policy('terms'),
            child: const Text('用户协议'),
          ),
          TextButton(
            onPressed: busy ? null : () => policy('privacy'),
            child: const Text('隐私政策'),
          ),
        ],
      ),
      if (error != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(
            error!,
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ),
      if (notice != null)
        Padding(
          padding: const EdgeInsets.only(bottom: 12),
          child: Text(notice!),
        ),
      FilledButton(
        onPressed: busy || config == null ? null : submit,
        child: Text(
          busy
              ? '请稍候…'
              : mode == 'login'
              ? '登录'
              : challenge == null
              ? '发送验证码'
              : mode == 'register'
              ? '验证并注册'
              : '重置密码',
        ),
      ),
      if (mode == 'login' && config?['wechat_enabled'] == true) ...[
        const SizedBox(height: 12),
        OutlinedButton.icon(
          icon: const Icon(Icons.chat_bubble_outline),
          label: const Text('微信登录'),
          onPressed: busy || config == null
              ? null
              : () => run(() async {
                  checkAgreement();
                  if (config!['wechat_enabled'] != true) {
                    throw Exception('微信登录尚未开通，请先使用邮箱登录');
                  }
                  await loginWithWechat(
                    policyVersion: config!['policy_version'],
                    inviteCode: invite.text,
                  );
                }),
        ),
      ],
      const SizedBox(height: 12),
      Wrap(
        alignment: WrapAlignment.center,
        children: [
          for (final item in const [
            ('login', '登录'),
            ('register', '创建账号'),
            ('reset', '忘记密码'),
          ])
            if (mode != item.$1)
              TextButton(
                onPressed: busy
                    ? null
                    : () => setState(() {
                        mode = item.$1;
                        challenge = error = notice = null;
                        code.clear();
                        password.clear();
                      }),
                child: Text(item.$2),
              ),
          if (config == null)
            TextButton(onPressed: loadConfig, child: const Text('重试连接')),
        ],
      ),
    ],
  );
}
