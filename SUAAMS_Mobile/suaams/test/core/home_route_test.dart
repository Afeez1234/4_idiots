import 'package:flutter_test/flutter_test.dart';

import 'package:suaams/core/router/home_route.dart';
import 'package:suaams/features/auth/models/auth_user.dart';

AuthUser _user(String role, {bool password = false, bool teaches = true}) => AuthUser(
      id: 1,
      role: role,
      username: 'u',
      token: 't',
      requiresPasswordChange: password,
      hasLecturerProfile: teaches,
    );

void main() {
  // homeRouteFor is the one copy of "where a signed-in user lives". The
  // splash and change-password screens used to keep their own copies that
  // didn't know 'hod'. (2026-10-19)
  group('homeRouteFor', () {
    test('a forced password change comes first, for every role', () {
      for (final role in ['student', 'lecturer', 'hod', 'admin']) {
        expect(homeRouteFor(_user(role, password: true)), '/change-password', reason: role);
      }
    });

    test('students and lecturers go to their homes', () {
      expect(homeRouteFor(_user('student')), '/student/home');
      expect(homeRouteFor(_user('lecturer')), '/lecturer/home');
    });

    test('a promoted HOD teaches through the lecturer screens', () {
      expect(homeRouteFor(_user('hod')), '/lecturer/home');
    });

    test('an HOD without a Lecturer profile, and an admin, get the web-portal screen', () {
      expect(homeRouteFor(_user('hod', teaches: false)), '/web-portal');
      expect(homeRouteFor(_user('admin')), '/web-portal');
    });

    test('an unknown role is sent to login', () {
      expect(homeRouteFor(_user('janitor')), '/login');
    });
  });

  group('AuthUser.hasLecturerProfile', () {
    test('reads the server flag, and defaults to true when it is missing', () {
      final base = {'id': 1, 'role': 'hod', 'username': 'h'};
      expect(AuthUser.fromJson({...base, 'has_lecturer_profile': false}, 't').hasLecturerProfile, isFalse);
      // A server from before the flag existed: behave as every account did.
      expect(AuthUser.fromJson(base, 't').hasLecturerProfile, isTrue);
    });
  });
}
