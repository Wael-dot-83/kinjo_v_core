import 'package:flutter/material.dart';
import '../core/api/api_service.dart';
import '../core/api/operational_repository.dart';
import '../core/theme/app_theme.dart';
import '../models/absence_request_model.dart';
import '../models/user_model.dart';

/// Parent Operational Screen — Child Reports Viewer & Absence Submission
class ParentOperationsScreen extends StatefulWidget {
  final UserModel user;

  const ParentOperationsScreen({super.key, required this.user});

  @override
  State<ParentOperationsScreen> createState() => _ParentOperationsScreenState();
}

class _ParentOperationsScreenState extends State<ParentOperationsScreen> with SingleTickerProviderStateMixin {
  late final OperationalRepository _repo = OperationalRepository(ApiService());
  late final TabController _tabController = TabController(length: 2, vsync: this);

  bool _loadingChildren = true;
  bool _loadingAbsences = true;
  String? _childrenError;
  String? _absencesError;

  List<Map<String, dynamic>> _children = [];
  List<AbsenceRequestModel> _absenceRequests = [];

  @override
  void initState() {
    super.initState();
    _loadChildren();
    _loadAbsenceRequests();
  }

  Future<void> _loadChildren() async {
    setState(() {
      _loadingChildren = true;
      _childrenError = null;
    });

    try {
      final list = await _repo.getParentChildren();
      if (!mounted) return;
      setState(() {
        _children = list;
        _loadingChildren = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _childrenError = e.toString();
        _loadingChildren = false;
      });
    }
  }

  Future<void> _loadAbsenceRequests() async {
    setState(() {
      _loadingAbsences = true;
      _absencesError = null;
    });

    try {
      final list = await _repo.getAbsenceRequests();
      if (!mounted) return;
      setState(() {
        _absenceRequests = list;
        _loadingAbsences = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _absencesError = e.toString();
        _loadingAbsences = false;
      });
    }
  }

  void _showNewAbsenceDialog() {
    if (_children.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('لا يوجد أطفال مسجلون لتطبيق طلب الإجازة.')),
      );
      return;
    }

    int selectedChildId = (_children.first['id'] as num).toInt();
    final tomorrow = DateTime.now().add(const Duration(days: 1));
    String startDate = tomorrow.toIso8601String().split('T')[0];
    String endDate = tomorrow.add(const Duration(days: 1)).toIso8601String().split('T')[0];
    final reasonController = TextEditingController();
    bool submitting = false;

    showDialog(
      context: context,
      builder: (ctx) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return AlertDialog(
              title: const Text('تقديم طلب إجازة جديد'),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('اختر الطفل:', style: TextStyle(fontWeight: FontWeight.bold)),
                    DropdownButton<int>(
                      isExpanded: true,
                      value: selectedChildId,
                      items: _children.map((c) {
                        final id = (c['id'] as num).toInt();
                        final name = '${c['first_name'] ?? ''} ${c['last_name'] ?? ''}'.trim();
                        return DropdownMenuItem<int>(
                          value: id,
                          child: Text(name.isEmpty ? 'طفل #$id' : name),
                        );
                      }).toList(),
                      onChanged: (val) {
                        if (val != null) setModalState(() => selectedChildId = val);
                      },
                    ),
                    const SizedBox(height: 12),
                    Text('تاريخ البدء: $startDate'),
                    Text('تاريخ الانتهاء: $endDate'),
                    const SizedBox(height: 12),
                    TextField(
                      controller: reasonController,
                      decoration: const InputDecoration(
                        labelText: 'سبب الإجازة (مثل: مراجعة طبيب)',
                      ),
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(ctx).pop(),
                  child: const Text('إلغاء'),
                ),
                ElevatedButton(
                  onPressed: submitting
                      ? null
                      : () async {
                          if (reasonController.text.trim().isEmpty) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('يُرجى إدخال سبب الإجازة')),
                            );
                            return;
                          }
                          final messenger = ScaffoldMessenger.of(context);
                          final navigator = Navigator.of(ctx);
                          setModalState(() => submitting = true);
                          try {
                            await _repo.submitAbsenceRequest(
                              childId: selectedChildId,
                              startDate: startDate,
                              endDate: endDate,
                              reason: reasonController.text.trim(),
                            );
                            if (!mounted) return;
                            navigator.pop();
                            messenger.showSnackBar(
                              const SnackBar(content: Text('تم تقديم طلب الإجازة بنجاح.')),
                            );
                            _loadAbsenceRequests();
                          } catch (e) {
                            setModalState(() => submitting = false);
                            messenger.showSnackBar(
                              SnackBar(content: Text(e.toString()), backgroundColor: AppTheme.danger),
                            );
                          }
                        },
                  child: submitting
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Text('تقديم الطلب'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  void _showChildReportsModal(Map<String, dynamic> child) async {
    final id = (child['id'] as num).toInt();
    final name = '${child['first_name'] ?? ''} ${child['last_name'] ?? ''}'.trim();

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        return Container(
          height: MediaQuery.of(context).size.height * 0.7,
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'التقارير اليومية للطفل: $name',
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              Expanded(
                child: FutureBuilder<List<Map<String, dynamic>>>(
                  future: _repo.getChildDailyReports(id),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting) {
                      return const Center(child: CircularProgressIndicator());
                    }
                    if (snapshot.hasError) {
                      return Center(child: Text('خطأ: ${snapshot.error}'));
                    }
                    final reports = snapshot.data ?? [];
                    if (reports.isEmpty) {
                      return const Center(child: Text('لا توجد تقارير منشورة لهذا الطفل حتى الآن.'));
                    }

                    return ListView.builder(
                      itemCount: reports.length,
                      itemBuilder: (context, i) {
                        final r = reports[i];
                        final date = r['date']?.toString() ?? '';
                        final mood = r['mood']?.toString() ?? 'happy';
                        final notes = r['notes']?.toString() ?? 'لا توجد ملاحظات إضافية';

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
                                    Text('تقرير يوم: $date', style: const TextStyle(fontWeight: FontWeight.bold)),
                                    Chip(label: Text('مزاج: $mood')),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                Text('ملاحظات: $notes', style: const TextStyle(color: Colors.grey)),
                              ],
                            ),
                          ),
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('خدمات ولي الأمر والتقارير'),
        bottom: TabBar(
          controller: _tabController,
          tabs: const [
            Tab(icon: Icon(Icons.child_care), text: 'أطفالي والتقارير'),
            Tab(icon: Icon(Icons.event_busy), text: 'طلبات الإجازة'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _buildChildrenTab(),
          _buildAbsencesTab(),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _showNewAbsenceDialog,
        icon: const Icon(Icons.add),
        label: const Text('طلب إجازة جديد'),
        backgroundColor: AppTheme.primary,
      ),
    );
  }

  Widget _buildChildrenTab() {
    if (_loadingChildren) return const Center(child: CircularProgressIndicator());
    if (_childrenError != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_childrenError!),
            ElevatedButton(onPressed: _loadChildren, child: const Text('إعادة المحاولة')),
          ],
        ),
      );
    }

    if (_children.isEmpty) {
      return const Center(child: Text('لم تقم بتسجيل أي طفل بعد.'));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _children.length,
      itemBuilder: (ctx, idx) {
        final child = _children[idx];
        final name = '${child['first_name'] ?? ''} ${child['last_name'] ?? ''}'.trim();
        final kgName = child['kindergarten_name']?.toString() ?? 'غير محدد';

        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: ListTile(
            leading: CircleAvatar(
              backgroundColor: AppTheme.primary.withOpacity(0.12),
              child: Text(name.isNotEmpty ? name[0] : '?'),
            ),
            title: Text(name, style: const TextStyle(fontWeight: FontWeight.bold)),
            subtitle: Text('الروضة: $kgName'),
            trailing: OutlinedButton.icon(
              onPressed: () => _showChildReportsModal(child),
              icon: const Icon(Icons.article),
              label: const Text('عرض التقارير'),
            ),
          ),
        );
      },
    );
  }

  Widget _buildAbsencesTab() {
    if (_loadingAbsences) return const Center(child: CircularProgressIndicator());
    if (_absencesError != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_absencesError!),
            ElevatedButton(onPressed: _loadAbsenceRequests, child: const Text('إعادة المحاولة')),
          ],
        ),
      );
    }

    if (_absenceRequests.isEmpty) {
      return const Center(child: Text('لم تقم بتقديم أي طلبات إجازة سابقة.'));
    }

    return ListView.builder(
      padding: const EdgeInsets.all(16),
      itemCount: _absenceRequests.length,
      itemBuilder: (ctx, idx) {
        final req = _absenceRequests[idx];
        return Card(
          margin: const EdgeInsets.only(bottom: 12),
          child: ListTile(
            leading: const Icon(Icons.event_note, color: AppTheme.primary),
            title: Text('إجازة من ${req.startDate} إلى ${req.endDate}'),
            subtitle: Text('السبب: ${req.reason}'),
            trailing: Chip(
              label: Text(req.statusArabic, style: const TextStyle(fontSize: 11)),
            ),
          ),
        );
      },
    );
  }
}
