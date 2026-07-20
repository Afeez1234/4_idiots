// Mirrors the JSON shape returned by GET /api/v1/student/schedule/today
// (see api/student.py's get_today_schedule for the exact field names and
// the PENDING/PRESENT/ABSENT status logic).
class TodayProtocolEntry {
  final int courseId;
  final String courseName;
  final String courseCode;
  final String status; // 'PENDING' | 'PRESENT' | 'ABSENT'
  final String? startTime;
  final String? endTime;
  final String? room;

  TodayProtocolEntry({
    required this.courseId,
    required this.courseName,
    required this.courseCode,
    required this.status,
    this.startTime,
    this.endTime,
    this.room,
  });

  factory TodayProtocolEntry.fromJson(Map<String, dynamic> json) {
    return TodayProtocolEntry(
      courseId: json['course_id'] as int,
      courseName: json['course_name'] as String,
      courseCode: json['course_code'] as String,
      status: json['status'] as String? ?? 'PENDING',
      startTime: json['start_time'] as String?,
      endTime: json['end_time'] as String?,
      room: json['room'] as String?,
    );
  }
}
