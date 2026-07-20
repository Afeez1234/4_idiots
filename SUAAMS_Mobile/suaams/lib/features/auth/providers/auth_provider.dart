// This file is the brain of the auth feature. It holds the current auth state,
// exposes login, logout, changePassword, and session restoration actions,
// and notifies the router when auth state changes so navigation happens automatically.
import 'package:device_info_plus/device_info_plus.dart';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:jwt_decoder/jwt_decoder.dart';
import '../data/auth_service.dart';
import '../models/auth_user.dart';

class AuthState {
  final bool isLoading;
  final AuthUser? user;
  final String? errorMessage;

  AuthState({this.isLoading = false, this.user, this.errorMessage});

  AuthState copyWith({bool? isLoading, AuthUser? user, String? errorMessage}) {
    return AuthState(
      isLoading: isLoading ?? this.isLoading,
      user: user ?? this.user,
      errorMessage: errorMessage,
    );
  }
}

final authServiceProvider = Provider<AuthService>((ref) => AuthService());

final authProvider = NotifierProvider<AuthNotifier, AuthState>(
  AuthNotifier.new,
);

class AuthNotifier extends Notifier<AuthState> with ChangeNotifier {
  AuthService get _authService => ref.read(authServiceProvider);

  @override
  AuthState build() {
    return AuthState();
  }

  // Helper method to securely get the unique hardware UUID
  Future<String> _getHardwareUUID() async {
    final DeviceInfoPlugin deviceInfo = DeviceInfoPlugin();
    try {
      if (Platform.isIOS) {
        final iosInfo = await deviceInfo.iosInfo;
        return iosInfo.identifierForVendor ?? 'unknown_ios_device';
      } else if (Platform.isAndroid) {
        final androidInfo = await deviceInfo.androidInfo;
        return androidInfo.id;
      }
    } catch (e) {
      return 'fallback_device_id';
    }
    return 'unknown_platform';
  }

  // RESTORE FIX: this previously trusted ANY stored token as "still logged
  // in" with zero expiry check, so an app restart after the access token
  // died (guaranteed after 30 min, see JWT_ACCESS_TOKEN_EXPIRES in app.py)
  // would still navigate to the destination screen -- the dead token was
  // only discovered later, when that screen's first API call 401'd. It
  // "worked" eventually (withAuthRetry silently refreshes on that 401), but
  // only after already flashing the wrong screen and burning a wasted
  // failed-then-retried round trip.
  //
  // Now: decode the access token locally (jwt_decoder -- already a
  // dependency, just never wired up) with no network call. If it's not
  // expired, proceed exactly as before. If it IS expired, attempt a silent
  // refresh via refreshSession() BEFORE deciding whether a session exists
  // at all -- only fall through to "no session" (state.user stays null,
  // which sends the splash screen to /login) if that refresh also fails,
  // meaning the refresh token itself is expired/revoked/missing.
  Future<void> checkExistingAuth() async {
    state = state.copyWith(isLoading: true);
    notifyListeners();

    final token = await _authService.getToken();
    final role = await _authService.getUserRole();
    final username = await _authService.getUsername();
    final reqPwdChange = await _authService.getPwdState();

    if (token == null || role == null || username == null) {
      state = state.copyWith(isLoading: false);
      notifyListeners();
      return;
    }

    // Provisionally set the user so refreshSession() below (which reads
    // state.user for the id/username/role/requiresPasswordChange it
    // preserves across the swap, and uses its mere presence as "is there a
    // session to refresh") has something to work with.
    state = state.copyWith(
      user: AuthUser(
        id: 0,
        username: username,
        role: role,
        token: token,
        requiresPasswordChange: reqPwdChange,
      ),
    );

    bool tokenLooksValid;
    try {
      tokenLooksValid = !JwtDecoder.isExpired(token);
    } catch (e) {
      // Malformed/corrupt stored token -- treat exactly like "expired"
      // rather than crashing restore.
      tokenLooksValid = false;
    }

    if (!tokenLooksValid) {
      final refreshed = await refreshSession();
      if (!refreshed) {
        // Refresh token is also invalid/expired/revoked (or missing) --
        // there's no real session here. notifyServer: false because we
        // already know the refresh token that logout() would otherwise
        // present to the backend is dead; no point making a network call
        // just to have it rejected.
        await logout(notifyServer: false);
        state = state.copyWith(isLoading: false);
        notifyListeners();
        return;
      }
    }

    state = state.copyWith(isLoading: false);
    notifyListeners();
  }

  Future<bool> login(String username, String password) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    notifyListeners();

    try {
      String deviceId = await _getHardwareUUID();
      final user = await _authService.login(username, password, deviceId);
      await _authService.saveUsername(user.username);
      state = state.copyWith(isLoading: false, user: user);
      notifyListeners();
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
      notifyListeners();
      return false;
    }
  }

  Future<bool> changePassword(String newPassword) async {
    state = state.copyWith(isLoading: true, errorMessage: null);
    notifyListeners();

    try {
      if (state.user == null) {
        throw Exception('Session corrupted. Please log in again.');
      }

      // FIX: this previously had NO expiry handling at all -- an expired
      // access token here just surfaced a raw error, same gap
      // today_schedule_provider.dart had before withAuthRetry
      // (lib/core/network/auth_retry.dart) was introduced. Not using
      // withAuthRetry itself here, though: it needs `Ref` to reach
      // authProvider.notifier from outside, but changePassword already IS
      // a method on that notifier -- so it calls refreshSession()/logout()
      // directly on itself instead, which also avoids a circular import
      // (auth_retry.dart already imports this file for `authProvider`).
      Future<String> attempt() =>
          _authService.changePassword(newPassword, state.user!.token);

      // The backend rotates the session on a successful password change
      // (see mobile_change_password in api/auth.py), so `attempt()`
      // returns a NEW access token that must be used below -- not
      // whatever was in state.user.token before this call.
      String newAccessToken;
      try {
        newAccessToken = await attempt();
      } catch (e) {
        final msg = e.toString().toLowerCase();
        final looksExpired = msg.contains('expired') || msg.contains('unauthorized');
        if (!looksExpired) rethrow;

        final refreshed = await refreshSession();
        if (!refreshed) {
          await logout();
          rethrow;
        }
        newAccessToken = await attempt(); // retry once with the now-refreshed token
      }

      final currentUser = state.user!;
      state = state.copyWith(
        isLoading: false,
        user: AuthUser(
          id: currentUser.id,
          username: currentUser.username,
          role: currentUser.role,
          token: newAccessToken,
          requiresPasswordChange: false,
        ),
      );
      notifyListeners();
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
      notifyListeners();
      return false;
    }
  }

  // notifyServer: false skips the backend /logout call entirely -- used by
  // checkExistingAuth() above when we've already confirmed the refresh
  // token is dead (expired/revoked/missing), so there's no point making a
  // network call just to have it rejected. Every other caller (the actual
  // "sign out" button, etc.) keeps the default of telling the backend.
  Future<void> logout({bool notifyServer = true}) async {
    await _authService.logout(notifyServer: notifyServer);
    state = AuthState();
    notifyListeners();
  }

  // Memoizes the in-flight refresh so concurrent callers share ONE
  // outcome instead of each firing an independent /refresh request. This
  // matters because refresh tokens rotate on every use (see
  // mobile_refresh in api/auth.py): if two providers both discover an
  // expired access token around the same time
  // (e.g. studentDashboardProvider and todayScheduleProvider both firing
  // on the dashboard's first build) and each called
  // _authService.refreshAccessToken() independently, the first call's
  // response would rotate the stored refresh token, and the second call
  // -- still holding the now-superseded refresh token -- would get
  // rejected as "revoked" even though the session is completely fine.
  // That would incorrectly force a logout on a perfectly good session,
  // purely from client-side timing, not an actual problem with the token.
  //
  // `_inFlightRefresh ??= ...` assigns the Future synchronously on the
  // first call; any call that arrives before that Future completes sees
  // it already set and awaits the SAME Future instead of starting a new
  // one. whenComplete clears it again once done (success or failure) so
  // the *next* time the token expires, a fresh refresh can run.
  Future<bool>? _inFlightRefresh;

  // Attempts to exchange the stored refresh token for a new access token,
  // updating in-memory state (and, via AuthService.refreshAccessToken,
  // secure storage) on success. Called by withAuthRetry
  // (lib/core/network/auth_retry.dart) whenever an authenticated API call
  // gets a 401, by checkExistingAuth() on restore, and directly by
  // changePassword() above -- this is the single "silent refresh" used by
  // all three. Returns false (rather than throwing) on any failure --
  // expired/revoked refresh token, no user in state, network error -- so
  // callers can decide to force a logout without needing to unwrap an
  // exception.
  Future<bool> refreshSession() {
    return _inFlightRefresh ??= _performRefresh().whenComplete(() {
      _inFlightRefresh = null;
    });
  }

  Future<bool> _performRefresh() async {
    final currentUser = state.user;
    if (currentUser == null) return false;

    try {
      final newAccessToken = await _authService.refreshAccessToken();
      state = state.copyWith(
        user: AuthUser(
          id: currentUser.id,
          username: currentUser.username,
          role: currentUser.role,
          token: newAccessToken,
          requiresPasswordChange: currentUser.requiresPasswordChange,
        ),
      );
      notifyListeners();
      return true;
    } catch (e) {
      return false;
    }
  }
}
