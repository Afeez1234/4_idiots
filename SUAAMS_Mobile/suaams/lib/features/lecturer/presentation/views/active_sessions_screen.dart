import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Sessions tab root -- "Active sessions list". CourseWorkspaceScreen (the
// "Course workspace (same as above)" node in the nav map) is reused
// unchanged and pushed from here once this list is wired up to real data --
// see the courses list on the Home tab (lecturer_home_screen.dart) for the
// LecturerCourse.hasActiveSession/activeSessionId fields already available
// from the dashboard provider.
class ActiveSessionsScreen extends StatelessWidget {
  const ActiveSessionsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComingSoonScreen(
      title: 'Active Sessions',
      subtitle: 'A live list of your active sessions is coming soon.',
      icon: Icons.sensors_rounded,
    );
  }
}
