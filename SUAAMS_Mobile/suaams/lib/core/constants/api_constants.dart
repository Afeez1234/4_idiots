//This file contains constants for API endpoints used in the SUAAMS app. It defines the base URL for the API and specific endpoints for authentication, student dashboard, attendance, courses, and notifications. The base URL can be switched between a local Flask server for testing and a production server on Render.

abstract final class ApiConstants {
  // Use 10.0.2.2 for Android Emulator connecting to local Flask server.
  static const String baseUrl = 'http://10.0.2.2:5000/api/v1';//localhost for testing
  // static const String baseUrl = 'https://suaams.onrender.com/api/v1';//for production
  
  static const String loginEndpoint = '$baseUrl/auth/login';
  static const String studentDashboardEndpoint = '$baseUrl/student/dashboard';
  static const String attendanceEndpoint = '$baseUrl/attendance';
  static const String studentCoursesEndpoint = '$baseUrl/student/courses';
  static const String notificationsEndpoint = '$baseUrl/student/notifications';

  // Registers/refreshes this app instance's FCM token (see
  // register_device_token in api/student.py) -- called once after login and
  // again whenever Firebase hands the app a new token via onTokenRefresh.
  static const String deviceTokenEndpoint = '$baseUrl/student/device-token';

  static String markNotificationReadEndpoint(int notificationId) =>
      '$baseUrl/student/notifications/$notificationId/read';
  static const String changePasswordEndpoint = '$baseUrl/auth/change-password';

  // Exchanges a refresh token (sent as the Authorization bearer) for a new
  // access+refresh pair -- see mobile_refresh in api/auth.py. Rotates on
  // every call: the old refresh token stops working the moment a new one
  // is issued.
  static const String refreshEndpoint = '$baseUrl/auth/refresh';

  // Invalidates the current refresh token server-side (also sent as the
  // Authorization bearer, not the access token -- see mobile_logout in
  // api/auth.py for why).
  static const String logoutEndpoint = '$baseUrl/auth/logout';

  // Mints the short-lived HCE "beacon" token (see api/student.py on the
  // backend). This is a different endpoint from attendanceEndpoint above --
  // the phone calls this one over its normal authenticated connection to
  // get a token to broadcast; the ESP32 terminal is the one that later
  // posts that beacon token to POST /student/checkin (no Dart client for
  // that second endpoint since only hardware calls it).
  static const String checkinBeaconEndpoint = '$baseUrl/student/checkin/beacon';

  // Polled by the app after broadcasting a beacon, to find out whether the
  // ESP32 terminal actually relayed it and Flask recorded attendance --
  // the beacon broadcast itself is one-way (phone -> ESP32 -> Flask), so
  // this is the only way the app learns the outcome. See
  // NfcCheckInNotifier's confirming/unconfirmed states.
  static const String checkinStatusEndpoint = '$baseUrl/student/checkin/status';

  // Backs the "TODAY'S PROTOCOL" list on the student dashboard home tab.
  // Deliberately separate from studentDashboardEndpoint above -- dashboard
  // stats barely change, but a course's status here changes live as a
  // lecturer starts/ends a session and the student checks in, so it has
  // its own refresh cadence (see today_schedule_provider.dart).
  static const String todayScheduleEndpoint = '$baseUrl/student/schedule/today';

  // Full per-session attendance breakdown for one course, scoped to this
  // student -- see get_course_attendance_history in api/student.py.
  static String courseAttendanceHistoryEndpoint(int courseId) =>
      '$baseUrl/student/course/$courseId/history';

  // Lecturer mobile endpoints (see api/lecturer.py). courseWorkspaceEndpoint/
  // startSessionEndpoint/endSessionEndpoint take the course id as a path
  // segment, so they're functions rather than plain consts like the ones
  // above.
  static const String lecturerDashboardEndpoint = '$baseUrl/lecturer/dashboard';

  static String courseWorkspaceEndpoint(int courseId) =>
      '$baseUrl/lecturer/course/$courseId';

  static String startSessionEndpoint(int courseId) =>
      '$baseUrl/lecturer/course/$courseId/start-session';

  static String endSessionEndpoint(int courseId) =>
      '$baseUrl/lecturer/course/$courseId/end-session';

  static String sessionHistoryEndpoint(int courseId) =>
      '$baseUrl/lecturer/course/$courseId/history';

  static String sessionDetailEndpoint(int courseId, int sessionId) =>
      '$baseUrl/lecturer/course/$courseId/session/$sessionId';
}