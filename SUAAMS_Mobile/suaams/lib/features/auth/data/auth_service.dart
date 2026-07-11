//This file talks to flask and handles the login/logout process, as well as storing the JWT securely on the phone's hardware.Note 2-AleshMoney

import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../../../core/constants/api_constants.dart';
import '../models/auth_user.dart';

class AuthService {
  // Initialize the secure vault for storing the JWT on the hardware
  final FlutterSecureStorage _secureStorage = const FlutterSecureStorage();

  // The login function (returns an AuthUser if successful, throws an Exception if it fails)
  Future<AuthUser> login(String username, String password) async {
    // 1. Prepare the JSON payload exactly like we did in Postman
    final Map<String, String> payload = {
      'username': username,
      'password': password,
    };

    // 2. Fire the HTTP POST request to Flask
    final response = await http.post(
      Uri.parse(ApiConstants.loginEndpoint),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode(payload),
    );

    // 3. Decode the raw JSON string into a Dart Map
    final Map<String, dynamic> responseData = jsonDecode(response.body);

    // 4. Check the status code
    if (response.statusCode == 200 && responseData['success'] == true) {
      // Extract the token and the user object
      final String token = responseData['token'];
      final Map<String, dynamic> userData = responseData['user'];

      // Save the token securely to the phone's hardware storage
      await _secureStorage.write(key: 'jwt_token', value: token);
      await _secureStorage.write(key: 'user_role', value: userData['role']);
      await _secureStorage.write(key: 'username', value: userData['username']);

        // Return the structured Dart object
      return AuthUser.fromJson(userData, token);
    } else {
      // If Flask returned 401, 403, or 404, throw the exact error message
      throw Exception(responseData['error'] ?? 'Login failed');
    }
  
  }


  // A helper function to log the user out by wiping the vault
  Future<void> logout() async {
    await _secureStorage.delete(key: 'jwt_token');
    await _secureStorage.delete(key: 'user_role');
    await _secureStorage.delete(key: 'username');
  }
  // A helper function to retrieve the JWT token from secure storage
  Future<String?> getToken() async {
    return await _secureStorage.read(key: 'jwt_token');
  }
  // A helper function to retrieve the user role from secure storage
  Future<String?> getUserRole() async {
    return await _secureStorage.read(key: 'user_role');
  }
  // A helper function to retrieve the username from secure storage
  Future<String?> getUsername() async {
    return await _secureStorage.read(key: 'username');
  }
  //a helper function to save the username to secure storage
  Future<void> saveUsername(String username) async {
    await _secureStorage.write(key: 'username', value: username);
  } 

}
