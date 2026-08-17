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

  WeekScheduleEntry({
    required this.dayOfWeek,
    required this.courseId,
    required this.courseName,
    required this.courseCode,
    this.startTime,
    this.endTime,
    this.room,
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
    );
  }
}
