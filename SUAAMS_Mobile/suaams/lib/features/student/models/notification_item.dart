// Mirrors the JSON shape returned by GET /api/v1/student/notifications (see
// get_notifications in api/student.py).
class NotificationItem {
  final int id;
  final String type; // 'attendance_marked' | 'device_unlocked' | 'device_lockout_alert'
  final String title;
  final String body;
  final Map<String, dynamic>? data;
  final bool read;
  final DateTime createdAt;

  NotificationItem({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    required this.data,
    required this.read,
    required this.createdAt,
  });

  factory NotificationItem.fromJson(Map<String, dynamic> json) {
    return NotificationItem(
      id: json['id'] as int,
      type: json['type'] as String,
      title: json['title'] as String,
      body: json['body'] as String,
      data: (json['data'] as Map?)?.cast<String, dynamic>(),
      read: json['read'] as bool? ?? false,
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }
}
