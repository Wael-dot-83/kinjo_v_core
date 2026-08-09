/// Daily Report Model for Parent & Manager Modules
class DailyReportModel {
  final int id;
  final int childId;
  final String childName;
  final String date;
  final String status;
  final String? mood;
  final String? meals;
  final String? napTime;
  final String? activities;
  final String? notes;

  DailyReportModel({
    required this.id,
    required this.childId,
    required this.childName,
    required this.date,
    required this.status,
    this.mood,
    this.meals,
    this.napTime,
    this.activities,
    this.notes,
  });

  factory DailyReportModel.fromJson(Map<String, dynamic> json) {
    return DailyReportModel(
      id: json['id'] ?? 0,
      childId: json['child_id'] ?? 0,
      childName: json['child_name'] ?? '',
      date: json['date'] ?? '',
      status: json['status'] ?? 'DRAFT',
      mood: json['mood'] ?? '😊',
      meals: json['meals'] ?? 'ممتاز 🍏',
      napTime: json['nap_time'] ?? 'ساعة و 30 دقيقة 😴',
      activities: json['activities'],
      notes: json['notes'],
    );
  }
}
