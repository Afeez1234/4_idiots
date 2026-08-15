// Mirrors GET /api/v1/lecturer/course/<id>/history's JSON shape -- see
// get_session_history in api/lecturer.py for the exact field names.
class SessionHistoryModel {
  final HistoryCourse course;
  final List<SessionSummary> sessions;

  SessionHistoryModel({required this.course, required this.sessions});

  factory SessionHistoryModel.fromJson(Map<String, dynamic> json) {
    return SessionHistoryModel(
      course: HistoryCourse.fromJson(json['course']),
      sessions: (json['sessions'] as List)
          .map((s) => SessionSummary.fromJson(s))
          .toList(),
    );
  }
}

class HistoryCourse {
  final int id;
  final String title;
  final String code;

  HistoryCourse({required this.id, required this.title, required this.code});

  factory HistoryCourse.fromJson(Map<String, dynamic> json) {
    return HistoryCourse(
      id: json['id'] as int,
      title: json['title'] as String,
      code: json['code'] as String,
    );
  }
}

class SessionSummary {
  final int sessionId;
  final String? date;
  // "HH:MM:SS" strings (Python str(time)) or null -- see formatTimeOfDay
  // (lecturer_session_history_screen.dart) for display formatting.
  final String? plannedStart;
  final String? plannedEnd;
  final int presentCount;
  final int absentCount;
  final int enrolledCount;

  SessionSummary({
    required this.sessionId,
    this.date,
    this.plannedStart,
    this.plannedEnd,
    required this.presentCount,
    required this.absentCount,
    required this.enrolledCount,
  });

  factory SessionSummary.fromJson(Map<String, dynamic> json) {
    return SessionSummary(
      sessionId: json['session_id'] as int,
      date: json['date'] as String?,
      plannedStart: json['planned_start'] as String?,
      plannedEnd: json['planned_end'] as String?,
      presentCount: json['present_count'] as int,
      absentCount: json['absent_count'] as int,
      enrolledCount: json['enrolled_count'] as int,
    );
  }
}
