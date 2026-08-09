import 'dart:io';
import 'package:dio/dio.dart';
import 'api_endpoints.dart';
import '../auth/token_storage.dart';

/// Normalized Exception for KinJo API Errors
class ApiException implements Exception {
  final int? statusCode;
  final String message;
  final dynamic detail;

  ApiException({
    this.statusCode,
    required this.message,
    this.detail,
  });

  bool get isRateLimited => statusCode == 429;
  bool get isUnauthorized => statusCode == 401;
  bool get isForbidden => statusCode == 403;
  bool get isNotFound => statusCode == 404;
  bool get isConflict => statusCode == 409;
  bool get isValidationError => statusCode == 422;

  @override
  String toString() => message;
}

/// Production-ready Dio HTTP Network Service Client for KinJo FastAPI Backend
class ApiService {
  late final Dio _dio;

  ApiService({String? baseUrl}) {
    _dio = Dio(
      BaseOptions(
        baseUrl: baseUrl ?? ApiEndpoints.baseUrl,
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 15),
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
      ),
    );

    // Inject Auth & Language Interceptors
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          // Inject JWT Authorization Bearer token
          final token = await TokenStorage.getToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }

          // Inject Language header ('ar' or 'en')
          final lang = await TokenStorage.getLanguage();
          options.headers['Accept-Language'] = lang;
          options.headers['X-UI-Language'] = lang;

          return handler.next(options);
        },
        onError: (DioException error, handler) async {
          if (error.response?.statusCode == 401) {
            await TokenStorage.clearAll();
          }
          return handler.next(error);
        },
      ),
    );
  }

  ApiException normalizeError(dynamic error) {
    if (error is ApiException) return error;

    if (error is DioException) {
      final statusCode = error.response?.statusCode;
      final rawData = error.response?.data;
      String message = 'حدث خطأ في الاتصال بالسيرفر. يُرجى التثبت من شبكة الإنترنِت والتعاوُد.';

      if (statusCode == 429) {
        message = 'لقد تجاوزت عدد المحاولات المسموح بها. يُرجى الانتظار قليلاً ثم المحاولة مرة أخرى.';
      } else if (statusCode == 401) {
        message = 'اسم المستخدم أو كلمة المرور غير صحيحة.';
      } else if (statusCode == 403) {
        message = 'غير مصرح لك بإجراء هذه العملية.';
      } else if (statusCode == 404) {
        message = 'المورد المطلوب غير موجود.';
      } else if (statusCode == 409) {
        message = 'يوجد سجل مكرر أو طلب متداخل بالفعل.';
      } else if (rawData != null) {
        if (rawData is Map && rawData.containsKey('detail')) {
          final detail = rawData['detail'];
          if (detail is String) {
            message = detail;
          } else if (detail is Map && detail.containsKey('message')) {
            message = detail['message'].toString();
          }
        }
      } else if (error.error is SocketException) {
        message = 'تعذّر الاتصال بالخادم. يُرجى التحقق من اتصال الإنترنت.';
      }

      return ApiException(
        statusCode: statusCode,
        message: message,
        detail: rawData,
      );
    }

    return ApiException(message: error.toString());
  }

  // GET Request
  Future<Response> get(
    String path, {
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await _dio.get(
        path,
        queryParameters: queryParameters,
        options: options,
      );
    } catch (e) {
      throw normalizeError(e);
    }
  }

  // POST Request
  Future<Response> post(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await _dio.post(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
    } catch (e) {
      throw normalizeError(e);
    }
  }

  // PUT Request
  Future<Response> put(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await _dio.put(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
    } catch (e) {
      throw normalizeError(e);
    }
  }

  // DELETE Request
  Future<Response> delete(
    String path, {
    dynamic data,
    Map<String, dynamic>? queryParameters,
    Options? options,
  }) async {
    try {
      return await _dio.delete(
        path,
        data: data,
        queryParameters: queryParameters,
        options: options,
      );
    } catch (e) {
      throw normalizeError(e);
    }
  }
}
