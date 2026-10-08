import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:suaams/core/constants/api_constants.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/features/student/models/today_protocol_entry.dart';
import 'package:suaams/features/student/models/notification_item.dart';
import 'package:suaams/features/student/models/course_attendance_history_model.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/features/student/models/device_info.dart';
import 'package:suaams/features/student/models/available_course_model.dart';
import 'package:suaams/features/student/models/student_announcement_model.dart';

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

/// Result of a `/checkin/beacon` mint.
///
/// Carries the server's `expires_in` alongside the beacon so the native
/// HCE service can arm its own expiry deadline from the authoritative
/// window. The native side is what actually enforces the window (a
/// monotonic `SystemClock.elapsedRealtime()` deadline plus a self-clear),
/// so feeding it Flask's own number keeps the app's countdown, the reader's
/// behaviour, and the server's acceptance window from drifting apart.
class BeaconMintResult {
  /// The beacon itself — 32 ASCII characters, small enough for the HCE
  /// service to answer a reader in a single APDU exchange.
  final String beaconToken;

  /// Seconds the server will accept this beacon for. Null if the server
  /// omitted it, in which case the native side falls back to its own
  /// default matching BEACON_TOKEN_TTL_SECONDS.
  final int? expiresIn;

  BeaconMintResult({required this.beaconToken, this.expiresIn});
}

/// Which check-in channels the server has switched on (/checkin/methods).
class CheckinMethods {
  final bool nfc;
  final bool ble;

  const CheckinMethods({required this.nfc, required this.ble});
}

/// Outcome of a Bluetooth check-in (/checkin/ble).
///
/// The server's "expected" refusals come back as a result rather than an
/// exception, deliberately. withAuthRetry treats any error mentioning
/// "expired" as a dead login, and the server's reply to a stale code is
/// "Invalid or expired code" -- thrown, it would trigger a pointless token
/// refresh and resubmit the same stale code.
class BleCheckinResult {
  final bool recorded; // true for a new record AND for "already marked"
  final String? reason; // 'invalid_code', 'no_active_session', or null
  final String? courseCode;

  const BleCheckinResult({required this.recorded, this.reason, this.courseCode});
}

class StudentService {
  Future<CheckinMethods> fetchCheckinMethods(String token) async {
    try {
      final response = await http
          .get(
            Uri.parse(ApiConstants.checkinMethodsEndpoint),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
            },
          )
          .timeout(const Duration(seconds: 12));

      final Map<String, dynamic> responseData = jsonDecode(response.body);
      if (response.statusCode == 200 && responseData['success'] == true) {
        return CheckinMethods(
          nfc: responseData['nfc'] == true,
          ble: responseData['ble'] == true,
        );
      }
      throw Exception(
        responseData['error'] ??
            responseData['msg'] ??
            'Server returned status ${response.statusCode}',
      );
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

  /// Posts the 14-byte payload heard from the terminal (as hex). See
  /// BleCheckinResult for why refusals are returned, not thrown.
  Future<BleCheckinResult> submitBleCheckin(
    String token, {
    required String payloadHex,
    required int rssi,
  }) async {
    try {
      final response = await http
          .post(
            Uri.parse(ApiConstants.checkinBleEndpoint),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
            },
            body: jsonEncode({'payload': payloadHex, 'rssi': rssi}),
          )
          // The code the phone heard is only good for ~10s, so a request
          // that takes longer than this was lost anyway; fail and let the
          // student retry with a fresh scan.
          .timeout(const Duration(seconds: 12));

      final Map<String, dynamic> responseData = jsonDecode(response.body);
      final reason = responseData['reason'] as String?;
      final courseCode = responseData['course_code'] as String?;

      if (response.statusCode == 200 && responseData['success'] == true) {
        return BleCheckinResult(recorded: true, courseCode: courseCode);
      }
      if (reason == 'invalid_code' || reason == 'no_active_session') {
        return BleCheckinResult(recorded: false, reason: reason);
      }
      throw Exception(
        responseData['error'] ??
            responseData['msg'] ??
            'Server returned status ${response.statusCode}',
      );
    } catch (e) {
      throw Exception(e.toString().replaceAll('Exception: ', ''));
    }
  }

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
  Future<BeaconMintResult> mintCheckinBeacon(String token) async {
    try {
      final response = await http
          .post(
            Uri.parse(ApiConstants.checkinBeaconEndpoint),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
            },
          )
          // A hung socket while Render is cold-starting used to leave the
          // UI stuck in `authenticating`, with no cancel that could
          // actually unblock it -- and force-quitting the app was
          // precisely what triggered the dispose race this flow used to
          // have. Fail fast instead: a 3-second-window beacon minted more
          // than 10 seconds ago is worthless anyway.
          .timeout(const Duration(seconds: 10));

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return BeaconMintResult(
          beaconToken: responseData['beacon_token'] as String,
          expiresIn: responseData['expires_in'] as int?,
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

  // Polls whether the ESP32 terminal actually relayed the beacon and Flask
  // recorded attendance -- see checkinStatusEndpoint's doc-comment in
  // api_constants.dart. Deliberately doesn't distinguish "not confirmed
  // yet" from most error responses (only truly unexpected ones throw) --
  // NfcCheckInNotifier treats a single failed poll as "try again next
  // tick", not a reason to abort the whole confirmation attempt, since the
  // actual check-in already happened over NFC.
  Future<CheckinStatusResult> checkCheckinStatus(String token) async {
    try {
      final response = await http
          .get(
            Uri.parse(ApiConstants.checkinStatusEndpoint),
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer $token',
            },
          )
          // Must be comfortably longer than a real response, not shorter.
          // This was 5s, which a slow Render free-tier dyno exceeded on a
          // routine check -- every poll timed out, so a check-in that had
          // genuinely been recorded was reported to the student as
          // "could not confirm". 12s still bounds a genuinely hung socket
          // (and NfcCheckInNotifier skips a new poll while one is in flight,
          // so this can't stack up), while giving a cold backend room to
          // actually answer.
          .timeout(const Duration(seconds: 12));

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

  // Backs the student Announcements screen -- see
  // studentAnnouncementsEndpoint's doc-comment in api_constants.dart and
  // get_student_announcements in api/student.py.
  //
  // Returns the unread count alongside the list rather than leaving the app
  // to count `!isRead` itself. The server owns the definition of "unread"
  // (via the last_seen_announcement_id watermark), and the nav badge is
  // rendered on every screen, so deriving it in two places would be a
  // standing invitation for them to disagree.
  Future<({List<StudentAnnouncement> items, int unreadCount})>
  fetchAnnouncements(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.studentAnnouncementsEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        final items = (responseData['announcements'] as List)
            .map((entry) => StudentAnnouncement.fromJson(entry))
            .toList();
        // Fall back to counting the list if the field is absent, so an
        // older backend still produces a correct badge rather than a
        // silently-zeroed one.
        final unread = responseData['unread_count'] as int? ??
            items.where((a) => !a.isRead).length;
        return (items: items, unreadCount: unread);
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

  /// Advance the server-side read watermark. Fire-and-forget: the badge is
  /// already cleared optimistically by the provider, so a failure here
  /// costs nothing until the next fetch corrects it.
  Future<void> markAnnouncementsSeen(String token, int announcementId) async {
    try {
      final response = await http.patch(
        Uri.parse(ApiConstants.markAnnouncementsSeenEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({'announcement_id': announcementId}),
      );
      if (response.statusCode != 200) {
        throw Exception('Failed to mark announcements seen: ${response.statusCode}');
      }
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

  // Full recurring weekly schedule -- see weekScheduleEndpoint's
  // doc-comment in api_constants.dart.
  Future<List<WeekScheduleEntry>> fetchWeekSchedule(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.weekScheduleEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return (responseData['week'] as List)
            .map((entry) => WeekScheduleEntry.fromJson(entry))
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

  // Read-only device-binding status -- see deviceInfoEndpoint's
  // doc-comment in api_constants.dart.
  Future<DeviceInfo> fetchDeviceInfo(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.deviceInfoEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        return DeviceInfo.fromJson(responseData['data']);
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

  // Backs the course registration screen -- see get_available_courses in
  // api/student.py. Returns every course in the student's own department +
  // the active semester, each flagged with whether they're already
  // enrolled, so Register/Drop can live in a single list.
  Future<List<AvailableCourse>> fetchAvailableCourses(String token) async {
    try {
      final response = await http.get(
        Uri.parse(ApiConstants.availableCoursesEndpoint),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 200 && responseData['success'] == true) {
        final courses = responseData['data']['courses'] as List;
        return courses
            .map((entry) => AvailableCourse.fromJson(entry))
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

  Future<void> registerCourse(String token, int courseId) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.registerCourseEndpoint(courseId)),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
      );

      final Map<String, dynamic> responseData = jsonDecode(response.body);

      if (response.statusCode == 201 && responseData['success'] == true) {
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

  Future<void> dropCourse(String token, int courseId) async {
    try {
      final response = await http.post(
        Uri.parse(ApiConstants.dropCourseEndpoint(courseId)),
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
}
