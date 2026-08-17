/// A course in the student's own department + the active semester, with
/// whether they're already registered -- backs the self-service course
/// registration screen. See get_available_courses in api/student.py.
class AvailableCourse {
  final int id;
  final String courseCode;
  final String courseTitle;
  final int? creditUnits;
  final String? lecturer;
  final bool enrolled;

  AvailableCourse({
    required this.id,
    required this.courseCode,
    required this.courseTitle,
    required this.creditUnits,
    required this.lecturer,
    required this.enrolled,
  });

  AvailableCourse copyWith({bool? enrolled}) {
    return AvailableCourse(
      id: id,
      courseCode: courseCode,
      courseTitle: courseTitle,
      creditUnits: creditUnits,
      lecturer: lecturer,
      enrolled: enrolled ?? this.enrolled,
    );
  }

  factory AvailableCourse.fromJson(Map<String, dynamic> json) {
    return AvailableCourse(
      id: json['id'] as int,
      courseCode: json['course_code'] as String,
      courseTitle: json['course_title'] as String,
      creditUnits: json['credit_units'] as int?,
      lecturer: json['lecturer'] as String?,
      enrolled: json['enrolled'] as bool,
    );
  }
}
