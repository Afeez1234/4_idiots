// Mirrors GET /api/v1/student/course/<id>/history's JSON shape -- see
// get_course_attendance_history in api/student.py for the exact field
// names. Kept separate from the lecturer feature's HistoryCourse (same
// {id, title, code} shape) so student/ and lecturer/ stay self-contained.
class CourseAttendanceHistoryModel {
  final AttendanceHistoryCourse course;
  final List<CourseSessionAttendance> sessions;

  CourseAttendanceHistoryModel({required this.course, required this.sessions});

  factory CourseAttendanceHistoryModel.fromJson(Map<String, dynamic> json) {
    return CourseAttendanceHistoryModel(
      course: AttendanceHistoryCourse.fromJson(json['course']),
      sessions: (json['sessions'] as List)
          .map((s) => CourseSessionAttendance.fromJson(s))
          .toList(),
    );
  }
}

class AttendanceHistoryCourse {
  final int id;
  final String title;
  final String code;

  AttendanceHistoryCourse({
    required this.id,
    required this.title,
    required this.code,
  });

  factory AttendanceHistoryCourse.fromJson(Map<String, dynamic> json) {
    return AttendanceHistoryCourse(
      id: json['id'] as int,
      title: json['title'] as String,
      code: json['code'] as String,
    );
  }
}

class CourseSessionAttendance {
  final int sessionId;
  final String? date;
  final String? plannedStart;
  final String? plannedEnd;
  final String status; // 'present' | 'absent' | 'late' | 'excused'
  final String? timeIn;

  CourseSessionAttendance({
    required this.sessionId,
    this.date,
    this.plannedStart,
    this.plannedEnd,
    required this.status,
    this.timeIn,
  });

  factory CourseSessionAttendance.fromJson(Map<String, dynamic> json) {
    return CourseSessionAttendance(
      sessionId: json['session_id'] as int,
      date: json['date'] as String?,
      plannedStart: json['planned_start'] as String?,
      plannedEnd: json['planned_end'] as String?,
      status: json['status'] as String,
      timeIn: json['time_in'] as String?,
    );
  }
}
