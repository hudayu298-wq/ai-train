import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const apiBase = String.fromEnvironment(
  'API_BASE',
  defaultValue: 'http://127.0.0.1:8000',
);
var authSession = AuthSession();

class AuthSession extends ChangeNotifier {
  AuthSession({http.Client? client, FlutterSecureStorage? storage})
    : client = client ?? http.Client(),
      storage = storage ?? const FlutterSecureStorage();
  final http.Client client;
  final FlutterSecureStorage storage;
  Map<String, dynamic>? user;
  String? _access, _refresh;
  DateTime _expiry = DateTime.fromMillisecondsSinceEpoch(0);
  Future<void>? _refreshing;
  int _generation = 0;
  bool ready = false;
  String? restoreError;
  String get _key => 'liftlab.refresh.v1.$apiBase';

  Future<Map<String, dynamic>> publicPost(
    String path,
    Map<String, dynamic> body,
  ) async {
    final response = await client
        .post(
          Uri.parse('$apiBase/api$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(const Duration(seconds: 40));
    return decode(response);
  }

  Map<String, dynamic> decode(http.Response response) {
    final dynamic data;
    try {
      data = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      throw Exception('服务响应异常，请稍后重试');
    }
    if (response.statusCode >= 400) {
      throw Exception(
        data is Map && data['detail'] is String ? data['detail'] : '请求失败，请检查输入',
      );
    }
    return Map<String, dynamic>.from(data as Map);
  }

  Future<void> restore() async {
    try {
      // Browser preview deliberately keeps refresh credentials in memory only.
      _refresh = kIsWeb ? null : await storage.read(key: _key);
      if (_refresh != null) await _rotate();
    } catch (_) {
      restoreError = '自动登录暂不可用，请重新登录';
    } finally {
      ready = true;
      notifyListeners();
    }
  }

  Future<void> accept(
    Map<String, dynamic> result, {
    bool refreshed = false,
  }) async {
    if (!refreshed) _generation++;
    _access = result['access_token'] as String;
    _refresh = result['refresh_token'] as String;
    _expiry = DateTime.now().add(
      Duration(seconds: result['expires_in'] as int),
    );
    user = Map<String, dynamic>.from(result['user']);
    ready = true;
    if (!kIsWeb) {
      try {
        await storage.write(key: _key, value: _refresh);
      } catch (_) {
        await clear();
        throw Exception('无法安全保存登录状态，请检查设备安全存储');
      }
    }
    notifyListeners();
  }

  Future<void> _rotate() async {
    final generation = _generation;
    final token = _refresh;
    if (token == null) throw Exception('请先登录');
    try {
      final response = await client
          .post(
            Uri.parse('$apiBase/api/auth/refresh'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'refresh_token': token}),
          )
          .timeout(const Duration(seconds: 20));
      if (generation != _generation) throw Exception('登录状态已变化');
      if (response.statusCode == 401) {
        await clear();
        throw Exception('登录已失效，请重新登录');
      }
      final result = decode(response);
      await accept(result, refreshed: true);
    } catch (_) {
      rethrow;
    }
  }

  Future<void> ensureAccess() async {
    if (_access != null &&
        _expiry.isAfter(DateTime.now().add(const Duration(seconds: 60)))) {
      return;
    }
    if (_refreshing != null) return _refreshing!;
    final pending = _rotate();
    _refreshing = pending;
    try {
      await pending;
    } finally {
      if (identical(_refreshing, pending)) _refreshing = null;
    }
  }

  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    await ensureAccess();
    final generation = _generation;
    request.headers['Authorization'] = 'Bearer $_access';
    final response = await client.send(request);
    if (generation != _generation) throw Exception('登录状态已变化，请重新操作');
    if (response.statusCode == 401) {
      await clear();
      throw Exception('登录已失效，请重新登录');
    }
    // Mutating and billable requests are never automatically replayed.
    return response;
  }

  Future<dynamic> request(
    String path, {
    String method = 'GET',
    Object? body,
  }) async {
    final request = http.Request(method, Uri.parse('$apiBase/api$path'));
    if (body != null) {
      request.headers['Content-Type'] = 'application/json';
      request.body = jsonEncode(body);
    }
    final response = await http.Response.fromStream(await send(request))
        .timeout(const Duration(seconds: 30));
    final data = jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode >= 400) {
      throw Exception(data['detail'] is String ? data['detail'] : '请求失败');
    }
    return data;
  }

  Future<void> logout({bool all = false}) async {
    // If revocation fails, retain the session so the user can retry; don't imply server logout succeeded.
    await request(all ? '/auth/logout-all' : '/auth/logout', method: 'POST');
    await clear();
  }

  Future<void> clear() async {
    _generation++;
    _access = _refresh = null;
    user = null;
    try {
      if (!kIsWeb) await storage.delete(key: _key);
    } finally {
      notifyListeners();
    }
  }
}
