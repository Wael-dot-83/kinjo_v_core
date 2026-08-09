/// Roster Entry Model for Batch Daily Reports
class RosterEntryModel {
  final int childId;
  final String childName;
  String arrivalTime;
  String leaveTime;
  String? mood;
  bool breakfast;
  bool snack;
  bool milk;
  bool lunch;
  String? activities;
  String? notes;
  String? healthNotes;
  bool skip;

  RosterEntryModel({
    required this.childId,
    required this.childName,
    this.arrivalTime = '08:00',
    this.leaveTime = '14:00',
    this.mood = 'happy',
    this.breakfast = true,
    this.snack = true,
    this.milk = true,
    this.lunch = true,
    this.activities,
    this.notes,
    this.healthNotes,
    this.skip = false,
  });

  Map<String, dynamic> toJson() {
    return {
      'child_id': childId,
      'arrival_time': arrivalTime,
      'leave_time': leaveTime,
      'mood': mood,
      'breakfast': breakfast,
      'snack': snack,
      'milk': milk,
      'lunch': lunch,
      'activities': activities,
      'notes': notes,
      'health_notes': healthNotes,
      'skip': skip,
    };
  }
}

class RosterBatchRequestModel {
  final String date;
  final String arrivalTime;
  final String leaveTime;
  final bool breakfast;
  final bool snack;
  final bool milk;
  final bool lunch;
  final List<RosterEntryModel> children;

  RosterBatchRequestModel({
    required this.date,
    this.arrivalTime = '08:00',
    this.leaveTime = '14:00',
    this.breakfast = true,
    this.snack = true,
    this.milk = true,
    this.lunch = true,
    required this.children,
  });

  Map<String, dynamic> toJson() {
    return {
      'date': date,
      'arrival_time': arrivalTime,
      'leave_time': leaveTime,
      'breakfast': breakfast,
      'snack': snack,
      'milk': milk,
      'lunch': lunch,
      'children': children.map((c) => c.toJson()).toList(),
    };
  }
}

class RosterResultItemModel {
  final int childId;
  final String status; // 'created', 'skipped', 'failed'
  final int? reportId;
  final int? code;
  final String? detail;

  RosterResultItemModel({
    required this.childId,
    required this.status,
    this.reportId,
    this.code,
    this.detail,
  });

  factory RosterResultItemModel.fromJson(Map<String, dynamic> json) {
    return RosterResultItemModel(
      childId: json['child_id'] ?? 0,
      status: json['status'] ?? 'unknown',
      reportId: json['report_id'],
      code: json['code'],
      detail: json['detail'],
    );
  }
}

class RosterBatchResponseModel {
  final String date;
  final int created;
  final int skipped;
  final int failed;
  final List<RosterResultItemModel> results;

  RosterBatchResponseModel({
    required this.date,
    required this.created,
    required this.skipped,
    required this.failed,
    required this.results,
  });

  factory RosterBatchResponseModel.fromJson(Map<String, dynamic> json) {
    final rawResults = (json['results'] as List?) ?? [];
    return RosterBatchResponseModel(
      date: json['date'] ?? '',
      created: json['created'] ?? 0,
      skipped: json['skipped'] ?? 0,
      failed: json['failed'] ?? 0,
      results: rawResults
          .map((r) => RosterResultItemModel.fromJson((r as Map).cast<String, dynamic>()))
          .toList(),
    );
  }
}
