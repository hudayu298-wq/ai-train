import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:fluwx/fluwx.dart';

import 'session.dart';

Future<void> loginWithWechat({
  required String policyVersion,
  String inviteCode = '',
  bool bind = false,
}) async {
  if (kIsWeb || defaultTargetPlatform != TargetPlatform.android) {
    throw Exception('当前已接入安卓微信登录，请在安卓 App 中使用');
  }
  final verifier = base64UrlEncode(
    List.generate(48, (_) => Random.secure().nextInt(256)),
  ).replaceAll('=', '');
  final payload = {
    'code_challenge': sha256.convert(utf8.encode(verifier)).toString(),
    'policy_version': policyVersion,
    'invite_code': inviteCode,
    'purpose': bind ? 'bind' : 'login',
  };
  final Map<String, dynamic> start;
  if (bind) {
    start = Map<String, dynamic>.from(
      await authSession.request(
        '/auth/wechat/start',
        method: 'POST',
        body: payload,
      ),
    );
  } else {
    start = await authSession.publicPost('/auth/wechat/start', payload);
  }
  final sdk = Fluwx();
  final complete = Completer<WeChatAuthResponse>();
  final subscriber = sdk.addSubscriber((response) {
    if (response is WeChatAuthResponse &&
        response.state == start['state'] &&
        !complete.isCompleted) {
      complete.complete(response);
    }
  });
  try {
    if (!await sdk.registerApi(appId: start['app_id'], doOnIOS: false)) {
      throw Exception('微信 SDK 初始化失败');
    }
    if (!await sdk.isWeChatInstalled) throw Exception('请先安装微信');
    if (!await sdk.authBy(
      which: NormalAuth(scope: 'snsapi_userinfo', state: start['state']),
    )) {
      throw Exception('无法打开微信，请检查开放平台应用配置');
    }
    final response = await complete.future.timeout(const Duration(minutes: 3));
    if (response.errCode != 0 ||
        response.code == null ||
        response.code!.isEmpty) {
      throw Exception('微信授权已取消或未成功');
    }
    final exchange = {
      'state': start['state'],
      'code': response.code!,
      'code_verifier': verifier,
      'device_name': '安卓手机',
    };
    if (bind) {
      await authSession.request(
        '/auth/wechat/exchange',
        method: 'POST',
        body: exchange,
      );
    } else {
      await authSession.accept(
        await authSession.publicPost('/auth/wechat/exchange', exchange),
      );
    }
  } finally {
    subscriber.cancel();
  }
}
