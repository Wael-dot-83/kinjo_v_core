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
    this.fullNameRaw,
    required this.role,
  });

  /// Supplied whole by endpoints that do not split the name.
  final String? fullNameRaw;

  /// Best display name available, never blank.
  ///
  /// The endpoints disagree about shape: login returns username but no name
  /// parts, /api/users/me returns id and role but no username, and
  /// /api/me/profile returns full_name. Falling straight through to `username`
  /// left the greeting empty whenever the source lacked it.
  String get fullName {
    if (firstName != null && lastName != null) {
      return '$firstName $lastName';
    }
    if (fullNameRaw != null && fullNameRaw!.trim().isNotEmpty) {
      return fullNameRaw!.trim();
    }
    if (username.isNotEmpty) return username;
    return email;
  }

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id'] ?? 0,
      username: json['username'] ?? '',
      email: json['email'] ?? '',
      firstName: json['first_name'],
      lastName: json['last_name'],
      fullNameRaw: json['full_name'],
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
