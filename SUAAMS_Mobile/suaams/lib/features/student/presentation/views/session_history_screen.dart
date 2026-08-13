import 'package:flutter/material.dart';
import 'records_view.dart';

// Attendance > "Session history (tap a session)". RecordsView already
// renders the full chronological attendance log (filterable, grouped by
// month) -- reused as-is, just wrapped with its own AppBar now that it's a
// pushed route instead of a bottom-nav tab body.
//
// Per-session tap-through isn't wired up yet: RecentAttendance (the model
// RecordsView renders) doesn't carry a session id from the backend, only
// course/date/time/present -- see student_dashboard_model.dart. Add an id
// there once api/student.py's dashboard endpoint exposes one, then wire
// _buildLogEntry's tap to push '/student/attendance/history/session/:id'.
class SessionHistoryScreen extends StatelessWidget {
  const SessionHistoryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Session History'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: const RecordsView(),
    );
  }
}
