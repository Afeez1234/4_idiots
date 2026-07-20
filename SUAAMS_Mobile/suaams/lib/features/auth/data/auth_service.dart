// This file handles secure authentication calls and platform-key storage.
// Optimized to prevent Android Keystore and iOS Secure Enclave execution deadlocks.

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../core/constants/api_constants.dart';
import '../models/auth_user.dart';

class AuthService {
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  Future<AuthUser> login(
    String username,
    String password,
    String deviceId,
  ) async {
    final response = await http.post(
      Uri.parse(ApiConstants.loginEndpoint),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'username': username,
        'password': password,
        'device_id': deviceId,
      }),
    );

    final Map<String, dynamic> responseData = jsonDecode(response.body);

    if (response.statusCode == 200 && responseData['success'] == true) {
      final String token = responseData['token'];
      // Stored alongside the access token but never surfaced on AuthUser --
      // only AuthService/AuthNotifier ever read it back (for
      // refreshAccessToken/logout below), keeping the more sensitive
      // long-lived credential out of the broader app state.
      final String refreshToken = responseData['refresh_token'];
      final Map<String, dynamic> userData = responseData['user'];

      // Grouping writes into a parallel pool ensures they commit to the hardware keystore
      // simultaneously and finish completely before we return control back to the UI router.
      await Future.wait([
        _secureStorage.write(key: 'jwt_token', value: token),
        _secureStorage.write(key: 'refresh_token', value: refreshToken),
        _secureStorage.write(key: 'user_role', value: userData['role']),
        _secureStorage.write(key: 'username', value: userData['username']),
        _secureStorage.write(
          key: 'requires_password_change',
          value: userData['requires_password_change'].toString(),
        ),
      ]).catchError((e) {
        debugPrint('Secure Storage write exception: $e');
        return [];
      });

      return AuthUser.fromJson(userData, token);
    } else {
      throw Exception(responseData['error'] ?? 'Login failed');
    }
  }

  // Returns the NEW access token on success (was `Future<bool>`). The
  // backend now rotates the session on password change (see
  // mobile_change_password in api/auth.py) -- it returns a fresh
  // access+refresh pair alongside the success response, so this needs to
  // persist and hand back the new access token rather than just a bool,
  // otherwise the caller (AuthNotifier.changePassword) would keep using
  // the pre-rotation token, which the server no longer recognizes as the
  // "current" one for refresh purposes.
  Future<String> changePassword(String newPassword, String token) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.changePasswordEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({'new_password': newPassword}),
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        final String newAccessToken = responseData['token'];
        final String newRefreshToken = responseData['refresh_token'];

        await Future.wait([
          _secureStorage.write(key: 'jwt_token', value: newAccessToken),
          _secureStorage.write(key: 'refresh_token', value: newRefreshToken),
          _secureStorage.write(key: 'requires_password_change', value: 'false'),
        ]).catchError((e) {
          debugPrint('Secure Storage write exception: $e');
          return [];
        });

        return newAccessToken;
      }

      try {
        final Map<String, dynamic> errorData = jsonDecode(response.body);
        throw Exception(
          errorData['error'] ?? errorData['msg'] ?? 'Failed to update code.',
        );
      } catch (e) {
        throw Exception('Server Error: ${response.statusCode}');
      }
    } catch (e) {
      rethrow;
    }
  }

  // Exchanges the stored refresh token for a new access+refresh pair (see
  // refreshEndpoint's doc-comment in api_constants.dart -- the backend
  // rotates on every call). Called by AuthNotifier.refreshSession(), which
  // is itself called by withAuthRetry (lib/core/network/auth_retry.dart)
  // whenever any authenticated API call gets a 401. Persists the new pair
  // to secure storage and returns the new access token; throws if the
  // refresh token is missing, expired, or has been revoked (device unbind,
  // explicit logout, or an earlier rotation already consumed it) -- the
  // caller is expected to treat any failure here as "force logout".
  Future<String> refreshAccessToken() async {
    final refreshToken = await getRefreshToken();
    if (refreshToken == null) {
      throw Exception('No refresh token available');
    }

    final response = await http.post(
      Uri.parse(ApiConstants.refreshEndpoint),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $refreshToken',
      },
    );

    final Map<String, dynamic> responseData = jsonDecode(response.body);

    if (response.statusCode == 200 && responseData['success'] == true) {
      final String newAccessToken = responseData['token'];
      final String newRefreshToken = responseData['refresh_token'];

      await Future.wait([
        _secureStorage.write(key: 'jwt_token', value: newAccessToken),
        _secureStorage.write(key: 'refresh_token', value: newRefreshToken),
      ]).catchError((e) {
        debugPrint('Secure Storage write exception: $e');
        return [];
      });

      return newAccessToken;
    }

    final errorMsg = responseData['error'] ??
        responseData['msg'] ??
        responseData['message'] ??
        'Session refresh failed';
    throw Exception(errorMsg);
  }

  Future<void> logout() async {
    // Best-effort: tell the backend to invalidate the refresh token
    // server-side (see mobile_logout in api/auth.py) before wiping local
    // storage. Wrapped so a network drop never blocks the user from
    // logging out locally -- worst case, the refresh token stays valid
    // server-side until it naturally expires (<=14 days) or gets revoked
    // some other way (e.g. device unbind), but the device itself no longer
    // has it once deleteAll() runs below.
    try {
      final refreshToken = await getRefreshToken();
      if (refreshToken != null) {
        await http.post(
          Uri.parse(ApiConstants.logoutEndpoint),
          headers: {'Authorization': 'Bearer $refreshToken'},
        );
      }
    } catch (e) {
      debugPrint('Logout backend call failed (continuing with local logout): $e');
    }

    await _secureStorage.deleteAll();
  }

  Future<String?> getToken() async {
    return await _secureStorage.read(key: 'jwt_token');
  }

  Future<String?> getRefreshToken() async {
    return await _secureStorage.read(key: 'refresh_token');
  }

  Future<String?> getUserRole() async {
    return await _secureStorage.read(key: 'user_role');
  }

  Future<String?> getUsername() async {
    return await _secureStorage.read(key: 'username');
  }

  Future<void> saveUsername(String username) async {
    await _secureStorage.write(key: 'username', value: username);
  }

  Future<bool> getPwdState() async {
    final value = await _secureStorage.read(key: 'requires_password_change');
    return value == 'true';
  }
}
