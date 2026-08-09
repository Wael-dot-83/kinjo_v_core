import 'package:dio/dio.dart';

import 'api_endpoints.dart';
import 'api_service.dart';

/// Loads the one payload each role's home screen is built from.
///
/// Every screen previously rendered hard-coded text and called nothing, so the
/// app showed the same numbers whatever the data said. Each method returns the
/// decoded map and lets DioException surface, so the screen can tell "failed"
/// apart from "loaded, but empty" instead of silently showing zeros.
class DashboardRepository {
  final ApiService _api;

  DashboardRepository(this._api);

  Future<Map<String, dynamic>> parentDashboard() =>
      _getMap(ApiEndpoints.parentDashboard);

  Future<Map<String, dynamic>> supervisorDashboard() =>
      _getMap(ApiEndpoints.supervisorDashboard);

  Future<Map<String, dynamic>> managerDashboard() =>
      _getMap(ApiEndpoints.managerDashboard);

  /// The supervisor's class list, used for the roster preview.
  Future<List<Map<String, dynamic>>> supervisorChildren() async {
    final data = await _getMap(ApiEndpoints.supervisorChildren);
    return _listOf(data['children']);
  }

  Future<Map<String, dynamic>> _getMap(String path) async {
    final Response response = await _api.get(path);
    final data = response.data;
    if (data is Map<String, dynamic>) return data;
    return <String, dynamic>{};
  }

  static List<Map<String, dynamic>> _listOf(dynamic raw) {
    if (raw is! List) return const [];
    return raw.whereType<Map>().map((e) => e.cast<String, dynamic>()).toList();
  }
}
