// Mirrors GET /api/v1/student/schedule/week's JSON shape -- see
// get_week_schedule in api/student.py. dayOfWeek is 0=Monday..6=Sunday,
// matching Timetable.day_of_week's documented convention (models.py) and
// Python's date.weekday(), so no conversion is needed anywhere this is used.
class WeekScheduleEntry {
  final int dayOfWeek;
  final int courseId;
  final String courseName;
  final String courseCode;
  final String? startTime;
  final String? endTime;
  final String? room;
  // Every lecturer on the course, coordinator first, comma-separated
  // (Course.lecturer_names on the server). Null from a server that predates
  // it (2026-11-01), or for a course with nobody assigned.
  final String? lecturer;

  WeekScheduleEntry({
    required this.dayOfWeek,
    required this.courseId,
    required this.courseName,
    required this.courseCode,
    this.startTime,
    this.endTime,
    this.room,
    this.lecturer,
  });

  factory WeekScheduleEntry.fromJson(Map<String, dynamic> json) {
    return WeekScheduleEntry(
      dayOfWeek: json['day_of_week'] as int,
      courseId: json['course_id'] as int,
      courseName: json['course_name'] as String,
      courseCode: json['course_code'] as String,
      startTime: json['start_time'] as String?,
      endTime: json['end_time'] as String?,
      room: json['room'] as String?,
      lecturer: json['lecturer'] as String?,
    );
  }
}
