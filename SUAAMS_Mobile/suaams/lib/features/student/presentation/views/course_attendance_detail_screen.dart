import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';
import '../../providers/course_attendance_history_provider.dart';
import '../../models/course_attendance_history_model.dart';

String _fmtTime(String? raw) {
  if (raw == null || raw.length < 5) return '--:--';
  return raw.substring(0, 5);
}

class CourseAttendanceDetailScreen extends ConsumerWidget {
  final int courseId;

  const CourseAttendanceDetailScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(courseAttendanceHistoryProvider(courseId));
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Course Attendance')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load attendance history',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () => ref
              .read(courseAttendanceHistoryProvider(courseId).notifier)
              .loadHistory(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(data.course.title),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () => ref
            .read(courseAttendanceHistoryProvider(courseId).notifier)
            .loadHistory(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                data.course.code,
                style: AppTheme.accent(
                  size: 11,
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),
              if (data.sessions.isEmpty)
                const AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.history_rounded,
                  title: 'No sessions yet',
                  message:
                      'Attendance appears here once this course has run a session.',
                  compact: true,
                )
              else
                ...data.sessions.map(
                  (session) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _SessionRow(
                      session: session,
                      colorScheme: colorScheme,
                    ),
                  ),
                ),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _SessionRow extends StatelessWidget {
  final CourseSessionAttendance session;
  final ColorScheme colorScheme;

  const _SessionRow({required this.session, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final statusColor = attendanceStatusColor(session.status);

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
                session.date ?? 'Unknown date',
                style: const TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              Text(
                '${_fmtTime(session.plannedStart)} – ${_fmtTime(session.plannedEnd)}',
                style: AppTheme.accent(
                  size: 10,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                session.timeIn ?? '--:--',
                style: AppTheme.accent(size: 12, weight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                attendanceStatusLabel(session.status),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: statusColor,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
