import 'package:flutter/foundation.dart' show kIsWeb;

/// KinJo API Endpoints Registry
class ApiEndpoints {
  /// Base backend URL.
  ///
  /// 10.0.2.2 is the Android emulator's alias for the host machine's loopback.
  /// It does not resolve anywhere else — in a browser or on desktop it is a
  /// dead address, so every request failed before it left the client. Pick the
  /// address that is actually reachable from the platform being run on.
  static String get baseUrl =>
      kIsWeb ? 'http://127.0.0.1:8000' : 'http://10.0.2.2:8000';

  // Auth & Account
  static const String login = '/api/auth/login';
  static const String token = '/token';
  static const String logout = '/api/auth/logout';

  /// Current user. `/api/me` was declared here but has never existed on the
  /// backend, and AuthRepository.getCurrentUser swallows every exception, so a
  /// stored session silently failed to restore on each launch and the user was
  /// sent back to the login screen with no error shown.
  static const String me = '/api/users/me';

  // Parent Endpoints
  static const String parentDashboard = '/api/parent/dashboard';
  static const String parentChildren = '/api/parent/children';
  static const String parentAttendance = '/api/parent/attendance';
  static const String parentEnrollments = '/api/parent/enrollments';
  static const String parentProfile = '/api/parent/profile';
  static String childDailyReports(int childId) => '/api/daily-reports/child/$childId';
  static const String submitAbsenceRequest = '/api/attendance/absence-requests';

  // Supervisor Endpoints
  static const String supervisorDashboard = '/api/supervisor/dashboard';
  static const String supervisorChildren = '/api/supervisor/children';
  static const String supervisorMyClasses = '/api/supervisor/my-classes';
  static const String supervisorObservations = '/api/supervisor/observations';

  // Manager Endpoints
  static const String managerDashboard = '/api/manager/dashboard';
  static const String managerDailyReports = '/api/manager/daily-reports';

  // Removed: /api/supervisor/performance, /api/manager/absence-requests,
  // /api/manager/benchmarking and /api/notifications/register-device were all
  // declared here but return 404 — this registry listed 22 endpoints of which 5
  // did not exist on the backend. Nothing referenced them, so they were a map
  // of a service that isn't there. Re-add each one with the code that calls it,
  // after checking it against /openapi.json.

  // Messaging & Notifications
  static const String messages = '/api/messages';
  static const String notifications = '/api/notifications';
  static const String tasks = '/api/tasks';
}
