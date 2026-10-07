// This file is the brain of the auth feature. It holds the current auth state,
// exposes login, logout, changePassword, and session restoration actions,
// and notifies the router when auth state changes so navigation happens automatically.
import 'package:android_id/android_id.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:jwt_decoder/jwt_decoder.dart';
import 'package:suaams/features/auth/data/auth_service.dart';
import 'package:suaams/features/auth/models/auth_user.dart';
import 'package:suaams/core/services/notification_service.dart';
import 'package:suaams/core/network/user_facing_error.dart';


/// Outcome of a token refresh.
///
/// The distinction this carries is the whole fix. `refreshSession` used to
/// return a plain bool, and every caller treated `false` as "session dead,
/// log them out". But a refresh can fail because the SERVER rejected the
/// token (session genuinely dead, wiping local state is correct) or because
/// the NETWORK dropped and we never got to ask (session may be perfectly
/// fine). Collapsing those meant one dead spot in a lecture hall could
/// destroy a 14-day session.
enum RefreshOutcome {
  /// New access token obtained; session continues.
  refreshed,

  /// Server rejected the token. The stored session is worthless.
  rejected,

  /// Could not reach the server, or it timed out. Session state untouched
  /// and still assumed valid -- retry when signal returns.
  unreachable,
}

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

  // Helper method to securely get the unique hardware UUID.
  //
  // Throws rather than returning a placeholder when the ID can't be read.
  // It used to fall back to fixed strings ('fallback_device_id' etc.), and
  // since every failing phone sent the SAME string, they all looked like one
  // device to the backend -- any of them could log into an account bound to
  // it. With one-account-per-phone enforced server-side, a shared placeholder
  // would also block every student after the first. The backend now rejects
  // those strings too, for builds that still send them.
  Future<String> _getHardwareUUID() async {
    String? id;
    try {
      if (Platform.isIOS) {
        // identifierForVendor can be nil briefly after a restart, before
        // the first unlock -- a retry a moment later normally succeeds.
        final iosInfo = await DeviceInfoPlugin().iosInfo;
        id = iosInfo.identifierForVendor;
      } else if (Platform.isAndroid) {
        // DEVICE-BINDING FIX: androidInfo.id (device_info_plus) is
        // Build.ID -- an OS build/firmware string, identical across every
        // device flashed with the same image (e.g. two phones on the same
        // stock ROM release). It is NOT a per-device identifier, so it
        // silently defeated the "lock account to this phone" security
        // model whenever two demo devices shared a build. ANDROID_ID
        // (Settings.Secure.ANDROID_ID, via the android_id package) is a
        // random value generated per device+app-signing-key at first boot
        // -- the standard per-device identifier Android actually exposes,
        // now that raw IMEI/serial access requires a system-level
        // permission apps can't hold.
        id = await const AndroidId().getId();
      }
    } catch (e) {
      debugPrint('[auth] hardware ID read failed: $e');
    }
    if (id == null || id.isEmpty) {
      throw Exception('Device identity unavailable');
    }
    return id;
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
      final outcome = await refreshSession();
      if (outcome == RefreshOutcome.rejected) {
        // The server told us this session is dead. Only now is wiping the
        // stored credentials correct. notifyServer: false because we
        // already know the refresh token that logout() would otherwise
        // present to the backend is dead; no point making a network call
        // just to have it rejected.
        await logout(notifyServer: false);
        state = state.copyWith(isLoading: false);
        notifyListeners();
        return;
      }
      // unreachable: we could not ask the server, so we do not know that
      // the session is dead. Falling through keeps the user signed in --
      // the access token is stale, but the refresh token is untouched and
      // every authenticated call routes through withAuthRetry, which will
      // refresh on the first request that gets signal. Previously this
      // destroyed a 14-day session because a phone opened on bad wifi.
    }

    state = state.copyWith(isLoading: false);
    notifyListeners();
    // Covers all branches above (token still valid, refreshed just now, or
    // simply unreachable) -- in every case a session still exists and is
    // worth syncing a push token against.
    unawaited(NotificationService.instance.syncDeviceToken());
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
      // Fire-and-forget, same reasoning as AuthService's own
      // _notifyServerLogout: a push-token sync failure shouldn't block or
      // fail the login itself, since it isn't part of the auth flow's own
      // success/failure condition.
      unawaited(NotificationService.instance.syncDeviceToken());
      return true;
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
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

        final outcome = await refreshSession();
        if (outcome != RefreshOutcome.refreshed) {
          // Same rule as withAuthRetry: only an actual rejection from the
          // server means the session is dead. An unreachable refresh means
          // we never got to ask, so destroying the stored tokens here would
          // sign the user out over a network blip.
          if (outcome == RefreshOutcome.rejected) {
            await logout();
          }
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
        errorMessage: userFacingError(e),
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
  Future<RefreshOutcome>? _inFlightRefresh;

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
  Future<RefreshOutcome> refreshSession() {
    return _inFlightRefresh ??= _performRefresh().whenComplete(() {
      _inFlightRefresh = null;
    });
  }

  Future<RefreshOutcome> _performRefresh() async {
    final currentUser = state.user;
    if (currentUser == null) return RefreshOutcome.rejected;

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
      return RefreshOutcome.refreshed;
    } on AuthRejected {
      // The server said no. That is the only outcome that justifies
      // destroying locally-stored credentials.
      return RefreshOutcome.rejected;
    } catch (e) {
      // Transport failure: ClientException, SocketException, Timeout, or a
      // malformed response. We do not know anything about the token's
      // validity, so we must not assume it is dead.
      debugPrint('[auth] token refresh unreachable, session preserved: $e');
      return RefreshOutcome.unreachable;
    }
  }
}
