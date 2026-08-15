class StudentDashboardModel {
  final StudentProfile profile;
  final DashboardStats stats;
  final List<CourseBreakdown> courses;
  final List<RecentAttendance> recentAttendance;

  StudentDashboardModel({
    required this.profile,
    required this.stats,
    required this.courses,
    required this.recentAttendance,
  });

  factory StudentDashboardModel.fromJson(Map<String, dynamic> json) {
    return StudentDashboardModel(
      profile: StudentProfile.fromJson(json['student']),
      stats: DashboardStats.fromJson(json['stats']),
      courses: (json['courses'] as List)
          .map((course) => CourseBreakdown.fromJson(course))
          .toList(),
      recentAttendance: (json['recent_attendance'] as List)
          .map((attendance) => RecentAttendance.fromJson(attendance))
          .toList(),
    );
  }
}

class StudentProfile {
  final String fullName;
  final String department;
  final String level;
  final String?
  rfidUid; // Nullable in case a student hasn't been issued an RFID yet
  final String matricNumber;

  StudentProfile({
    required this.fullName,
    required this.department,
    required this.level,
    this.rfidUid,
    required this.matricNumber,
  });

  factory StudentProfile.fromJson(Map<String, dynamic> json) {
    return StudentProfile(
      fullName: json['full_name'] ?? 'Unknown Student',
      department: json['department'] ?? 'Unknown Dept',
      level:
          json['level']?.toString() ??
          'N/A', // .toString() protects us if DB sends an int
      rfidUid: json['rfid_uid'],
      matricNumber: json['matric_number'] ?? '',
    );
  }
}

class DashboardStats {
  final double overallRate;
  final int attendanceCount;
  final int totalSessions;
  final int atRiskCount;
  final int enrollmentCount;

  DashboardStats({
    required this.overallRate,
    required this.attendanceCount,
    required this.totalSessions,
    required this.atRiskCount,
    required this.enrollmentCount,
  });

  factory DashboardStats.fromJson(Map<String, dynamic> json) {
    return DashboardStats(
      // We use (json['...'] as num).toDouble() because JSON sometimes sends whole numbers (85)
      // instead of floats (85.0), which causes Dart to crash if explicitly cast as double.
      overallRate: (json['overall_rate'] as num).toDouble(),
      attendanceCount: json['attendance_count'] as int,
      totalSessions: json['total_sessions'] as int,
      atRiskCount: json['at_risk_count'] as int,
      enrollmentCount: json['enrollment_count'] as int,
    );
  }
}

class CourseBreakdown {
  final int id;
  final String name;
  final String code;
  final double pct;
  final int attended;
  final int total;

  CourseBreakdown({
    required this.id,
    required this.name,
    required this.code,
    required this.pct,
    required this.attended,
    required this.total,
  });

  factory CourseBreakdown.fromJson(Map<String, dynamic> json) {
    return CourseBreakdown(
      id: json['id'] as int,
      name: json['name'] as String,
      code: json['code'] as String,
      pct: (json['pct'] as num).toDouble(),
      attended: json['attended'] as int,
      total: json['total'] as int,
    );
  }
}

class RecentAttendance {
  final String course;
  final String date;
  final String time;
  final String status; // 'present' | 'late' | 'absent' | 'excused'
  final int sessionId;

  RecentAttendance({
    required this.course,
    required this.date,
    required this.time,
    required this.status,
    required this.sessionId,
  });

  factory RecentAttendance.fromJson(Map<String, dynamic> json) {
    return RecentAttendance(
      course: json['course'] as String,
      date: json['date'] as String,
      time: json['time'] as String,
      status: json['status'] as String,
      sessionId: json['session_id'] as int,
    );
  }
}
