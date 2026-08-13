import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../../core/constants/api_constants.dart';
import '../models/lecturer_dashboard_model.dart';
import '../models/course_workspace_model.dart';

class LecturerService {
  Future<LecturerDashboardModel> fetchDashboardData(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.lecturerDashboardEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        try {
          return LecturerDashboardModel.fromJson(responseData['data']);
        } catch (parseError) {
          throw Exception('Data parsing error: $parseError');
        }
      } else {
        final errorMsg =
            responseData['error'] ??
            responseData['msg'] ??
            responseData['message'] ??
            'Server returned status ${response.statusCode}';
        throw Exception(errorMsg);
      }
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  Future<CourseWorkspaceModel> fetchCourseWorkspace(
    String token,
    int courseId,
  ) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.courseWorkspaceEndpoint(courseId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        try {
          return CourseWorkspaceModel.fromJson(responseData['data']);
        } catch (parseError) {
          throw Exception('Data parsing error: $parseError');
        }
      } else {
        final errorMsg =
            responseData['error'] ??
            responseData['msg'] ??
            responseData['message'] ??
            'Server returned status ${response.statusCode}';
        throw Exception(errorMsg);
      }
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  // plannedStart/plannedEnd are "HH:MM" strings straight from a time
  // picker, or null -- api/lecturer.py's start_session parses them into
  // real datetime.time objects server-side (see BUG FIX comment there for
  // why that parsing has to happen; this client just passes the raw
  // strings through).
  Future<void> startSession(
    String token,
    int courseId, {
    String? plannedStart,
    String? plannedEnd,
  }) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.startSessionEndpoint(courseId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'planned_start': ?plannedStart,
          'planned_end': ?plannedEnd,
        }),
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (!(response.statusCode == 201 && responseData['success'] == true)) {
        final errorMsg =
            responseData['error'] ??
            responseData['msg'] ??
            responseData['message'] ??
            'Server returned status ${response.statusCode}';
        throw Exception(errorMsg);
      }
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  Future<void> endSession(String token, int courseId) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.endSessionEndpoint(courseId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (!(response.statusCode == 200 && responseData['success'] == true)) {
        final errorMsg =
            responseData['error'] ??
            responseData['msg'] ??
            responseData['message'] ??
            'Server returned status ${response.statusCode}';
        throw Exception(errorMsg);
      }
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }
}
