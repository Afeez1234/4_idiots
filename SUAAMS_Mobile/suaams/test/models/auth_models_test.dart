// Contract test for AuthUser against POST /api/v1/auth/login's response
// (mobile_login in SUAAMS/api/auth.py).
//
// requires_password_change is the field worth pinning: the router uses it
// to force a first-login password change, and the backend comment on it
// literally reads "Flutter relies on this!". If it stopped parsing, the
// model's `?? false` default would quietly let a user with a default
// password straight into the app.

import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/features/auth/models/auth_user.dart';

// Relative on purpose: package: URIs only resolve under lib/, and test/
// isn't. CLAUDE.md's absolute-import rule guards against a lib/ type
// being loaded under two URIs; this helper defines no lib/ types, so the
// collision it prevents can't happen here.
import '../support/api_fixtures.dart';

void main() {
  group('AuthUser (POST /auth/login)', () {
    test('parses the user object and keeps the token passed alongside', () {
      // Mirrors AuthService.login: token comes from the top level of the
      // body, user fields from responseData['user'].
      final body = loadApiFixture('auth_login');
      final user = AuthUser.fromJson(
        body['user'] as Map<String, dynamic>,
        body['token'] as String,
      );

      expect(user.id, 23);
      expect(user.username, 'MCT/2022/014');
      expect(user.role, 'student');
      expect(user.token, 'header.access-payload.signature');
      expect(user.requiresPasswordChange, isTrue);
    });

    test('requires_password_change absent defaults to false', () {
      // Older backends / the refresh path don't send it. Documenting the
      // default so a change to it is a deliberate decision.
      final user = AuthUser.fromJson(
        {'id': 1, 'role': 'lecturer', 'username': 'STF/0042'},
        't',
      );
      expect(user.requiresPasswordChange, isFalse);
    });
  });
}
