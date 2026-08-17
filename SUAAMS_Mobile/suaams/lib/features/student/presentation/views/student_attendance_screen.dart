import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'courses_view.dart';

// Attendance tab root -- "Overview (overall rate, at-risk courses)" in the
// navigation map. CoursesView already renders exactly this (per-course
// attendance % with health-color coding), so it's reused as-is here; only
// the AppBar chrome and the entry point into Session History are new.
class StudentAttendanceScreen extends StatelessWidget {
  const StudentAttendanceScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Attendance'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
        actions: [
          TextButton.icon(
            onPressed: () => context.push('/student/attendance/register'),
            icon: const Icon(Icons.add_circle_outline_rounded, size: 18),
            label: const Text('REGISTER'),
          ),
          TextButton.icon(
            onPressed: () => context.push('/student/attendance/history'),
            icon: const Icon(Icons.history_rounded, size: 18),
            label: const Text('HISTORY'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: const CoursesView(),
    );
  }
}
