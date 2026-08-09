import 'package:flutter/material.dart';
import '../core/api/api_service.dart';
import '../core/api/operational_repository.dart';
import '../core/theme/app_theme.dart';
import '../models/absence_request_model.dart';
import '../models/user_model.dart';

/// Manager Operational Screen — Absence Requests Review & Daily Report Approvals
class ManagerOperationsScreen extends StatefulWidget {
  final UserModel user;

  const ManagerOperationsScreen({super.key, required this.user});

  @override
  State<ManagerOperationsScreen> createState() => _ManagerOperationsScreenState();
}

class _ManagerOperationsScreenState extends State<ManagerOperationsScreen> with SingleTickerProviderStateMixin {
  late final OperationalRepository _repo = OperationalRepository(ApiService());
  late final TabController _tabController = TabController(length: 2, vsync: this);

  bool _loadingAbsences = true;
  bool _loadingReports = true;
  String? _absenceError;
  String? _reportsError;

  List<AbsenceRequestModel> _absenceRequests = [];
  List<Map<String, dynamic>> _dailyReports = [];

  @override
  void initState() {
    super.initState();
    _loadAbsenceRequests();
    _loadDailyReports();
  }

  Future<void> _loadAbsenceRequests() async {
    setState(() {
      _loadingAbsences = true;
      _absenceError = null;
    });

    try {
      final requests = await _repo.getAbsenceRequests();
      if (!mounted) return;
      setState(() {
        _absenceRequests = requests;
        _loadingAbsences = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _absenceError = e.toString();
        _loadingAbsences = false;
      });
    }
  }

  Future<void> _loadDailyReports() async {
    setState(() {
      _loadingReports = true;
      _reportsError = null;
    });

    try {
      final reports = await _repo.getManagerDailyReports();
      if (!mounted) return;
      setState(() {
        _dailyReports = reports;
        _loadingReports = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _reportsError = e.toString();
        _loadingReports = false;
      });
    }
  }

  Future<void> _approveAbsence(AbsenceRequestModel req) async {
    try {
      await _repo.approveAbsenceRequest(req.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تم قبول طلب الإجازة بنجاح.')),
      );
      _loadAbsenceRequests();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: AppTheme.danger),
      );
    }
  }

  Future<void> _rejectAbsence(AbsenceRequestModel req) async {
    try {
      await _repo.rejectAbsenceRequest(req.id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تم رفض طلب الإجازة.')),
      );
      _loadAbsenceRequests();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: AppTheme.danger),
      );
    }
  }

  Future<void> _approveReport(int reportId) async {
    try {
      await _repo.approveDailyReport(reportId);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تم اعتماد التقرير اليومي وإرساله لولي الأمر.')),
      );
      _loadDailyReports();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString()), backgroundColor: AppTheme.danger),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('عمليات الإدارة ومراجعة الطلبات'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.event_busy), text: 'طلبات الإجازة'),
            Tab(icon: Icon(Icons.description), text: 'التقارير اليومية'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildAbsenceTab(),
          _buildReportsTab(),
        ],
      ),
    );
  }

  Widget _buildAbsenceTab() {
    if (_loadingAbsences) return const Center(child: CircularProgressIndicator());
    if (_absenceError != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_absenceError!),
            ElevatedButton(onPressed: _loadAbsenceRequests, child: const Text('إعادة المحاولة')),
          ],
        ),
      );
    }

    if (_absenceRequests.isEmpty) {
      return const Center(child: Text('لا توجد طلبات إجازة قيد الانتظار حالياً.'));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _absenceRequests.length,
      itemBuilder: (ctx, idx) {
        final req = _absenceRequests[idx];
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      req.childName ?? 'طفل #${req.childId}',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                    Chip(
                      label: Text(req.statusArabic, style: const TextStyle(fontSize: 12)),
                      backgroundColor: req.isPending
                          ? AppTheme.accent.withOpacity(0.2)
                          : (req.isApproved ? Colors.green.withOpacity(0.2) : Colors.red.withOpacity(0.2)),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text('الفترة: من ${req.startDate} إلى ${req.endDate}'),
                Text('السبب: ${req.reason}', style: const TextStyle(color: Colors.grey)),
                if (req.parentName != null) Text('ولي الأمر: ${req.parentName}', style: const TextStyle(fontSize: 12, color: Colors.grey)),
                if (req.isPending) ...[
                  const SizedBox(height: 12),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      OutlinedButton.icon(
                        onPressed: () => _rejectAbsence(req),
                        icon: const Icon(Icons.close, color: AppTheme.danger),
                        label: const Text('رفض', style: TextStyle(color: AppTheme.danger)),
                      ),
                      const SizedBox(width: 12),
                      ElevatedButton.icon(
                        onPressed: () => _approveAbsence(req),
                        icon: const Icon(Icons.check),
                        label: const Text('موافقة'),
                      ),
                    ],
                  )
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildReportsTab() {
    if (_loadingReports) return const Center(child: CircularProgressIndicator());
    if (_reportsError != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_reportsError!),
            ElevatedButton(onPressed: _loadDailyReports, child: const Text('إعادة المحاولة')),
          ],
        ),
      );
    }

    if (_dailyReports.isEmpty) {
      return const Center(child: Text('لا توجد تقارير يومية قيد المراجعة.'));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _dailyReports.length,
      itemBuilder: (ctx, idx) {
        final r = _dailyReports[idx];
        final id = r['id'] is num ? (r['id'] as num).toInt() : 0;
        final childName = r['child_name']?.toString() ?? 'طفل #$id';
        final date = r['date']?.toString() ?? '';
        final status = r['status']?.toString() ?? 'DRAFT';
        final isSubmitted = status.toUpperCase() == 'SUBMITTED';

        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: ListTile(
            leading: const Icon(Icons.description, color: AppTheme.primary),
            title: Text(childName, style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text('التاريخ: $date · الحالة: $status'),
            trailing: isSubmitted
                ? ElevatedButton(
                    onPressed: () => _approveReport(id),
                    child: const Text('اعتماد'),
                  )
                : const Chip(label: Text('معتمد', style: TextStyle(fontSize: 11))),
          ),
        );
      },
    );
  }
}
