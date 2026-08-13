import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Reports > "Course attendance analytics". The sibling
// "Export PDF/Excel" node in the nav map is an action within this screen
// (not a separate route) once built.
class CourseAnalyticsScreen extends StatelessWidget {
  final int courseId;

  const CourseAnalyticsScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: 'Course Analytics',
      subtitle: 'Attendance analytics for course #$courseId are coming soon.',
      icon: Icons.insights_rounded,
    );
  }
}
