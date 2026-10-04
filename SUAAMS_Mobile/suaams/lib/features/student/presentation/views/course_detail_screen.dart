import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/network/user_facing_error.dart';

// Reuses the already-loaded studentDashboardProvider -- CourseBreakdown
// already carries everything this screen needs (id/name/code/pct/attended/
// total), and recentAttendance's course-code strings let this filter down
// to just this course's records, so there's no separate fetch here, same
// reasoning as ActiveSessionsScreen on the lecturer side.
class CourseDetailScreen extends ConsumerWidget {
  final int courseId;

  const CourseDetailScreen({super.key, required this.courseId});

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
        appBar: AppBar(title: const Text('Course Detail')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load this course',
          message: isGenericServerMessage(state.errorMessage)
                      ? 'Check your connection and try again.'
                      : state.errorMessage,
          onRetry: () =>
              ref.read(studentDashboardProvider.notifier).loadDashboardData(),
        ),
      );
    }

    CourseBreakdown? course;
    for (final c in data.courses) {
      if (c.id == courseId) {
        course = c;
        break;
      }
    }

    if (course == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Course Detail')),
        body: const Center(child: Text('Course not found.')),
      );
    }

    final relatedRecords = data.recentAttendance
        .where((r) => r.course == course!.code)
        .toList();

    final isAtRisk = course.pct < 75;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(course.name),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              course.code,
              style: AppTheme.accent(
                size: 11,
                letterSpacing: 1,
                color: colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(height: 24),

            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: isAtRisk
                    ? colorScheme.errorContainer.withValues(alpha: 0.12)
                    : colorScheme.surfaceContainer,
                borderRadius: BorderRadius.circular(16),
                border: Border(
                  left: BorderSide(
                    color: isAtRisk
                        ? colorScheme.error
                        : AppStatus.success,
                    width: 4,
                  ),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    isAtRisk ? 'BELOW 75% THRESHOLD' : 'ATTENDANCE ON TRACK',
                    style: TextStyle(
                      fontSize: 10,
                      letterSpacing: 1.5,
                      fontWeight: FontWeight.bold,
                      color: isAtRisk
                          ? colorScheme.error
                          : AppStatus.success,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${course.pct}%',
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 32,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${course.attended} of ${course.total} sessions attended',
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 32),

            Text(
              'RECENT ATTENDANCE',
              style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
            ),
            const SizedBox(height: 16),

            if (relatedRecords.isEmpty)
              AppStateView(
                kind: AppStateKind.empty,
                icon: Icons.event_note_rounded,
                title: 'No records yet',
                message: 'Attendance for this course will appear here.',
                compact: true,
              )
            else
              ...relatedRecords.map(
                (record) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _RecordCard(record: record, colorScheme: colorScheme),
                ),
              ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }
}

class _RecordCard extends StatelessWidget {
  final RecentAttendance record;
  final ColorScheme colorScheme;

  const _RecordCard({required this.record, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final statusColor = attendanceStatusText(record.status, terminalOf(context));

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                record.date,
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text(
                record.time,
                style: AppTheme.accent(
                  size: 10,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: statusColor.withValues(alpha: 0.3)),
            ),
            child: Text(
              attendanceStatusLabel(record.status),
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                letterSpacing: 0.5,
                color: statusColor,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
