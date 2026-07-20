import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../../core/constants/api_constants.dart';
import '../models/student_dashboard_model.dart';
import '../models/today_protocol_entry.dart';

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

  // Mints the short-lived HCE beacon token used for check-in (see
  // checkinBeaconEndpoint doc-comment in api_constants.dart, and
  // BEACON_TOKEN_TTL_SECONDS in api/student.py for why this token is
  // separate from the long-lived session token passed in here).
  Future<String> mintCheckinBeacon(String token) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.checkinBeaconEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return responseData['beacon_token'] as String;
      }

      final errorMsg = responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  // Backs the "TODAY'S PROTOCOL" list -- see todayScheduleEndpoint's
  // doc-comment in api_constants.dart for why this is a separate call from
  // fetchDashboardData rather than folded into that response.
  Future<List<TodayProtocolEntry>> fetchTodaySchedule(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.todayScheduleEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return (responseData['today_protocol'] as List)
            .map((entry) => TodayProtocolEntry.fromJson(entry))
            .toList();
      }

      final errorMsg = responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }
}