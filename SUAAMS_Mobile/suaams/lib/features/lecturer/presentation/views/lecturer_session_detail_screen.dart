import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/lecturer/providers/session_detail_provider.dart';
import 'package:suaams/features/lecturer/models/session_detail_model.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';

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
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load the session',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () =>
              ref.read(sessionDetailProvider(args).notifier).loadDetail(),
        ),
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
                style: AppTheme.accent(
                  size: 11,
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),

              _StatsGrid(stats: data.stats),
              const SizedBox(height: 32),

              Text(
                'ATTENDANCE',
                style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),

              if (data.attendance.isEmpty)
                const AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.contactless_rounded,
                  title: 'No check-ins yet',
                  message: 'Students appear here as they tap the terminal.',
                  compact: true,
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

  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return AppStatRow([
      // ABSENT is left neutral here on purpose. It reads like it wants to
      // be the red box, but the old copy highlighted PRESENT green and
      // left ABSENT plain, and changing that is a visual decision, not a
      // refactor. Flagged rather than silently altered.
      AppStatValue.success('${stats.presentCount}', 'PRESENT'),
      AppStatValue('${stats.absentCount}', 'ABSENT'),
      AppStatValue('${stats.enrolledCount}', 'ENROLLED'),
    ]);
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
                  style: AppTheme.accent(
                    size: 10,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
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
                style: AppTheme.accent(size: 12, weight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                record.status.toUpperCase(),
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
