import 'package:flutter/material.dart';

import '../core/api/api_service.dart';
import '../core/api/dashboard_repository.dart';
import '../core/theme/app_theme.dart';
import '../models/user_model.dart';
import 'manager_operations_screen.dart';
import 'parent_operations_screen.dart';
import 'supervisor_roster_screen.dart';

/// Shared scaffolding for the three role home screens.
abstract class _DashboardScreen extends StatefulWidget {
  final UserModel user;

  const _DashboardScreen({super.key, required this.user});
}

abstract class _DashboardState<T extends _DashboardScreen> extends State<T> {
  late final DashboardRepository _repo = DashboardRepository(ApiService());

  bool _loading = true;
  String? _error;
  Map<String, dynamic> _data = const {};

  /// Title shown in the app bar.
  String get title;

  /// The one call this screen is built from.
  Future<Map<String, dynamic>> load(DashboardRepository repo);

  /// Rendered once [load] succeeds.
  List<Widget> buildBody(BuildContext context, Map<String, dynamic> data);

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final data = await load(_repo);
      if (!mounted) return;
      setState(() {
        _data = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'تعذّر تحميل البيانات. تحقّق من الاتصال وحاول مجدداً.';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            tooltip: 'تحديث',
            onPressed: _loading ? null : _refresh,
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'تسجيل الخروج',
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: _buildState(context),
      ),
    );
  }

  Widget _buildState(BuildContext context) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return ListView(
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 80),
          const Icon(Icons.wifi_off, size: 56, color: Colors.grey),
          const SizedBox(height: 16),
          Text(_error!, textAlign: TextAlign.center),
          const SizedBox(height: 16),
          Center(
            child: FilledButton.icon(
              onPressed: _refresh,
              icon: const Icon(Icons.refresh),
              label: const Text('إعادة المحاولة'),
            ),
          ),
        ],
      );
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: buildBody(context, _data),
    );
  }
}

// ── Shared pieces ───────────────────────────────────────────────────────────

int _int(dynamic v) => v is num ? v.toInt() : 0;
String _str(dynamic v) => v == null ? '' : v.toString();

class _Hero extends StatelessWidget {
  final String greeting;
  final String subtitle;

  const _Hero({required this.greeting, required this.subtitle});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppTheme.primary, AppTheme.primaryDark],
        ),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            greeting,
            style: const TextStyle(
                color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          Text(subtitle,
              style: const TextStyle(color: Colors.white70, fontSize: 14)),
        ],
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final IconData icon;
  final String label;
  final String value;
  final Color color;

  const _StatTile({
    required this.icon,
    required this.label,
    required this.value,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 12),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            CircleAvatar(
              backgroundColor: color.withOpacity(0.15),
              child: Icon(icon, color: color),
            ),
            const SizedBox(height: 10),
            Text(value,
                style: const TextStyle(
                    fontSize: 22, fontWeight: FontWeight.bold)),
            const SizedBox(height: 2),
            Text(
              label,
              textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.grey, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}

Widget _statGrid(List<Widget> tiles) => GridView.count(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisCount: 2,
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.15,
      children: tiles,
    );

Widget _sectionTitle(String text) => Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 12),
      child: Text(text,
          style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
    );

Widget _emptyNote(String text) => Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            const Icon(Icons.inbox, color: Colors.grey),
            const SizedBox(width: 12),
            Expanded(child: Text(text, style: const TextStyle(color: Colors.grey))),
          ],
        ),
      ),
    );

// ── Parent ──────────────────────────────────────────────────────────────────

class ParentDashboardScreen extends _DashboardScreen {
  const ParentDashboardScreen({super.key, required super.user});

  @override
  State<ParentDashboardScreen> createState() => _ParentState();
}

class _ParentState extends _DashboardState<ParentDashboardScreen> {
  @override
  String get title => 'لوحة ولي الأمر - KinJo';

  @override
  Future<Map<String, dynamic>> load(DashboardRepository repo) =>
      repo.parentDashboard();

  @override
  List<Widget> buildBody(BuildContext context, Map<String, dynamic> data) {
    final children = (data['children'] as List?) ?? const [];
    final total = _int(data['total_children']);
    final presentToday = children.where((c) {
      final a = (c as Map)['attendance_today'];
      return a is Map && a['checked_in'] == true && a['checked_out'] != true;
    }).length;

    return [
      _Hero(
        greeting: 'أهلاً بك، ${widget.user.fullName}',
        subtitle: 'تابع أنشطة أطفالك اليومية وحالة الحضور وتقارير الروضة.',
      ),
      const SizedBox(height: 16),
      SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ParentOperationsScreen(user: widget.user),
              ),
            );
          },
          icon: const Icon(Icons.assignment),
          label: const Text('متابعة التقارير اليومية وتقديم إجازة'),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppTheme.secondary,
            padding: const EdgeInsets.symmetric(vertical: 14),
          ),
        ),
      ),
      const SizedBox(height: 16),
      _statGrid([
        _StatTile(
            icon: Icons.child_care,
            label: 'الأطفال',
            value: '$total',
            color: AppTheme.primary),
        _StatTile(
            icon: Icons.how_to_reg,
            label: 'حاضرون اليوم',
            value: '$presentToday',
            color: AppTheme.secondary),
      ]),
      _sectionTitle('أطفالي'),
      if (children.isEmpty)
        _emptyNote('لم تقم بتسجيل أي طفل بعد.')
      else
        ...children.map((raw) {
          final c = (raw as Map).cast<String, dynamic>();
          final name =
              '${_str(c['first_name'])} ${_str(c['last_name'])}'.trim();
          final att = c['attendance_today'];
          final present =
              att is Map && att['checked_in'] == true && att['checked_out'] != true;
          final hasReport = _str(c['latest_report_date']).isNotEmpty;
          return Card(
            child: ListTile(
              leading: CircleAvatar(
                backgroundColor: AppTheme.primary.withOpacity(0.12),
                child: Text(name.isEmpty ? '?' : name.characters.first),
              ),
              title: Text(name),
              subtitle: Text(_str(c['kindergarten_name'])),
              trailing: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    present ? 'حاضر' : 'غير مسجّل',
                    style: TextStyle(
                      color: present ? Colors.green : Colors.grey,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                  if (hasReport)
                    const Text('تقرير متاح',
                        style: TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ),
            ),
          );
        }),
    ];
  }
}

// ── Supervisor ──────────────────────────────────────────────────────────────

class SupervisorDashboardScreen extends _DashboardScreen {
  const SupervisorDashboardScreen({super.key, required super.user});

  @override
  State<SupervisorDashboardScreen> createState() => _SupervisorState();
}

class _SupervisorState extends _DashboardState<SupervisorDashboardScreen> {
  @override
  String get title => 'لوحة المشرف';

  @override
  Future<Map<String, dynamic>> load(DashboardRepository repo) =>
      repo.supervisorDashboard();

  @override
  List<Widget> buildBody(BuildContext context, Map<String, dynamic> data) {
    final classes = (data['classes'] as List?) ?? const [];
    final attendance = data['attendance_summary'];
    final presentToday =
        attendance is Map ? _int(attendance['today']) : 0;
    final remaining = _int(data['reports_remaining_today']);

    return [
      _Hero(
        greeting: 'أهلاً بك، ${widget.user.fullName}',
        subtitle: 'ملخّص صفوفك ليوم ${_str(data['date'])}.',
      ),
      const SizedBox(height: 16),
      SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => SupervisorRosterScreen(user: widget.user),
              ),
            );
          },
          icon: const Icon(Icons.assignment_turned_in),
          label: const Text('تعبئة كشف التقارير اليومية للأطفال'),
          style: ElevatedButton.styleFrom(
            padding: const EdgeInsets.symmetric(vertical: 14),
          ),
        ),
      ),
      const SizedBox(height: 16),
      _statGrid([
        _StatTile(
            icon: Icons.groups,
            label: 'إجمالي الأطفال',
            value: '${_int(data['total_children'])}',
            color: AppTheme.primary),
        _StatTile(
            icon: Icons.how_to_reg,
            label: 'حاضرون اليوم',
            value: '$presentToday',
            color: AppTheme.secondary),
        _StatTile(
            icon: Icons.assignment_turned_in,
            label: 'تقارير اليوم',
            value: '${_int(data['reports_today'])}',
            color: AppTheme.accent),
        _StatTile(
            icon: remaining > 0 ? Icons.pending_actions : Icons.task_alt,
            label: remaining > 0 ? 'بلا تقرير اليوم' : 'مكتمل',
            value: '$remaining',
            color: remaining > 0 ? AppTheme.danger : AppTheme.secondary),
      ]),
      _sectionTitle('صفوفي'),
      if (classes.isEmpty)
        _emptyNote('لا توجد صفوف مسندة إليك.')
      else
        ...classes.map((raw) {
          final c = (raw as Map).cast<String, dynamic>();
          final isPrimary = c['is_primary'] == true;
          return Card(
            child: ListTile(
              leading: const Icon(Icons.class_, color: AppTheme.primary),
              title: Text(_str(c['name_ar']).isNotEmpty
                  ? _str(c['name_ar'])
                  : _str(c['name_en'])),
              trailing: isPrimary
                  ? const Chip(
                      label: Text('مسؤول أساسي',
                          style: TextStyle(fontSize: 11)))
                  : null,
            ),
          );
        }),
    ];
  }
}

// ── Manager ─────────────────────────────────────────────────────────────────

class ManagerDashboardScreen extends _DashboardScreen {
  const ManagerDashboardScreen({super.key, required super.user});

  @override
  State<ManagerDashboardScreen> createState() => _ManagerState();
}

class _ManagerState extends _DashboardState<ManagerDashboardScreen> {
  @override
  String get title => 'إدارة الحضانة';

  @override
  Future<Map<String, dynamic>> load(DashboardRepository repo) =>
      repo.managerDashboard();

  @override
  List<Widget> buildBody(BuildContext context, Map<String, dynamic> data) {
    final kg = data['kindergarten'];
    final kgName = kg is Map ? _str(kg['name_ar']) : '';
    final summary =
        (data['summary'] as Map?)?.cast<String, dynamic>() ?? const {};
    final alerts = (data['alerts'] as List?) ?? const [];
    final classes = (data['classes'] as List?) ?? const [];

    return [
      _Hero(
        greeting: kgName.isEmpty ? widget.user.fullName : kgName,
        subtitle: 'ملخّص عمليات الحضانة اليوم.',
      ),
      const SizedBox(height: 16),
      SizedBox(
        width: double.infinity,
        child: ElevatedButton.icon(
          onPressed: () {
            Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) => ManagerOperationsScreen(user: widget.user),
              ),
            );
          },
          icon: const Icon(Icons.approval),
          label: const Text('مراجعة طلبات الإجازة والتقارير اليومية'),
          style: ElevatedButton.styleFrom(
            backgroundColor: AppTheme.purpleAccent,
            padding: const EdgeInsets.symmetric(vertical: 14),
          ),
        ),
      ),
      const SizedBox(height: 16),
      _statGrid([
        _StatTile(
            icon: Icons.people,
            label: 'تسجيلات نشطة',
            value: '${_int(summary['active_enrollments'])}',
            color: AppTheme.primary),
        _StatTile(
            icon: Icons.how_to_reg,
            label: 'حضور اليوم',
            value: '${_int(summary['attendance_today'])}',
            color: AppTheme.secondary),
        _StatTile(
            icon: Icons.inbox,
            label: 'طلبات قيد الانتظار',
            value: '${_int(summary['pending_applications'])}',
            color: AppTheme.accent),
        _StatTile(
            icon: Icons.description,
            label: 'تقارير قيد المراجعة',
            value: '${_int(summary['pending_daily_reports'])}',
            color: AppTheme.purpleAccent),
      ]),
      if (alerts.isNotEmpty) ...[
        _sectionTitle('تنبيهات'),
        ...alerts.map((raw) {
          final a = (raw as Map).cast<String, dynamic>();
          final text = _str(a['message_ar']).isNotEmpty
              ? _str(a['message_ar'])
              : _str(a['message']);
          final high = _str(a['priority']).toLowerCase() == 'high';
          return Card(
            child: ListTile(
              leading: Icon(
                high ? Icons.error : Icons.info,
                color: high ? AppTheme.danger : AppTheme.accent,
              ),
              title: Text(text, style: const TextStyle(fontSize: 14)),
            ),
          );
        }),
      ],
      _sectionTitle('الصفوف'),
      if (classes.isEmpty)
        _emptyNote('لا توجد صفوف مسجّلة.')
      else
        ...classes.map((raw) {
          final c = (raw as Map).cast<String, dynamic>();
          final name = _str(c['name_ar']).isNotEmpty
              ? _str(c['name_ar'])
              : _str(c['name']);
          return Card(
            child: ListTile(
              leading: const Icon(Icons.meeting_room, color: AppTheme.primary),
              title: Text(name),
              subtitle: Text(
                  'مسجّلون ${_int(c['enrolled'])} من ${_int(c['capacity'])} · حاضرون ${_int(c['present'])}'),
            ),
          );
        }),
    ];
  }
}
