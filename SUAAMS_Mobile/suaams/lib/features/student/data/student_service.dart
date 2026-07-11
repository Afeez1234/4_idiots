import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../../core/constants/api_constants.dart';
import '../models/student_dashboard_model.dart';

class StudentService {
  // 1. Receive the token directly from RAM to avoid hardware storage race conditions
  Future<StudentDashboardModel> fetchDashboardData(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.studentDashboardEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      // 2. Safely parse data or catch specific JSON structure errors
      if (response.statusCode == 200 && responseData['success'] == true) {
        try {
          return StudentDashboardModel.fromJson(responseData['data']);
        } catch (parseError) {
          throw Exception('Data parsing error: $parseError');
        }
      } else {
        // 3. Extract exact error from Flask or Flask-JWT-Extended
        final errorMsg = responseData['error'] ?? responseData['msg'] ?? responseData['message'] ?? 'Server returned status ${response.statusCode}';
        throw Exception(errorMsg);
      }
    } catch (e) {
      // 4. Catch offline network drops or HTML 500 errors
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }
}