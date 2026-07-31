// Mirrors GET /api/v1/lecturer/dashboard's JSON shape -- see
// get_lecturer_dashboard in api/lecturer.py for the exact field names.
class LecturerDashboardModel {
  final LecturerProfile profile;
  final LecturerStats stats;
  final List<LecturerCourse> courses;

  LecturerDashboardModel({
    required this.profile,
    required this.stats,
    required this.courses,
  });

  factory LecturerDashboardModel.fromJson(Map<String, dynamic> json) {
    return LecturerDashboardModel(
      profile: LecturerProfile.fromJson(json['lecturer']),
      stats: LecturerStats.fromJson(json['stats']),
      courses: (json['courses'] as List)
          .map((course) => LecturerCourse.fromJson(course))
          .toList(),
    );
  }
}

class LecturerProfile {
  final String fullName;
  final String staffId;
  final String? department;

  LecturerProfile({
    required this.fullName,
    required this.staffId,
    this.department,
  });

  factory LecturerProfile.fromJson(Map<String, dynamic> json) {
    return LecturerProfile(
      fullName: json['full_name'] ?? 'Unknown Lecturer',
      staffId: json['staff_id'] ?? '',
      department: json['department'],
    );
  }
}

class LecturerStats {
  final int totalCourses;
  final int activeSessions;
  final int todayCheckins;

  LecturerStats({
    required this.totalCourses,
    required this.activeSessions,
    required this.todayCheckins,
  });

  factory LecturerStats.fromJson(Map<String, dynamic> json) {
    return LecturerStats(
      totalCourses: json['total_courses'] as int,
      activeSessions: json['active_sessions'] as int,
      todayCheckins: json['today_checkins'] as int,
    );
  }
}

class LecturerCourse {
  final int id;
  final String title;
  final String code;
  final int enrolledCount;
  final int totalSessions;
  final double avgAttendance;
  final bool hasActiveSession;
  final int? activeSessionId;

  LecturerCourse({
    required this.id,
    required this.title,
    required this.code,
    required this.enrolledCount,
    required this.totalSessions,
    required this.avgAttendance,
    required this.hasActiveSession,
    this.activeSessionId,
  });

  factory LecturerCourse.fromJson(Map<String, dynamic> json) {
    return LecturerCourse(
      id: json['id'] as int,
      title: json['title'] as String,
      code: json['code'] as String,
      enrolledCount: json['enrolled_count'] as int,
      totalSessions: json['total_sessions'] as int,
      avgAttendance: (json['avg_attendance'] as num).toDouble(),
      hasActiveSession: json['has_active_session'] as bool,
      activeSessionId: json['active_session_id'] as int?,
    );
  }
}
