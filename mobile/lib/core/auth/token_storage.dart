import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure Token & Credentials Storage Service for KinJo Mobile
class TokenStorage {
  static const _storage = FlutterSecureStorage();
  
  static const _keyToken = 'kinjo_jwt_token';
  // No _keyRefreshToken: the backend issues a single access token and there is
  // no refresh flow to store one for. The key was declared and never read.
  static const _keyUserRole = 'kinjo_user_role';
  static const _keyUserLang = 'kinjo_user_lang';

  static Future<void> saveToken(String token) async {
    await _storage.write(key: _keyToken, value: token);
  }

  static Future<String?> getToken() async {
    return await _storage.read(key: _keyToken);
  }

  static Future<void> saveUserRole(String role) async {
    await _storage.write(key: _keyUserRole, value: role);
  }

  static Future<String?> getUserRole() async {
    return await _storage.read(key: _keyUserRole);
  }

  static Future<void> saveLanguage(String lang) async {
    await _storage.write(key: _keyUserLang, value: lang);
  }

  static Future<String> getLanguage() async {
    return (await _storage.read(key: _keyUserLang)) ?? 'ar';
  }

  static Future<void> clearAll() async {
    await _storage.deleteAll();
  }
}
