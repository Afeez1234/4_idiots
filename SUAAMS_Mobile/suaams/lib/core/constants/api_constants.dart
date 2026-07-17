//This file contains constants for API endpoints used in the SUAAMS app. It defines the base URL for the API and specific endpoints for authentication, student dashboard, attendance, courses, and notifications. The base URL can be switched between a local Flask server for testing and a production server on Render.

abstract final class ApiConstants {
  // Use 10.0.2.2 for Android Emulator connecting to local Flask server.
  // Replace with your Render URL for production (e.g., 'https://suaams.onrender.com/api/v1')
  // static const String baseUrl = 'http://10.0.2.2:5000/api/v1';//localhost for testing
  static const String baseUrl = 'https://suaams.onrender.com/api/v1';//for production
  
  static const String loginEndpoint = '$baseUrl/auth/login';
  static const String studentDashboardEndpoint = '$baseUrl/student/dashboard';
  static const String attendanceEndpoint = '$baseUrl/attendance';
  static const String studentCoursesEndpoint = '$baseUrl/student/courses';
  static const String notificationsEndpoint = '$baseUrl/student/notifications';
  static const String changePasswordEndpoint = '$baseUrl/auth/change-password';

  // Mints the short-lived HCE "beacon" token (see api/student.py on the
  // backend). This is a different endpoint from attendanceEndpoint above --
  // the phone calls this one over its normal authenticated connection to
  // get a token to broadcast; the ESP32 terminal is the one that later
  // posts that beacon token to POST /student/checkin (no Dart client for
  // that second endpoint since only hardware calls it).
  static const String checkinBeaconEndpoint = '$baseUrl/student/checkin/beacon';
}