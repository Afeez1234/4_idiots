// Mirrors GET /api/v1/lecturer/course/<id>'s JSON shape -- see
// get_course_workspace in api/lecturer.py for the exact field names.
class CourseWorkspaceModel {
  final WorkspaceCourse course;
  final WorkspaceStats stats;
  final ActiveSessionInfo? activeSession;
  final List<LiveAttendanceEntry> liveAttendance;

  CourseWorkspaceModel({
    required this.course,
    required this.stats,
    this.activeSession,
    required this.liveAttendance,
  });

  factory CourseWorkspaceModel.fromJson(Map<String, dynamic> json) {
    return CourseWorkspaceModel(
      course: WorkspaceCourse.fromJson(json['course']),
      stats: WorkspaceStats.fromJson(json['stats']),
      activeSession: json['active_session'] != null
          ? ActiveSessionInfo.fromJson(json['active_session'])
          : null,
      liveAttendance: (json['live_attendance'] as List)
          .map((entry) => LiveAttendanceEntry.fromJson(entry))
          .toList(),
    );
  }
}

class WorkspaceCourse {
  final int id;
  final String title;
  final String code;

  WorkspaceCourse({required this.id, required this.title, required this.code});

  factory WorkspaceCourse.fromJson(Map<String, dynamic> json) {
    return WorkspaceCourse(
      id: json['id'] as int,
      title: json['title'] as String,
      code: json['code'] as String,
    );
  }
}

class WorkspaceStats {
  final int enrolledCount;
  final int totalSessions;
  final double avgAttendance;
  final int presentNow;

  WorkspaceStats({
    required this.enrolledCount,
    required this.totalSessions,
    required this.avgAttendance,
    required this.presentNow,
  });

  factory WorkspaceStats.fromJson(Map<String, dynamic> json) {
    return WorkspaceStats(
      enrolledCount: json['enrolled_count'] as int,
      totalSessions: json['total_sessions'] as int,
      avgAttendance: (json['avg_attendance'] as num).toDouble(),
      presentNow: json['present_now'] as int,
    );
  }
}

class ActiveSessionInfo {
  final int id;
  final String? plannedStart;
  final String? plannedEnd;
  final String sessionDate;

  ActiveSessionInfo({
    required this.id,
    this.plannedStart,
    this.plannedEnd,
    required this.sessionDate,
  });

  factory ActiveSessionInfo.fromJson(Map<String, dynamic> json) {
    return ActiveSessionInfo(
      id: json['id'] as int,
      plannedStart: json['planned_start'] as String?,
      plannedEnd: json['planned_end'] as String?,
      sessionDate: json['session_date'] as String,
    );
  }
}

class LiveAttendanceEntry {
  final String fullName;
  final String matricNumber;
  // String, not int -- Student.level is db.String(20) in the schema
  // (values like "400L"), kept as a string deliberately to avoid a
  // migration that would fail casting non-numeric values (see models.py).
  // Was declared `int` here, which threw "type 'String' is not a subtype
  // of type 'int'" the moment a live-attendance list actually rendered a
  // real student -- caught via an on-device walkthrough, not the analyzer.
  final String level;
  final String? department;
  final String? timeIn;
  final String status;

  LiveAttendanceEntry({
    required this.fullName,
    required this.matricNumber,
    required this.level,
    this.department,
    this.timeIn,
    required this.status,
  });

  factory LiveAttendanceEntry.fromJson(Map<String, dynamic> json) {
    return LiveAttendanceEntry(
      fullName: json['full_name'] as String,
      matricNumber: json['matric_number'] as String,
      level: json['level']?.toString() ?? 'N/A',
      department: json['department'] as String?,
      timeIn: json['time_in'] as String?,
      status: json['status'] as String,
    );
  }
}
