import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/shared/widgets/app_label_value_row.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/core/theme/app_terminal.dart';

// Reuses the already-loaded studentDashboardProvider -- RecentAttendance
// already carries everything this screen needs (course/date/time/status),
// so there's no separate fetch here, same reasoning as CourseDetailScreen.
// Only the last 10 records are ever in that list (see get_student_dashboard
// in api/student.py), which matches this screen only ever being reached by
// tapping a row that's currently on-screen in that same list.
class SessionDetailScreen extends ConsumerWidget {
  final String sessionId;

  const SessionDetailScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Session Detail')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load the session',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () =>
              ref.read(studentDashboardProvider.notifier).loadDashboardData(),
        ),
      );
    }

    final id = int.tryParse(sessionId);
    RecentAttendance? record;
    for (final r in data.recentAttendance) {
      if (r.sessionId == id) {
        record = r;
        break;
      }
    }

    if (record == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Session Detail')),
        body: const Center(child: Text('Record not found in recent history.')),
      );
    }

    final statusColor = attendanceStatusText(record.status, terminalOf(context));

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(record.course),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: statusColor.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 12,
                        height: 12,
                        decoration: BoxDecoration(
                          color: statusColor,
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: statusColor.withValues(alpha: 0.4),
                              blurRadius: 6,
                              spreadRadius: 1,
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(width: 10),
                      Text(
                        attendanceStatusLabel(record.status),
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 1.5,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  AppLabelValueRow(
                    'Course',
                    record.course,
                    padding: const EdgeInsets.only(bottom: 12),
                  ),
                  AppLabelValueRow(
                    'Date',
                    record.date,
                    padding: const EdgeInsets.only(bottom: 12),
                  ),
                  AppLabelValueRow(
                    'Time',
                    record.time,
                    padding: const EdgeInsets.only(bottom: 12),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
