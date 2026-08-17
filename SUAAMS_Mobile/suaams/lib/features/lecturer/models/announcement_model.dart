// Mirrors GET /api/v1/lecturer/announcements's JSON shape -- see
// get_lecturer_announcements in api/lecturer.py.
class AnnouncementItem {
  final int id;
  final String title;
  final String body;
  final int courseId;
  final String? courseCode;
  final String? createdAt;

  AnnouncementItem({
    required this.id,
    required this.title,
    required this.body,
    required this.courseId,
    this.courseCode,
    this.createdAt,
  });

  factory AnnouncementItem.fromJson(Map<String, dynamic> json) {
    return AnnouncementItem(
      id: json['id'] as int,
      title: json['title'] as String,
      body: json['body'] as String,
      courseId: json['course_id'] as int,
      courseCode: json['course_code'] as String?,
      createdAt: json['created_at'] as String?,
    );
  }
}
