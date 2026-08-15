import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
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
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
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
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono',
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),
              if (data.sessions.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: Text(
                      'No past sessions for this course yet.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                )
              else
                ...data.sessions.map(
                  (session) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _SessionRow(session: session, colorScheme: colorScheme),
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
                style: TextStyle(
                  fontSize: 10,
                  fontFamily: 'JetBrains Mono',
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
                style: const TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontWeight: FontWeight.bold,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                attendanceStatusLabel(session.status),
                style: TextStyle(
                  fontSize: 9,
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
