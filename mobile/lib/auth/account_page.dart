import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'session.dart';
import 'wechat_login.dart';

class AccountPage extends StatefulWidget {
  const AccountPage({super.key});
  @override
  State<AccountPage> createState() => _AccountPageState();
}

class _AccountPageState extends State<AccountPage> {
  List<dynamic> devices = [];
  String? message;
  bool busy = false;
  bool wechatEnabled = false;
  final oldPassword = TextEditingController(),
      newPassword = TextEditingController();
  final email = TextEditingController(),
      emailPassword = TextEditingController(),
      emailCode = TextEditingController();
  String? emailChallenge;
  @override
  void initState() {
    super.initState();
    run(load);
  }

  Future<void> load() async {
    devices = await authSession.request('/auth/sessions') as List;
    final config = await authSession.request('/auth/config') as Map;
    wechatEnabled = config['wechat_enabled'] == true;
  }

  @override
  void dispose() {
    oldPassword.dispose();
    newPassword.dispose();
    email.dispose();
    emailPassword.dispose();
    emailCode.dispose();
    super.dispose();
  }

  Future<void> run(Future<void> Function() action) async {
    setState(() {
      busy = true;
      message = null;
    });
    try {
      await action();
    } catch (e) {
      message = e.toString().replaceFirst('Exception: ', '');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<bool> confirm(String text) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('确认操作'),
          content: Text(text),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('确认'),
            ),
          ],
        ),
      ) ??
      false;

  @override
  Widget build(BuildContext _) => Scaffold(
    appBar: AppBar(title: const Text('账号与安全')),
    body: ListView(
      padding: const EdgeInsets.all(20),
      children: [
        Text(
          authSession.user?['display_name'] ?? '我的账号',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        Text(authSession.user?['email'] ?? '微信账号'),
        if (busy) const LinearProgressIndicator(),
        if (message != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(message!),
          ),
        const SizedBox(height: 20),
        const Text('登录设备'),
        for (final device in devices)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.smartphone),
            title: Text(
              '${device['device_name']}${device['current'] == true ? ' · 当前设备' : ''}',
            ),
            subtitle: Text('最近使用：${device['last_used_at']}'),
            trailing: TextButton(
              onPressed: busy
                  ? null
                  : () => run(() async {
                      await authSession.request(
                        '/auth/sessions/${device['id']}',
                        method: 'DELETE',
                      );
                      if (device['current'] == true) {
                        await authSession.clear();
                      } else {
                        await load();
                      }
                    }),
              child: const Text('退出'),
            ),
          ),
        const Divider(height: 32),
        const Text('绑定或更换邮箱'),
        const SizedBox(height: 12),
        TextField(
          controller: email,
          keyboardType: TextInputType.emailAddress,
          decoration: const InputDecoration(labelText: '新邮箱'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: emailPassword,
          obscureText: true,
          decoration: const InputDecoration(labelText: '邮箱登录密码（微信账号首次绑定需设置）'),
        ),
        if (emailChallenge != null) ...[
          const SizedBox(height: 12),
          TextField(
            controller: emailCode,
            keyboardType: TextInputType.number,
            maxLength: 6,
            decoration: const InputDecoration(labelText: '邮件验证码'),
          ),
        ],
        TextButton(
          onPressed: busy
              ? null
              : () => run(() async {
                  if (emailChallenge == null) {
                    final result = await authSession.request(
                      '/me/email/start',
                      method: 'POST',
                      body: {
                        'email': email.text.trim(),
                        if (emailPassword.text.isNotEmpty)
                          'password': emailPassword.text,
                      },
                    );
                    emailChallenge = result['challenge_id'];
                    message = result['message'];
                  } else {
                    await authSession.request(
                      '/me/email/verify',
                      method: 'POST',
                      body: {
                        'challenge_id': emailChallenge,
                        'code': emailCode.text,
                      },
                    );
                    authSession.user = Map<String, dynamic>.from(
                      await authSession.request('/me'),
                    );
                    emailChallenge = null;
                    emailCode.clear();
                    emailPassword.clear();
                    message = '邮箱已更新';
                  }
                }),
          child: Text(emailChallenge == null ? '发送验证邮件' : '验证并绑定'),
        ),
        const Divider(height: 32),
        TextField(
          controller: oldPassword,
          obscureText: true,
          decoration: const InputDecoration(labelText: '当前密码'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: newPassword,
          obscureText: true,
          decoration: const InputDecoration(labelText: '新密码（至少15个字符）'),
        ),
        TextButton(
          onPressed: busy
              ? null
              : () => run(() async {
                  await authSession.request(
                    '/auth/password/change',
                    method: 'POST',
                    body: {
                      'current_password': oldPassword.text,
                      'new_password': newPassword.text,
                    },
                  );
                  await authSession.clear();
                }),
          child: const Text('修改密码并退出全部设备'),
        ),
        if (wechatEnabled)
          ListTile(
            leading: const Icon(Icons.link),
            title: const Text('绑定微信'),
            subtitle: const Text('需在重新登录后5分钟内操作'),
            onTap: busy
                ? null
                : () => run(() async {
                    await loginWithWechat(
                      policyVersion: '2026-10-18',
                      bind: true,
                    );
                    message = '微信已绑定';
                  }),
          ),
        ListTile(
          leading: const Icon(Icons.download_outlined),
          title: const Text('导出我的记录'),
          onTap: busy
              ? null
              : () => run(() async {
                  final result = await authSession.request('/me/export');
                  if (!mounted) return;
                  await showDialog<void>(
                    context: context,
                    builder: (context) => AlertDialog(
                      title: const Text('我的记录 JSON'),
                      content: SizedBox(
                        width: 520,
                        child: SingleChildScrollView(
                          child: SelectableText(
                            const JsonEncoder.withIndent('  ').convert(result),
                          ),
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () async {
                            await Clipboard.setData(
                              ClipboardData(text: jsonEncode(result)),
                            );
                          },
                          child: const Text('复制'),
                        ),
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('关闭'),
                        ),
                      ],
                    ),
                  );
                }),
        ),
        ListTile(
          leading: const Icon(Icons.logout),
          title: const Text('退出当前设备'),
          onTap: busy ? null : () => run(authSession.logout),
        ),
        ListTile(
          leading: const Icon(Icons.devices),
          title: const Text('退出全部设备'),
          onTap: busy ? null : () => run(() => authSession.logout(all: true)),
        ),
        const Divider(height: 32),
        ListTile(
          leading: const Icon(Icons.person_remove_outlined),
          title: const Text('注销账号'),
          subtitle: const Text('清除个人记录与媒体；历史备份按保留周期清除'),
          onTap: busy
              ? null
              : () => run(() async {
                  if (!await confirm(
                    '确认注销账号并清除个人数据？此操作无法撤销。请确保在最近5分钟内重新登录过。',
                  )) {
                    return;
                  }
                  await authSession.request('/me', method: 'DELETE');
                  await authSession.clear();
                }),
        ),
      ],
    ),
  );
}
