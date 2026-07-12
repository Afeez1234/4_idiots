import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../core/constants/api_constants.dart';
import '../models/auth_user.dart';

class AuthService {
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  Future<AuthUser> login(String username, String password) async {
    final response = await http.post(
      Uri.parse(ApiConstants.loginEndpoint),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({'username': username, 'password': password}),
    );

    final Map<String, dynamic> responseData = jsonDecode(response.body);

    if (response.statusCode == 200 && responseData['success'] == true) {
      final String token = responseData['token'];
      final Map<String, dynamic> userData = responseData['user'];

      await _secureStorage.write(key: 'jwt_token', value: token);
      await _secureStorage.write(key: 'user_role', value: userData['role']);
      await _secureStorage.write(key: 'username', value: userData['username']);
      await _secureStorage.write(
        key: 'requires_password_change',
        value: userData['requires_password_change'].toString(),
      );

      return AuthUser.fromJson(userData, token);
    } else {
      throw Exception(responseData['error'] ?? 'Login failed');
    }
  }

  Future<bool> changePassword(String newPassword, String token) async {
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
      await _secureStorage.write(
        key: 'requires_password_change',
        value: 'false',
      );
      return true;
    } else {
      throw Exception(
        responseData['error'] ?? 'Failed to update authorization code',
      );
    }
  }

  Future<void> logout() async {
    await _secureStorage.deleteAll();
  }

  Future<String?> getToken() async {
    return await _secureStorage.read(key: 'jwt_token');
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
}