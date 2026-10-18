import 'package:flutter/material.dart';

import '../app.dart';
import '../reminders/coach_reminders.dart';
import 'login_page.dart';
import 'session.dart';

class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool clearing = true;
  String? startupError;
  @override
  void initState() {
    super.initState();
    authSession.addListener(changed);
    start();
  }

  Future<void> start() async {
    setState(() {
      clearing = true;
      startupError = null;
    });
    try {
      await CoachReminders.clearLocalSession();
      if (!authSession.ready) await authSession.restore();
    } catch (_) {
      if (mounted) startupError = '启动准备失败，请重试';
    } finally {
      if (mounted) setState(() => clearing = false);
    }
  }

  void changed() {
    if (authSession.user == null) {
      setState(() {
        clearing = true;
        startupError = null;
      });
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) Navigator.of(context).popUntil((route) => route.isFirst);
      });
      CoachReminders.clearLocalSession().then(
        (_) {
          if (mounted) setState(() => clearing = false);
        },
        onError: (Object error, StackTrace stack) {
          if (mounted) {
            setState(() {
              clearing = false;
              startupError = '启动准备失败，请重试';
            });
          }
        },
      );
    } else if (mounted) {
      setState(() {});
    }
  }

  @override
  void dispose() {
    authSession.removeListener(changed);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (startupError != null) {
      return Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(startupError!),
              const SizedBox(height: 16),
              FilledButton(onPressed: start, child: const Text('重试')),
            ],
          ),
        ),
      );
    }
    if (!authSession.ready || clearing) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (authSession.user == null) return const LoginPage();
    return Home(key: ValueKey(authSession.user!['id']));
  }
}
