// Mirrors the JSON shape returned by GET /api/v1/student/schedule/today
// (see api/student.py's get_today_schedule for the exact field names and
// the PENDING/PRESENT/ABSENT status logic).
class TodayProtocolEntry {
  final int courseId;
  final String courseName;
  final String courseCode;
  final String status; // 'PENDING' | 'PRESENT' | 'ABSENT'
  final bool sessionLive;
  final bool adHoc;
  final String? startTime;
  final String? endTime;
  final String? room;

  TodayProtocolEntry({
    required this.courseId,
    required this.courseName,
    required this.courseCode,
    required this.status,
    required this.sessionLive,
    this.adHoc = false,
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
      // Defaulted false rather than derived from `status`, because a
      // PENDING entry covers both "session running, not checked in yet"
      // and "lecturer hasn't started anything" -- see the comment in
      // api/student.py's get_today_schedule. Defaulting to false keeps
      // the check-in tap target disarmed when the field is absent, which
      // is the safe direction: an old backend leaves the card inert
      // rather than inviting a check-in the server will reject.
      sessionLive: json['session_live'] as bool? ?? false,
      // True when the lecturer started a session for a course with no
      // Timetable row today (a make-up class, an extra lab). Such a
      // session is checkable like any other -- the beacon mint never
      // consults the timetable -- so this only affects how it's labelled.
      adHoc: json['ad_hoc'] as bool? ?? false,
      startTime: json['start_time'] as String?,
      endTime: json['end_time'] as String?,
      room: json['room'] as String?,
    );
  }
}
