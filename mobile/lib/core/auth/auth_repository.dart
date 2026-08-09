import 'package:dio/dio.dart';
import '../api/api_endpoints.dart';
import '../api/api_service.dart';
import 'token_storage.dart';
import '../../models/user_model.dart';

/// Authentication Repository handling login, JWT storage, role verification, and logout
class AuthRepository {
  final ApiService _apiService;

  AuthRepository(this._apiService);

  /// Authenticate user via email/username and password
  Future<UserModel> login({
    required String username,
    required String password,
  }) async {
    try {
      // /api/auth/login is declared with OAuth2PasswordRequestForm, which reads
      // an application/x-www-form-urlencoded body. A JSON map returned 422
      // "field required" for both fields on every attempt, so login could never
      // succeed.
      //
      // The contentType override is required as well as the map: ApiService
      // sets 'Content-Type: application/json' in BaseOptions.headers, and that
      // default wins over the type Dio would otherwise infer. Sending FormData
      // alone still produced a 422, because the body was encoded as a form
      // while the header continued to advertise JSON. Setting contentType on
      // the request makes the two agree.
      final response = await _apiService.post(
        ApiEndpoints.login,
        data: {
          'username': username,
          'password': password,
        },
        options: Options(contentType: Headers.formUrlEncodedContentType),
      );

      final data = response.data as Map<String, dynamic>;
      final token = data['access_token'] as String?;
      
      if (token == null || token.isEmpty) {
        throw Exception('Invalid token returned from server');
      }

      // Persist JWT securely
      await TokenStorage.saveToken(token);

      // Parse user details
      final userData = data['user'] as Map<String, dynamic>? ?? {};
      final user = UserModel.fromJson(userData);

      // Persist role
      await TokenStorage.saveUserRole(user.role.value);

      return user;
    } on DioException catch (e) {
      final errorMsg = e.response?.data?['detail'] ?? 'Login failed. Please check credentials.';
      throw Exception(errorMsg);
    }
  }

  /// Fetch authenticated current user profile
  Future<UserModel?> getCurrentUser() async {
    try {
      final token = await TokenStorage.getToken();
      if (token == null) return null;

      final response = await _apiService.get(ApiEndpoints.me);
      return UserModel.fromJson(response.data);
    } catch (_) {
      return null;
    }
  }

  // registerFcmToken was removed: it posted to /api/notifications/register-device,
  // which does not exist on this backend, and nothing ever called it. There is no
  // push-notification wiring in this app for it to belong to.

  /// Logout user and clear local session state
  Future<void> logout() async {
    try {
      await _apiService.post(ApiEndpoints.logout);
    } catch (_) {
      // Ignore logout endpoint failures (e.g. network offline)
    } finally {
      await TokenStorage.clearAll();
    }
  }
}
