import 'session_history_model.dart' show HistoryCourse;

// Mirrors GET /api/v1/lecturer/course/<id>/session/<id>'s JSON shape -- see
// get_session_detail in api/lecturer.py for the exact field names. Reuses
// HistoryCourse from session_history_model.dart since both endpoints return
// the identical {id, title, code} course shape.
class SessionDetailModel {
  final HistoryCourse course;
  final SessionInfo session;
  final SessionDetailStats stats;
  final List<SessionAttendanceRecord> attendance;

  SessionDetailModel({
    required this.course,
    required this.session,
    required this.stats,
    required this.attendance,
  });

  factory SessionDetailModel.fromJson(Map<String, dynamic> json) {
    return SessionDetailModel(
      course: HistoryCourse.fromJson(json['course']),
      session: SessionInfo.fromJson(json['session']),
      stats: SessionDetailStats.fromJson(json['stats']),
      attendance: (json['attendance'] as List)
          .map((a) => SessionAttendanceRecord.fromJson(a))
          .toList(),
    );
  }
}

class SessionInfo {
  final int id;
  final String? date;
  final String? plannedStart;
  final String? plannedEnd;

  SessionInfo({required this.id, this.date, this.plannedStart, this.plannedEnd});

  factory SessionInfo.fromJson(Map<String, dynamic> json) {
    return SessionInfo(
      id: json['id'] as int,
      date: json['date'] as String?,
      plannedStart: json['planned_start'] as String?,
      plannedEnd: json['planned_end'] as String?,
    );
  }
}

class SessionDetailStats {
  final int presentCount;
  final int absentCount;
  final int enrolledCount;

  SessionDetailStats({
    required this.presentCount,
    required this.absentCount,
    required this.enrolledCount,
  });

  factory SessionDetailStats.fromJson(Map<String, dynamic> json) {
    return SessionDetailStats(
      presentCount: json['present_count'] as int,
      absentCount: json['absent_count'] as int,
      enrolledCount: json['enrolled_count'] as int,
    );
  }
}

class SessionAttendanceRecord {
  final String fullName;
  final String matricNumber;
  final int level;
  final String? department;
  final String? timeIn;
  final String status;

  SessionAttendanceRecord({
    required this.fullName,
    required this.matricNumber,
    required this.level,
    this.department,
    this.timeIn,
    required this.status,
  });

  factory SessionAttendanceRecord.fromJson(Map<String, dynamic> json) {
    return SessionAttendanceRecord(
      fullName: json['full_name'] as String,
      matricNumber: json['matric_number'] as String,
      level: json['level'] as int,
      department: json['department'] as String?,
      timeIn: json['time_in'] as String?,
      status: json['status'] as String,
    );
  }
}
