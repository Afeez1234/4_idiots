import 'package:suaams/features/lecturer/models/session_history_model.dart' show HistoryCourse;

// Mirrors GET /api/v1/lecturer/course/<id>/session/<id>'s JSON shape -- see
// get_session_detail in api/lecturer.py for the exact field names. Reuses
// HistoryCourse from session_history_model.dart since both endpoints return
// the identical {id, title, code} course shape.
class SessionDetailModel {
  final HistoryCourse course;
  final SessionInfo session;
  final SessionDetailStats stats;
  final List<SessionAttendanceRecord> attendance;
  // Enrolled students with no record yet -- the ones the lecturer can mark
  // present by hand. `not_checked_in` in the JSON.
  final List<NotCheckedInStudent> notCheckedIn;

  SessionDetailModel({
    required this.course,
    required this.session,
    required this.stats,
    required this.attendance,
    required this.notCheckedIn,
  });

  factory SessionDetailModel.fromJson(Map<String, dynamic> json) {
    return SessionDetailModel(
      course: HistoryCourse.fromJson(json['course']),
      session: SessionInfo.fromJson(json['session']),
      stats: SessionDetailStats.fromJson(json['stats']),
      attendance: (json['attendance'] as List)
          .map((a) => SessionAttendanceRecord.fromJson(a))
          .toList(),
      // `?? const []` so this build still reads a server that predates
      // manual marking (deploy order: backend first, but don't crash if not).
      notCheckedIn: ((json['not_checked_in'] as List?) ?? const [])
          .map((s) => NotCheckedInStudent.fromJson(s))
          .toList(),
    );
  }
}

class SessionInfo {
  final int id;
  final String? date;
  final String? plannedStart;
  final String? plannedEnd;
  // Live vs. ended. Manual marking works on both; this only changes wording.
  final bool isActive;

  SessionInfo({
    required this.id,
    this.date,
    this.plannedStart,
    this.plannedEnd,
    this.isActive = false,
  });

  factory SessionInfo.fromJson(Map<String, dynamic> json) {
    return SessionInfo(
      id: json['id'] as int,
      date: json['date'] as String?,
      plannedStart: json['planned_start'] as String?,
      plannedEnd: json['planned_end'] as String?,
      isActive: json['is_active'] as bool? ?? false,
    );
  }
}

class NotCheckedInStudent {
  final int studentId;
  final String fullName;
  final String matricNumber;

  NotCheckedInStudent({
    required this.studentId,
    required this.fullName,
    required this.matricNumber,
  });

  factory NotCheckedInStudent.fromJson(Map<String, dynamic> json) {
    return NotCheckedInStudent(
      studentId: json['student_id'] as int,
      fullName: json['full_name'] as String,
      matricNumber: json['matric_number'] as String,
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
  // String, not int -- Student.level is db.String(20) in the schema
  // (values like "400L"), kept as a string deliberately to avoid a
  // migration that would fail casting non-numeric values (see models.py).
  final String level;
  final String? department;
  final String? timeIn;
  final String status;
  // 'nfc' | 'ble' | 'manual' | 'rfid', or null for rows recorded before
  // Attendance.method existed. Shown so a lecturer can tell a tap from a
  // Bluetooth code from a hand mark.
  final String? method;

  SessionAttendanceRecord({
    required this.fullName,
    required this.matricNumber,
    required this.level,
    this.department,
    this.timeIn,
    required this.status,
    this.method,
  });

  factory SessionAttendanceRecord.fromJson(Map<String, dynamic> json) {
    return SessionAttendanceRecord(
      fullName: json['full_name'] as String,
      matricNumber: json['matric_number'] as String,
      level: json['level']?.toString() ?? 'N/A',
      department: json['department'] as String?,
      timeIn: json['time_in'] as String?,
      status: json['status'] as String,
      method: json['method'] as String?,
    );
  }
}
