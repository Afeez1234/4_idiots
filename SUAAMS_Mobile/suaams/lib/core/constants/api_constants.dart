//This file contains constants for API endpoints used in the SUAAMS app. It defines the base URL for the API and specific endpoints for authentication, student dashboard, attendance, courses, and notifications. The base URL can be switched between a local Flask server for testing and a production server on Render.

abstract final class ApiConstants {
  // Use 10.0.2.2 for Android Emulator connecting to local Flask server.
  // Replace with your Render URL for production (e.g., 'https://suaams.onrender.com/api/v1')
  static const String baseUrl = 'http://10.0.2.2:5000/api/v1';//localhost for testing
  // static const String baseUrl = 'https://suaams.onrender.com/api/v1';//for production
  
  static const String loginEndpoint = '$baseUrl/auth/login';
  static const String studentDashboardEndpoint = '$baseUrl/student/dashboard';
  static const String attendanceEndpoint = '$baseUrl/attendance';
  static const String studentCoursesEndpoint = '$baseUrl/student/courses';
  static const String notificationsEndpoint = '$baseUrl/student/notifications';

}