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
      final user = state.user;
      if (user == null) {
        throw Exception('Session corrupted. Please log in again.');
      }
      await _authService.changePassword(newPassword, user.token);

      state = state.copyWith(
        isLoading: false,
        user: AuthUser(
          id: user.id,
          username: user.username,
          role: user.role,
          token: user.token,
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
}
