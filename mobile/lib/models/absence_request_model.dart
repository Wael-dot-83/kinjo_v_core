/// Absence Request Model for Mobile Application
class AbsenceRequestModel {
  final int id;
  final int childId;
  final String? childName;
  final String? parentName;
  final String startDate;
  final String endDate;
  final String reason;
  final String status;
  final String? decisionNote;

  AbsenceRequestModel({
    required this.id,
    required this.childId,
    this.childName,
    this.parentName,
    required this.startDate,
    required this.endDate,
    required this.reason,
    required this.status,
    this.decisionNote,
  });

  bool get isPending => status.toUpperCase() == 'SUBMITTED';
  bool get isApproved => status.toUpperCase() == 'APPROVED';
  bool get isRejected => status.toUpperCase() == 'REJECTED';

  String get statusArabic {
    switch (status.toUpperCase()) {
      case 'SUBMITTED':
        return 'قيد الانتظار';
      case 'APPROVED':
        return 'مقبول';
      case 'REJECTED':
        return 'مرفوض';
      default:
        return status;
    }
  }

  factory AbsenceRequestModel.fromJson(Map<String, dynamic> json) {
    return AbsenceRequestModel(
      id: json['id'] ?? 0,
      childId: json['child_id'] ?? 0,
      childName: json['child_name'],
      parentName: json['parent_name'],
      startDate: json['start_date'] ?? '',
      endDate: json['end_date'] ?? '',
      reason: json['reason'] ?? '',
      status: json['status'] ?? 'SUBMITTED',
      decisionNote: json['decision_note'],
    );
  }
}
