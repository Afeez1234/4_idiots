class AuthUser {
  final int id;
  final String role;
  final String username;
  final String token;
  final bool requiresPasswordChange;

  AuthUser({
    required this.id,
    required this.role,
    required this.username,
    required this.token,
    this.requiresPasswordChange = false,
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
    );
  }
}