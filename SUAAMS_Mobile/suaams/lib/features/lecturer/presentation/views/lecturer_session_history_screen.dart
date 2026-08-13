import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Course workspace > "Session history".
class LecturerSessionHistoryScreen extends StatelessWidget {
  final int courseId;

  const LecturerSessionHistoryScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: 'Session History',
      subtitle: 'Past sessions for course #$courseId are coming soon.',
      icon: Icons.history_rounded,
    );
  }
}
