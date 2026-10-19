import 'package:suaams/features/auth/models/auth_user.dart';

/// Where a signed-in user lives -- the one copy of this rule, used by the
/// router (app_router.dart), the splash, change-password and onboarding
/// screens. Each used to keep its own copy, and two of them didn't know
/// 'hod': an HOD reopening the app flashed the login screen, and one
/// finishing the first-login password change was left sitting on that
/// screen. In its own file so the screens can import it without importing
/// the router (which imports them). (2026-10-19)
///
/// HOD work is web-only by design. A promoted HOD (lecturer + HOD) teaches
/// through the lecturer screens -- get_lecturer_or_403 in api/lecturer.py
/// accepts role 'hod'. An HOD without a Lecturer profile, and an admin, get
/// the web-portal screen: the lecturer screens would only fail for them.
String homeRouteFor(AuthUser user) {
  if (user.requiresPasswordChange) return '/change-password';
  switch (user.role) {
    case 'student':
      return '/student/home';
    case 'lecturer':
      return '/lecturer/home';
    case 'hod':
      return user.hasLecturerProfile ? '/lecturer/home' : '/web-portal';
    case 'admin':
      return '/web-portal';
    default:
      return '/login';
  }
}
