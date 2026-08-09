import 'package:flutter/foundation.dart' show kIsWeb;

/// KinJo Canonical API Endpoints Registry
class ApiEndpoints {
  /// Base backend URL (resolves dynamically per platform).
  static String get baseUrl =>
      kIsWeb ? 'http://127.0.0.1:8000' : 'http://10.0.2.2:8000';

  // Auth & Account
  static const String login = '/api/auth/login';
  static const String token = '/token';
  static const String logout = '/api/auth/logout';
  static const String me = '/api/users/me';

  // Daily Reports
  static const String batchDailyReports = '/api/daily-reports/batch';
  static const String createDailyReport = '/api/daily-reports/create';
  static String childDailyReports(int childId) => '/api/daily-reports/child/$childId';
  static String submitDailyReport(int reportId) => '/api/daily-reports/$reportId/submit';
  static String approveDailyReport(int reportId) => '/api/daily-reports/$reportId/approve';
  static const String managerDailyReports = '/api/manager/daily-reports';

  // Supervisor Endpoints
  static const String supervisorDashboard = '/api/supervisor/dashboard';
  static const String supervisorChildren = '/api/supervisor/children';
  static const String supervisorMyClasses = '/api/supervisor/my-classes';
  static const String supervisorObservations = '/api/supervisor/observations';

  // Manager Endpoints
  static const String managerDashboard = '/api/manager/dashboard';

  // Parent Endpoints
  static const String parentDashboard = '/api/parent/dashboard';
  static const String parentChildren = '/api/parent/children';
  static const String parentAttendance = '/api/parent/attendance';
  static const String parentEnrollments = '/api/parent/enrollments';
  static const String parentProfile = '/api/parent/profile';

  // Absence Requests
  static const String absenceRequests = '/api/attendance/absence-requests';
  static String getAbsenceRequest(int id) => '/api/attendance/absence-requests/$id';
  static String approveAbsenceRequest(int id) => '/api/attendance/absence-requests/$id/approve';
  static String rejectAbsenceRequest(int id) => '/api/attendance/absence-requests/$id/reject';

  // Attendance Check-in / Check-out
  static const String checkIn = '/api/attendance/check-in';
  static const String checkOut = '/api/attendance/check-out';

  // Messaging
  static const String messages = '/api/messages';
}
