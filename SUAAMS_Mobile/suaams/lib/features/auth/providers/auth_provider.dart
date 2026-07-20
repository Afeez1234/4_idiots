// This file is the brain of the auth feature. It holds the current auth state,
// exposes login, logout, changePassword, and session restoration actions,
// and notifies the router when auth state changes so navigation happens automatically.
import 'package:device_info_plus/device_info_plus.dart';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
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

  Future<void> checkExistingAuth() async {
    state = state.copyWith(isLoading: true);
    notifyListeners();

    final token = await _authService.getToken();
    final role = await _authService.getUserRole();
    final username = await _authService.getUsername();
    final reqPwdChange = await _authService.getPwdState();

    if (token != null && role != null && username != null) {
      state = state.copyWith(
        isLoading: false,
        user: AuthUser(
          id: 0,
          username: username,
          role: role,
          token: token,
          requiresPasswordChange: reqPwdChange,
        ),
      );
    } else {
      state = state.copyWith(isLoading: false);
    }
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

  Future<void> logout() async {
    await _authService.logout();
    state = AuthState();
    notifyListeners();
  }

  // Attempts to exchange the stored refresh token for a new access token,
  // updating in-memory state (and, via AuthService.refreshAccessToken,
  // secure storage) on success. Called by withAuthRetry
  // (lib/core/network/auth_retry.dart) whenever an authenticated API call
  // gets a 401 -- this is the "silent refresh" half of that flow. Returns
  // false (rather than throwing) on any failure -- expired/revoked refresh
  // token, no user in state, network error -- so the caller can decide to
  // force a logout without needing to unwrap an exception.
  Future<bool> refreshSession() async {
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
