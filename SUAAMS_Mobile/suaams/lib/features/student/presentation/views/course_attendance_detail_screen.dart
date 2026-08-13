import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Attendance > "Course attendance detail (tap a course)".
class CourseAttendanceDetailScreen extends StatelessWidget {
  final int courseId;

  const CourseAttendanceDetailScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: 'Course Attendance',
      subtitle:
          'Per-session attendance breakdown for course #$courseId is coming soon.',
      icon: Icons.fact_check_rounded,
    );
  }
}
