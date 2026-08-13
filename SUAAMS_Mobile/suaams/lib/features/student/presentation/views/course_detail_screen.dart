import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Home > "Course detail (tap a course)". Reached by tapping
// a course in today's protocol list on the Home tab.
class CourseDetailScreen extends StatelessWidget {
  final int courseId;

  const CourseDetailScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: 'Course Detail',
      subtitle: 'Full detail view for course #$courseId is coming soon.',
      icon: Icons.menu_book_rounded,
    );
  }
}
