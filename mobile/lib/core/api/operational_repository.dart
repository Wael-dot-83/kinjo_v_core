import 'api_endpoints.dart';
import 'api_service.dart';
import '../../models/roster_model.dart';
import '../../models/absence_request_model.dart';

/// Repository for operational workflows across Supervisor, Manager, and Parent roles.
class OperationalRepository {
  final ApiService _api;

  OperationalRepository(this._api);

  // ── Supervisor Operations ──────────────────────────────────────────────────

  /// Get list of children assigned to supervisor's classes
  Future<List<Map<String, dynamic>>> getSupervisorChildren() async {
    final response = await _api.get(ApiEndpoints.supervisorChildren);
    final data = response.data;
    if (data is Map<String, dynamic> && data['children'] is List) {
      return (data['children'] as List)
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();
    }
    return [];
  }

  /// Submit batch daily reports for supervisor's class roster.
  /// Handles HTTP 207 Multi-Status response explicitly.
  Future<RosterBatchResponseModel> submitBatchDailyReports(
      RosterBatchRequestModel payload) async {
    final response = await _api.post(
      ApiEndpoints.batchDailyReports,
      data: payload.toJson(),
    );
    final data = response.data as Map<String, dynamic>;
    return RosterBatchResponseModel.fromJson(data);
  }

  /// Create a single daily report
  Future<Map<String, dynamic>> createSingleDailyReport(
      Map<String, dynamic> payload) async {
    final response = await _api.post(
      ApiEndpoints.createDailyReport,
      data: payload,
    );
    return (response.data as Map).cast<String, dynamic>();
  }

  // ── Manager Operations ─────────────────────────────────────────────────────

  /// Get absence requests list (Manager / Parent view)
  Future<List<AbsenceRequestModel>> getAbsenceRequests({String? status}) async {
    final Map<String, dynamic> query = {};
    if (status != null && status.isNotEmpty) {
      query['status'] = status;
    }
    final response = await _api.get(
      ApiEndpoints.absenceRequests,
      queryParameters: query,
    );
    final list = (response.data as List?) ?? [];
    return list
        .map((e) => AbsenceRequestModel.fromJson((e as Map).cast<String, dynamic>()))
        .toList();
  }

  /// Approve an absence request (Manager only)
  Future<void> approveAbsenceRequest(int requestId) async {
    await _api.post(ApiEndpoints.approveAbsenceRequest(requestId));
  }

  /// Reject an absence request (Manager only)
  Future<void> rejectAbsenceRequest(int requestId) async {
    await _api.post(ApiEndpoints.rejectAbsenceRequest(requestId));
  }

  /// Get daily reports list for review (Manager only)
  Future<List<Map<String, dynamic>>> getManagerDailyReports() async {
    final response = await _api.get(ApiEndpoints.managerDailyReports);
    final data = response.data;
    if (data is List) {
      return data.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
    }
    return [];
  }

  /// Approve daily report (Manager only)
  Future<void> approveDailyReport(int reportId) async {
    await _api.post(ApiEndpoints.approveDailyReport(reportId));
  }

  // ── Parent Operations ──────────────────────────────────────────────────────

  /// Submit a new absence request (Parent only)
  Future<Map<String, dynamic>> submitAbsenceRequest({
    required int childId,
    required String startDate,
    required String endDate,
    required String reason,
  }) async {
    final response = await _api.post(
      ApiEndpoints.absenceRequests,
      data: {
        'child_id': childId,
        'start_date': startDate,
        'end_date': endDate,
        'reason': reason,
      },
    );
    return (response.data as Map).cast<String, dynamic>();
  }

  /// Get child's daily reports history (Parent / Supervisor / Manager)
  Future<List<Map<String, dynamic>>> getChildDailyReports(int childId) async {
    final response = await _api.get(ApiEndpoints.childDailyReports(childId));
    final data = response.data;
    if (data is List) {
      return data.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
    }
    return [];
  }

  /// Get parent's registered children with full details
  Future<List<Map<String, dynamic>>> getParentChildren() async {
    final response = await _api.get(ApiEndpoints.parentChildren);
    final data = response.data;
    if (data is Map<String, dynamic> && data['children'] is List) {
      return (data['children'] as List)
          .whereType<Map>()
          .map((e) => e.cast<String, dynamic>())
          .toList();
    }
    return [];
  }
}
