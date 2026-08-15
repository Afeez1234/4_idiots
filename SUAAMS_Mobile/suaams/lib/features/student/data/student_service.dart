import 'dart:convert';
import 'package:http/http.dart' as http;
import '../../../core/constants/api_constants.dart';
import '../models/student_dashboard_model.dart';
import '../models/today_protocol_entry.dart';
import '../models/notification_item.dart';
import '../models/course_attendance_history_model.dart';

/// Result of a /checkin/status poll. `reason` distinguishes a definite,
/// permanent failure ('not_enrolled') from a genuinely ambiguous "not
/// confirmed yet" (reason == null) -- NfcCheckInNotifier needs that
/// distinction to know whether to keep polling or stop immediately.
class CheckinStatusResult {
  final bool checkedIn;
  final String? reason; // 'not_enrolled', 'no_active_session', or null
  final String? courseCode;

  CheckinStatusResult({required this.checkedIn, this.reason, this.courseCode});
}

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
        final errorMsg =
            responseData['error'] ??
            responseData['msg'] ??
            responseData['message'] ??
            'Server returned status ${response.statusCode}';
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

      final errorMsg =
          responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  // Polls whether the ESP32 terminal actually relayed the beacon and Flask
  // recorded attendance -- see checkinStatusEndpoint's doc-comment in
  // api_constants.dart. Deliberately doesn't distinguish "not confirmed
  // yet" from most error responses (only truly unexpected ones throw) --
  // NfcCheckInNotifier treats a single failed poll as "try again next
  // tick", not a reason to abort the whole confirmation attempt, since the
  // actual check-in already happened over NFC.
  Future<CheckinStatusResult> checkCheckinStatus(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.checkinStatusEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return CheckinStatusResult(
          checkedIn: responseData['checked_in'] == true,
          reason: responseData['reason'] as String?,
          courseCode: responseData['course_code'] as String?,
        );
      }

      final errorMsg =
          responseData['error'] ??
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

      final errorMsg =
          responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  // Backs the notification list/inbox screen -- see notificationsEndpoint's
  // doc-comment in api_constants.dart and get_notifications in
  // api/student.py.
  Future<List<NotificationItem>> fetchNotifications(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.notificationsEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return (responseData['notifications'] as List)
            .map((entry) => NotificationItem.fromJson(entry))
            .toList();
      }

      final errorMsg =
          responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  Future<void> markNotificationRead(String token, int notificationId) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.markNotificationReadEndpoint(notificationId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return;
      }

      final errorMsg =
          responseData['error'] ??
          responseData['msg'] ??
          responseData['message'] ??
          'Server returned status ${response.statusCode}';
      throw Exception(errorMsg);
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  // Full per-session attendance breakdown for one course -- see
  // courseAttendanceHistoryEndpoint's doc-comment in api_constants.dart.
  Future<CourseAttendanceHistoryModel> fetchCourseAttendanceHistory(
    String token,
    int courseId,
  ) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.courseAttendanceHistoryEndpoint(courseId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        try {
          return CourseAttendanceHistoryModel.fromJson(responseData['data']);
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

  // Upserts this app instance's FCM token (see register_device_token in
  // api/student.py). Deliberately silent on failure -- called fire-and-
  // forget from NotificationService right after login/token-refresh, and a
  // failure here shouldn't surface as a user-facing error or block anything
  // else; the device just won't receive pushes until the next successful
  // sync attempt.
  Future<void> registerDeviceToken(
    String token,
    String fcmToken,
    String platform,
  ) async {
    await http.post(
      Uri.parse(ApiConstants.deviceTokenEndpoint),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $token',
      },
      body: jsonEncode({'fcm_token': fcmToken, 'platform': platform}),
    );
  }
}
