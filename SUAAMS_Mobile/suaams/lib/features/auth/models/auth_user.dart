class AuthUser {
  final int id;
  final String role;
  final String username;
  final String token;
  final bool requiresPasswordChange;

  /// Whether the account has a Lecturer profile. Only matters for role
  /// 'hod': a promoted HOD (lecturer + HOD) teaches through the lecturer
  /// screens; an HOD created as a new account has none and is sent to the
  /// web-portal screen instead. Defaults to true, so a login saved before
  /// the server sent this keeps behaving as it did.
  final bool hasLecturerProfile;

  AuthUser({
    required this.id,
    required this.role,
    required this.username,
    required this.token,
    this.requiresPasswordChange = false,
    this.hasLecturerProfile = true,
  });

  // This factory constructor takes the raw JSON map from Postman/Flask
  // and safely converts it into our Dart object.
  factory AuthUser.fromJson(Map<String, dynamic> json, String token) {
    return AuthUser(
      id: json['id'] as int,
      role: json['role'] as String,
      username: json['username'] as String,
      token: token,
      requiresPasswordChange: json['requires_password_change'] as bool? ?? false,
      hasLecturerProfile: json['has_lecturer_profile'] as bool? ?? true,
    );
  }
}