// This file handles secure authentication calls and platform-key storage.
// Optimized to prevent Android Keystore and iOS Secure Enclave execution deadlocks.

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../core/constants/api_constants.dart';
import '../models/auth_user.dart';

// The backend (suaams.onrender.com) is on Render's free tier, which spins
// the dyno down after ~15 minutes idle -- the next request has to cold-start
// it, commonly taking 20-40s. Long enough to tolerate a real cold start,
// short enough that a genuinely dead/unreachable server fails within a
// bounded time instead of leaving the caller's spinner stuck forever.
const _kNetworkTimeout = Duration(seconds: 20);

class AuthService {
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  Future<AuthUser> login(
    String username,
    String password,
    String deviceId,
  ) async {
    final http.Response response;
    try {
      response = await http
          .post(
            Uri.parse(ApiConstants.loginEndpoint),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({
              'username': username,
              'password': password,
              'device_id': deviceId,
            }),
          )
          .timeout(_kNetworkTimeout);
    } on TimeoutException {
      throw Exception(
        'Server is taking too long to respond. It may be waking up from idle -- please try again in a moment.',
      );
    }

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
      final response = await http
          .post(
            Uri.parse(ApiConstants.changePasswordEndpoint),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
            },
            body: jsonEncode({'new_password': newPassword}),
          )
          .timeout(_kNetworkTimeout);

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
    } on TimeoutException {
      throw Exception(
        'Server is taking too long to respond. It may be waking up from idle -- please try again in a moment.',
      );
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

    final response = await http
        .post(
          Uri.parse(ApiConstants.refreshEndpoint),
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer $refreshToken',
          },
        )
        .timeout(_kNetworkTimeout);

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

  // notifyServer: false skips the backend call entirely -- used when the
  // caller already knows the refresh token is dead (e.g.
  // AuthNotifier.checkExistingAuth() after a failed restore-time refresh),
  // so there's no point spending a network round trip just to have it
  // rejected. Defaults to true for every normal "sign out" call.
  Future<void> logout({bool notifyServer = true}) async {
    // Best-effort: tell the backend to invalidate the refresh token
    // server-side (see mobile_logout in api/auth.py). Deliberately NOT
    // awaited -- local logout (below) used to wait on this call, so a cold
    // backend (Render free tier, see _kNetworkTimeout above) made "Sign
    // Out" look like it did nothing for up to a minute. The token is read
    // here (before deleteAll wipes it) and the request fires in the
    // background; worst case it fails/times out and the refresh token just
    // stays valid server-side until it naturally expires (<=14 days) or
    // gets revoked some other way (e.g. device unbind) -- the device itself
    // no longer has it once deleteAll() runs below, so the user is signed
    // out locally either way.
    if (notifyServer) {
      final refreshToken = await getRefreshToken();
      if (refreshToken != null) {
        unawaited(_notifyServerLogout(refreshToken));
      }
    }

    await _secureStorage.deleteAll();
  }

  Future<void> _notifyServerLogout(String refreshToken) async {
    try {
      await http
          .post(
            Uri.parse(ApiConstants.logoutEndpoint),
            headers: {'Authorization': 'Bearer $refreshToken'},
          )
          .timeout(_kNetworkTimeout);
    } catch (e) {
      debugPrint('Logout backend call failed (continuing with local logout): $e');
    }
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
