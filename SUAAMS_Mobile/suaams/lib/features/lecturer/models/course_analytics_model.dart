import 'session_history_model.dart' show HistoryCourse;

// Mirrors GET /api/v1/lecturer/course/<id>/analytics's JSON shape -- see
// get_course_analytics in api/lecturer.py for the exact field names.
class CourseAnalyticsModel {
  final HistoryCourse course;
  final AnalyticsSummary summary;
  final List<AttendanceTrendPoint> trend;
  final List<StudentAttendanceStat> students;

  CourseAnalyticsModel({
    required this.course,
    required this.summary,
    required this.trend,
    required this.students,
  });

  factory CourseAnalyticsModel.fromJson(Map<String, dynamic> json) {
    return CourseAnalyticsModel(
      course: HistoryCourse.fromJson(json['course']),
      summary: AnalyticsSummary.fromJson(json['summary']),
      trend: (json['trend'] as List)
          .map((t) => AttendanceTrendPoint.fromJson(t))
          .toList(),
      students: (json['students'] as List)
          .map((s) => StudentAttendanceStat.fromJson(s))
          .toList(),
    );
  }
}

class AnalyticsSummary {
  final int enrolledCount;
  final int totalSessions;
  final double avgAttendance;

  AnalyticsSummary({
    required this.enrolledCount,
    required this.totalSessions,
    required this.avgAttendance,
  });

  factory AnalyticsSummary.fromJson(Map<String, dynamic> json) {
    return AnalyticsSummary(
      enrolledCount: json['enrolled_count'] as int,
      totalSessions: json['total_sessions'] as int,
      avgAttendance: (json['avg_attendance'] as num).toDouble(),
    );
  }
}

class AttendanceTrendPoint {
  final int sessionId;
  final String? date;
  final int presentCount;
  final int enrolledCount;
  final double pct;

  AttendanceTrendPoint({
    required this.sessionId,
    this.date,
    required this.presentCount,
    required this.enrolledCount,
    required this.pct,
  });

  factory AttendanceTrendPoint.fromJson(Map<String, dynamic> json) {
    return AttendanceTrendPoint(
      sessionId: json['session_id'] as int,
      date: json['date'] as String?,
      presentCount: json['present_count'] as int,
      enrolledCount: json['enrolled_count'] as int,
      pct: (json['pct'] as num).toDouble(),
    );
  }
}

class StudentAttendanceStat {
  final int studentId;
  final String fullName;
  final String matricNumber;
  final int attended;
  final int total;
  final double pct;

  StudentAttendanceStat({
    required this.studentId,
    required this.fullName,
    required this.matricNumber,
    required this.attended,
    required this.total,
    required this.pct,
  });

  factory StudentAttendanceStat.fromJson(Map<String, dynamic> json) {
    return StudentAttendanceStat(
      studentId: json['student_id'] as int,
      fullName: json['full_name'] as String,
      matricNumber: json['matric_number'] as String,
      attended: json['attended'] as int,
      total: json['total'] as int,
      pct: (json['pct'] as num).toDouble(),
    );
  }
}
