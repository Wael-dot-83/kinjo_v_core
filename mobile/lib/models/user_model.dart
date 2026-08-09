/// User Entity Model for KinJo Platform
enum UserRole { parent, supervisor, manager, admin, unknown }

extension UserRoleExtension on UserRole {
  String get value {
    switch (this) {
      case UserRole.parent:
        return 'PARENT';
      case UserRole.supervisor:
        return 'SUPERVISOR';
      case UserRole.manager:
        return 'MANAGER';
      case UserRole.admin:
        return 'ADMIN';
      default:
        return 'UNKNOWN';
    }
  }

  static UserRole fromString(String? roleStr) {
    switch (roleStr?.toUpperCase()) {
      case 'PARENT':
        return UserRole.parent;
      case 'SUPERVISOR':
        return UserRole.supervisor;
      case 'MANAGER':
        return UserRole.manager;
      case 'ADMIN':
        return UserRole.admin;
      default:
        return UserRole.unknown;
    }
  }
}

class UserModel {
  final int id;
  final String username;
  final String email;
  final String? firstName;
  final String? lastName;
  final UserRole role;

  UserModel({
    required this.id,
    required this.username,
    required this.email,
    this.firstName,
    this.lastName,
    required this.role,
  });

  String get fullName {
    if (firstName != null && lastName != null) {
      return '$firstName $lastName';
    }
    return username;
  }

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] ?? 0,
      username: json['username'] ?? '',
      email: json['email'] ?? '',
      firstName: json['first_name'],
      lastName: json['last_name'],
      role: UserRoleExtension.fromString(json['role']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'username': username,
      'email': email,
      'first_name': firstName,
      'last_name': lastName,
      'role': role.value,
    };
  }
}
