import 'package:flutter/material.dart';
import '../core/api/api_service.dart';
import '../core/api/operational_repository.dart';
import '../core/theme/app_theme.dart';
import '../models/roster_model.dart';
import '../models/user_model.dart';

/// Supervisor Daily Report Roster Batch Filing Screen
class SupervisorRosterScreen extends StatefulWidget {
  final UserModel user;

  const SupervisorRosterScreen({super.key, required this.user});

  @override
  State<SupervisorRosterScreen> createState() => _SupervisorRosterScreenState();
}

class _SupervisorRosterScreenState extends State<SupervisorRosterScreen> {
  late final OperationalRepository _repo = OperationalRepository(ApiService());

  bool _loading = true;
  bool _submitting = false;
  String? _error;
  
  final String _date = DateTime.now().toIso8601String().split('T')[0];
  final String _defaultArrivalTime = '08:00';
  final String _defaultLeaveTime = '14:00';
  bool _defaultBreakfast = true;
  final bool _defaultSnack = true;
  bool _defaultMilk = true;
  bool _defaultLunch = true;

  List<RosterEntryModel> _rosterEntries = [];

  @override
  void initState() {
    super.initState();
    _loadChildren();
  }

  Future<void> _loadChildren() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final childrenList = await _repo.getSupervisorChildren();
      if (!mounted) return;

      setState(() {
        _rosterEntries = childrenList.map((c) {
          final id = c['id'] is num ? (c['id'] as num).toInt() : 0;
          final firstName = c['first_name']?.toString() ?? '';
          final lastName = c['last_name']?.toString() ?? '';
          final name = '$firstName $lastName'.trim();
          return RosterEntryModel(
            childId: id,
            childName: name.isEmpty ? 'طفل #$id' : name,
            arrivalTime: _defaultArrivalTime,
            leaveTime: _defaultLeaveTime,
            breakfast: _defaultBreakfast,
            snack: _defaultSnack,
            milk: _defaultMilk,
            lunch: _defaultLunch,
          );
        }).toList();
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.toString();
        _loading = false;
      });
    }
  }

  Future<void> _submitBatch() async {
    if (_rosterEntries.isEmpty) return;

    setState(() {
      _submitting = true;
    });

    final payload = RosterBatchRequestModel(
      date: _date,
      arrivalTime: _defaultArrivalTime,
      leaveTime: _defaultLeaveTime,
      breakfast: _defaultBreakfast,
      snack: _defaultSnack,
      milk: _defaultMilk,
      lunch: _defaultLunch,
      children: _rosterEntries,
    );

    try {
      final response = await _repo.submitBatchDailyReports(payload);
      if (!mounted) return;

      setState(() {
        _submitting = false;
      });

      _showMultiStatusDialog(response);
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _submitting = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(e.toString()),
          backgroundColor: AppTheme.danger,
        ),
      );
    }
  }

  void _showMultiStatusDialog(RosterBatchResponseModel response) {
    showDialog(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.assignment_turned_in, color: AppTheme.primary),
              SizedBox(width: 8),
              Text('نتيجة رفع التقارير (207)'),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: AppTheme.primary.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _statusCount('تم الإنشاء', response.created, Colors.green),
                      _statusCount('تم التجاوز', response.skipped, Colors.orange),
                      _statusCount('فشل / مكرر', response.failed, AppTheme.danger),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'تفاصيل الأطفال:',
                  style: TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                ...response.results.map((r) {
                  final entry = _rosterEntries.firstWhere(
                    (e) => e.childId == r.childId,
                    orElse: () => RosterEntryModel(childId: r.childId, childName: '#${r.childId}'),
                  );

                  Color statusColor = Colors.grey;
                  String label = r.status;
                  if (r.status == 'created') {
                    statusColor = Colors.green;
                    label = 'تمت الإضافة النجاح';
                  } else if (r.status == 'skipped') {
                    statusColor = Colors.orange;
                    label = 'تم التجاوز';
                  } else if (r.status == 'failed') {
                    statusColor = AppTheme.danger;
                    label = r.detail ?? 'فشل (مكرر أو خطأ)';
                  }

                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4.0),
                    child: Row(
                      children: [
                        Icon(
                          r.status == 'created'
                              ? Icons.check_circle
                              : (r.status == 'skipped' ? Icons.remove_circle : Icons.error),
                          color: statusColor,
                          size: 18,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            entry.childName,
                            style: const TextStyle(fontSize: 14),
                          ),
                        ),
                        Text(
                          label,
                          style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.bold),
                        ),
                      ],
                    ),
                  );
                }),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () {
                Navigator.of(ctx).pop();
                _loadChildren(); // Refresh roster status
              },
              child: const Text('إغلاق وتحديث'),
            ),
          ],
        );
      },
    );
  }

  Widget _statusCount(String label, int count, Color color) {
    return Column(
      children: [
        Text(
          '$count',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: color),
        ),
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('كشف صفوف الحضانة والتقارير'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _loadChildren,
          ),
        ],
      ),
      body: _buildBody(),
      bottomNavigationBar: _rosterEntries.isNotEmpty
          ? Container(
              padding: const EdgeInsets.all(16),
              decoration: const BoxDecoration(
                color: Colors.white,
                boxShadow: [BoxShadow(color: Colors.black12, blurRadius: 4, offset: Offset(0, -2))],
              ),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton.icon(
                  onPressed: _submitting ? null : _submitBatch,
                  icon: _submitting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                        )
                      : const Icon(Icons.send),
                  label: Text(_submitting ? 'جاري الإرسال...' : 'إرسال تقارير الكشف اليومي'),
                ),
              ),
            )
          : null,
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.wifi_off, size: 56, color: Colors.grey),
              const SizedBox(height: 16),
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              ElevatedButton.icon(
                onPressed: _loadChildren,
                icon: const Icon(Icons.refresh),
                label: const Text('إعادة المحاولة'),
              ),
            ],
          ),
        ),
      );
    }

    if (_rosterEntries.isEmpty) {
      return const Center(
        child: Text('لا يوجد أطفال متاحون للكشف اليومي في صفك.'),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Roster Global Defaults Card
        Card(
          color: AppTheme.primary.withOpacity(0.05),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.tune, color: AppTheme.primary),
                    const SizedBox(width: 8),
                    Text(
                      'إعدادات الكشف الجماعي (${_rosterEntries.length} طفل)',
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                Row(
                  children: [
                    Expanded(
                      child: Text('تاريخ اليوم: $_date',
                          style: const TextStyle(fontWeight: FontWeight.w600)),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    FilterChip(
                      selected: _defaultBreakfast,
                      label: const Text('إفطار 🍏'),
                      onSelected: (val) => setState(() => _defaultBreakfast = val),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _defaultLunch,
                      label: const Text('غداء 🍲'),
                      onSelected: (val) => setState(() => _defaultLunch = val),
                    ),
                    const SizedBox(width: 8),
                    FilterChip(
                      selected: _defaultMilk,
                      label: const Text('حليب 🥛'),
                      onSelected: (val) => setState(() => _defaultMilk = val),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),

        const SizedBox(height: 16),
        const Text(
          'قائمة الأطفال في الصف:',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 8),

        // Per Child Entry Cards
        ..._rosterEntries.map((entry) => _buildChildRosterCard(entry)),
      ],
    );
  }

  Widget _buildChildRosterCard(RosterEntryModel entry) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: AppTheme.primary.withOpacity(0.12),
                  child: Text(entry.childName.isNotEmpty ? entry.childName[0] : '?'),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    entry.childName,
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ),
                Row(
                  children: [
                    const Text('تجاوز (غائب)', style: TextStyle(fontSize: 12)),
                    Switch(
                      value: entry.skip,
                      activeColor: AppTheme.danger,
                      onChanged: (val) {
                        setState(() {
                          entry.skip = val;
                        });
                      },
                    ),
                  ],
                ),
              ],
            ),
            if (!entry.skip) ...[
              const Divider(height: 24),
              const Text('مزاج الطفل اليوم:', style: TextStyle(fontSize: 12, color: Colors.grey)),
              const SizedBox(height: 6),
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: Row(
                  children: [
                    _moodChoice(entry, 'happy', 'سعيد 😊'),
                    _moodChoice(entry, 'calm', 'هادئ 😌'),
                    _moodChoice(entry, 'active', 'نشيط 🏃'),
                    _moodChoice(entry, 'tired', 'تعبان 😴'),
                    _moodChoice(entry, 'sad', 'حزين 😢'),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                decoration: const InputDecoration(
                  labelText: 'ملاحظات المعلم اليومية (اختياري)',
                  isDense: true,
                ),
                onChanged: (val) => entry.notes = val,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _moodChoice(RosterEntryModel entry, String moodValue, String label) {
    final isSelected = entry.mood == moodValue;
    return Padding(
      padding: const EdgeInsets.only(left: 6.0),
      child: ChoiceChip(
        selected: isSelected,
        label: Text(label),
        selectedColor: AppTheme.primary.withOpacity(0.2),
        onSelected: (val) {
          if (val) {
            setState(() {
              entry.mood = moodValue;
            });
          }
        },
      ),
    );
  }
}
