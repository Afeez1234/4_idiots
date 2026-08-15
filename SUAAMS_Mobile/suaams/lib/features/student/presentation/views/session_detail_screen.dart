import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';

// Reuses the already-loaded studentDashboardProvider -- RecentAttendance
// already carries everything this screen needs (course/date/time/present),
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
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
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
        body: const Center(
          child: Text('Record not found in recent history.'),
        ),
      );
    }

    final statusColor = record.present
        ? const Color(0xFF10B981)
        : const Color(0xFFEF4444);

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
                        record.present ? 'PRESENT' : 'ABSENT',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.5,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),
                  _DetailRow(label: 'Course', value: record.course),
                  _DetailRow(label: 'Date', value: record.date),
                  _DetailRow(label: 'Time', value: record.time),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DetailRow extends StatelessWidget {
  final String label;
  final String value;

  const _DetailRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label.toUpperCase(),
            style: const TextStyle(
              fontSize: 10,
              letterSpacing: 1,
              fontWeight: FontWeight.bold,
              color: Colors.grey,
            ),
          ),
          Text(
            value,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.bold,
              fontFamily: 'JetBrains Mono',
            ),
          ),
        ],
      ),
    );
  }
}
