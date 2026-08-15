import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/session_detail_provider.dart';
import '../../models/session_detail_model.dart';

String _fmtTime(String? raw) {
  if (raw == null || raw.length < 5) return '--:--';
  return raw.substring(0, 5);
}

class LecturerSessionDetailScreen extends ConsumerWidget {
  final int courseId;
  final String sessionId;

  const LecturerSessionDetailScreen({
    super.key,
    required this.courseId,
    required this.sessionId,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final args = (courseId: courseId, sessionId: int.parse(sessionId));
    final state = ref.watch(sessionDetailProvider(args));
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

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(data.session.date ?? data.course.title),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(sessionDetailProvider(args).notifier).loadDetail(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${data.course.code} · ${_fmtTime(data.session.plannedStart)}–${_fmtTime(data.session.plannedEnd)}',
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono',
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),

              _StatsGrid(stats: data.stats, colorScheme: colorScheme),
              const SizedBox(height: 32),

              const Text(
                'ATTENDANCE',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.5,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),

              if (data.attendance.isEmpty)
                const Text(
                  'No check-ins recorded for this session.',
                  style: TextStyle(color: Colors.grey),
                )
              else
                ...data.attendance.map(
                  (record) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _AttendanceCard(
                      record: record,
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

class _StatsGrid extends StatelessWidget {
  final SessionDetailStats stats;
  final ColorScheme colorScheme;

  const _StatsGrid({required this.stats, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _StatBox(
          val: '${stats.presentCount}',
          label: 'PRESENT',
          colorScheme: colorScheme,
          highlight: true,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${stats.absentCount}',
          label: 'ABSENT',
          colorScheme: colorScheme,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${stats.enrolledCount}',
          label: 'ENROLLED',
          colorScheme: colorScheme,
        ),
      ],
    );
  }
}

class _StatBox extends StatelessWidget {
  final String val;
  final String label;
  final ColorScheme colorScheme;
  final bool highlight;

  const _StatBox({
    required this.val,
    required this.label,
    required this.colorScheme,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: highlight
              ? const Color(0xFF10B981).withValues(alpha: 0.12)
              : colorScheme.surfaceContainer.withValues(alpha: 0.78),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: highlight
                ? const Color(0xFF10B981).withValues(alpha: 0.35)
                : colorScheme.outline.withValues(alpha: 0.14),
          ),
        ),
        child: Column(
          children: [
            Text(
              val,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 18,
                color: highlight
                    ? const Color(0xFF10B981)
                    : colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 8,
                letterSpacing: 1,
                fontWeight: FontWeight.bold,
                color: highlight
                    ? const Color(0xFF10B981).withValues(alpha: 0.9)
                    : colorScheme.onSurface.withValues(alpha: 0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AttendanceCard extends StatelessWidget {
  final SessionAttendanceRecord record;
  final ColorScheme colorScheme;

  const _AttendanceCard({required this.record, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final isPresent = record.status.toLowerCase() == 'present';
    final statusColor = isPresent
        ? const Color(0xFF10B981)
        : colorScheme.onSurface.withValues(alpha: 0.5);

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
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  record.fullName,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  record.matricNumber,
                  style: TextStyle(
                    fontSize: 10,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                record.timeIn ?? '--:--',
                style: const TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontWeight: FontWeight.bold,
                  fontSize: 12,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                record.status.toUpperCase(),
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
