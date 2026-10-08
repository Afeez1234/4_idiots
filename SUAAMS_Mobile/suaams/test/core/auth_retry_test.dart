// Tests for withAuthRetry -- the "silent refresh, retry once" wrapper that
// every authenticated API call in the app (17 files) goes through.
//
// The rule worth pinning is WHO gets logged out, and when. A logout wipes
// a 14-day token store, so it must only follow an actual server rejection
// of the refresh token. An unreachable refresh (lecture-hall dead spot)
// used to be treated the same as a rejection and signed students out over
// a network blip; the "unreachable" tests below exist for that regression.
//
// What's real vs faked: withAuthRetry and AuthNotifier (including its
// refreshSession memoisation and logout) are the real code. Only
// AuthService -- secure storage and HTTP -- is faked, and the notifier's
// build() is seeded with a signed-in user.

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/features/auth/data/auth_service.dart';
import 'package:suaams/features/auth/models/auth_user.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';

/// Stands in for secure storage + /auth/refresh + /auth/logout. Extends
/// Fake, so any AuthService method a test didn't expect to be called throws
/// instead of silently doing nothing.
class _FakeAuthService extends Fake implements AuthService {
  /// What the next /auth/refresh does: return a new token or throw.
  Future<String> Function() onRefresh = () async => 'new-token';
  int refreshCalls = 0;
  int logoutCalls = 0;

  @override
  Future<String> refreshAccessToken() {
    refreshCalls++;
    return onRefresh();
  }

  @override
  Future<void> logout({bool notifyServer = true}) async {
    logoutCalls++;
  }
}

/// The real AuthNotifier, starting signed in (or not) instead of empty.
class _SeededAuthNotifier extends AuthNotifier {
  _SeededAuthNotifier(this._initialToken);
  final String? _initialToken;

  @override
  AuthState build() => AuthState(
        user: _initialToken == null
            ? null
            : AuthUser(
                id: 23,
                role: 'student',
                username: 'MCT/2022/014',
                token: _initialToken,
              ),
      );
}

/// Hands the test a live Ref, since withAuthRetry takes one. The container
/// outlives every call in a test, so the Ref stays valid throughout.
final _refProbe = Provider<Ref>((ref) => ref);

// Error strings in the shapes the services actually throw.
final _expired = Exception('Token has expired');
final _unauthorized = Exception('Unauthorized');
final _serverDown = Exception('Server Error: 503');

void main() {
  late _FakeAuthService auth;
  late ProviderContainer container;

  /// Builds the container. [token] null = no signed-in user.
  void signIn([String? token = 'old-token']) {
    auth = _FakeAuthService();
    container = ProviderContainer.test(
      overrides: [
        authServiceProvider.overrideWithValue(auth),
        authProvider.overrideWith(() => _SeededAuthNotifier(token)),
      ],
    );
  }

  Future<T> run<T>(Future<T> Function(String token) request) =>
      withAuthRetry(container.read(_refProbe), request);

  bool signedIn() => container.read(authProvider).user != null;

  // AuthNotifier logs a debugPrint on unreachable refreshes; keep test
  // output readable.
  setUpAll(() {
    debugPrint = (String? message, {int? wrapWidth}) {};
  });
  tearDownAll(() => debugPrint = debugPrintSynchronously);

  test('no signed-in user: throws without calling the request', () async {
    signIn(null);
    var called = false;

    await expectLater(
      run((_) async => called = true),
      throwsA(predicate((e) => '$e'.contains('Authentication token missing'))),
    );
    expect(called, isFalse);
  });

  test('success passes the current token and never refreshes', () async {
    signIn();
    final result = await run((token) async => 'ok with $token');

    expect(result, 'ok with old-token');
    expect(auth.refreshCalls, 0);
  });

  test('a non-auth failure is rethrown untouched, no refresh', () async {
    signIn();
    await expectLater(run<void>((_) => throw _serverDown), throwsA(_serverDown));
    expect(auth.refreshCalls, 0);
    expect(signedIn(), isTrue);
  });

  for (final (label, error) in [
    ('expired', _expired),
    ('unauthorized', _unauthorized),
  ]) {
    test('"$label" error: refreshes, retries once with the NEW token', () async {
      signIn();
      final tokensSeen = <String>[];

      final result = await run((token) async {
        tokensSeen.add(token);
        if (token == 'old-token') throw error;
        return 'ok';
      });

      expect(result, 'ok');
      expect(tokensSeen, ['old-token', 'new-token']);
      expect(auth.refreshCalls, 1);
      expect(container.read(authProvider).user!.token, 'new-token');
      expect(auth.logoutCalls, 0);
    });
  }

  test('refresh REJECTED: logs out and rethrows the original error', () async {
    signIn();
    auth.onRefresh = () => throw const AuthRejected('revoked', statusCode: 401);

    await expectLater(run<void>((_) => throw _expired), throwsA(_expired));
    expect(auth.logoutCalls, 1);
    expect(signedIn(), isFalse);
  });

  test('refresh UNREACHABLE: stays signed in, rethrows', () async {
    // The regression this file exists for: a dropped connection during
    // refresh says nothing about the session, so it must survive.
    signIn();
    auth.onRefresh = () => throw Exception('SocketException: Network is unreachable');

    await expectLater(run<void>((_) => throw _expired), throwsA(_expired));
    expect(auth.logoutCalls, 0);
    expect(signedIn(), isTrue);
    expect(container.read(authProvider).user!.token, 'old-token');
  });

  test('retry fails with a non-auth error: rethrown, still signed in', () async {
    signIn();
    final result = run<void>((token) {
      if (token == 'old-token') throw _expired;
      throw _serverDown;
    });

    await expectLater(result, throwsA(_serverDown));
    expect(auth.logoutCalls, 0);
    expect(signedIn(), isTrue);
  });

  test('retry still unauthorized and second refresh rejected: logs out', () async {
    signIn();
    var refreshes = 0;
    auth.onRefresh = () async {
      refreshes++;
      if (refreshes == 1) return 'new-token';
      throw const AuthRejected('revoked', statusCode: 401);
    };

    await expectLater(run<void>((_) => throw _expired), throwsA(_expired));
    expect(auth.refreshCalls, 2);
    expect(auth.logoutCalls, 1);
    expect(signedIn(), isFalse);
  });

  test('retry still unauthorized but second refresh unreachable: stays signed in',
      () async {
    signIn();
    var refreshes = 0;
    auth.onRefresh = () async {
      refreshes++;
      if (refreshes == 1) return 'new-token';
      throw Exception('TimeoutException');
    };

    await expectLater(run<void>((_) => throw _expired), throwsA(_expired));
    expect(auth.logoutCalls, 0);
    expect(signedIn(), isTrue);
  });

  test('concurrent 401s share ONE refresh', () async {
    // Refresh tokens rotate on every use server-side, so two parallel
    // refreshes would make the second present a superseded token and get a
    // spurious rejection -> logout. The dashboard fires several providers
    // at once on first build, which is exactly this case.
    signIn();
    Future<String> request(String token) async {
      if (token == 'old-token') throw _expired;
      return 'ok';
    }

    final results = await Future.wait([run(request), run(request), run(request)]);

    expect(results, ['ok', 'ok', 'ok']);
    expect(auth.refreshCalls, 1);
    expect(auth.logoutCalls, 0);
  });
}
