// Mirrors GET /api/v1/student/announcements's JSON shape -- see
// get_student_announcements in api/student.py. Unlike the lecturer-side
// AnnouncementItem (always course-scoped), this carries `scope` since a
// student can see university-wide and department notices too, not just
// course ones.
class StudentAnnouncement {
  final int id;
  final String title;
  final String body;
  final String scope; // 'university' | 'department' | 'course'
  final String? departmentName;
  final String? courseCode;
  final String? createdAt;

  StudentAnnouncement({
    required this.id,
    required this.title,
    required this.body,
    required this.scope,
    this.departmentName,
    this.courseCode,
    this.createdAt,
  });

  factory StudentAnnouncement.fromJson(Map<String, dynamic> json) {
    return StudentAnnouncement(
      id: json['id'] as int,
      title: json['title'] as String,
      body: json['body'] as String,
      scope: json['scope'] as String,
      departmentName: json['department_name'] as String?,
      courseCode: json['course_code'] as String?,
      createdAt: json['created_at'] as String?,
    );
  }
}
