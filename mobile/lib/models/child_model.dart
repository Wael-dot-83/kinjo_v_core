/// Child Entity Model for Parent & Manager Modules
class ChildModel {
  final int id;
  final String firstName;
  final String? lastName;
  final String? gender;
  final String? dateOfBirth;
  final String? kindergartenName;
  final bool isPresentToday;

  ChildModel({
    required this.id,
    required this.firstName,
    this.lastName,
    this.gender,
    this.dateOfBirth,
    this.kindergartenName,
    this.isPresentToday = false,
  });

  String get fullName => '$firstName ${lastName ?? ''}'.trim();

  factory ChildModel.fromJson(Map<String, dynamic> json) {
    final attendanceToday = json['attendance_today'] as Map<String, dynamic>?;
    final isPresent = attendanceToday != null &&
        (attendanceToday['checked_in'] == true) &&
        (attendanceToday['checked_out'] != true);

    return ChildModel(
      id: json['id'] ?? 0,
      firstName: json['first_name'] ?? '',
      lastName: json['last_name'],
      gender: json['gender'],
      dateOfBirth: json['date_of_birth'],
      kindergartenName: json['kindergarten_name'],
      isPresentToday: isPresent,
    );
  }
}
