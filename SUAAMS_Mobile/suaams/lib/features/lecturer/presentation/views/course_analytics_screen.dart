import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/lecturer/providers/course_analytics_provider.dart';
import 'package:suaams/features/lecturer/models/course_analytics_model.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/utils/attendance_status.dart';

class CourseAnalyticsScreen extends ConsumerWidget {
  final int courseId;

  const CourseAnalyticsScreen({super.key, required this.courseId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(courseAnalyticsProvider(courseId));
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Course Analytics')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title: 'Couldn''t load analytics',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () =>
              ref.read(courseAnalyticsProvider(courseId).notifier).loadAnalytics(),
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
            .read(courseAnalyticsProvider(courseId).notifier)
            .loadAnalytics(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                data.course.code,
                style: AppTheme.accent(size: 11, letterSpacing: 1, color: colorScheme.onSurface.withValues(alpha: 0.5)),
              ),
              const SizedBox(height: 24),

              _SummaryGrid(summary: data.summary),
              const SizedBox(height: 32),

              Text(
                'ATTENDANCE TREND',
                style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),
              if (data.trend.isEmpty)
                AppStateView(
                    kind: AppStateKind.empty,
                    icon: Icons.insights_rounded,
                    title: 'No trend data yet',
                    message: 'Trend appears after a session has been completed.',
                    compact: true,
                  )
              else
                ...data.trend.map(
                  (point) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _TrendRow(point: point, colorScheme: colorScheme),
                  ),
                ),
              const SizedBox(height: 32),

              Text(
                'STUDENT BREAKDOWN',
                style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),
              if (data.students.isEmpty)
                AppStateView(
                    kind: AppStateKind.empty,
                    icon: Icons.groups_rounded,
                    title: 'No students enrolled',
                    message: 'Students appear here once they register for the course.',
                    compact: true,
                  )
              else
                ...data.students.map(
                  (student) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _StudentRow(
                      student: student,
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

class _SummaryGrid extends StatelessWidget {
  final AnalyticsSummary summary;

  const _SummaryGrid({required this.summary});

  @override
  Widget build(BuildContext context) {
    final isLow = summary.avgAttendance < 75;
    return AppStatRow([
      AppStatValue('${summary.enrolledCount}', 'ENROLLED'),
      AppStatValue('${summary.totalSessions}', 'SESSIONS'),
      // Sub-75% average is the warning state; at or above it reads as good.
      // The old copy could only express this as `highlight` plus `warning`
      // booleans that both fed one accent colour.
      isLow
          ? AppStatValue.warning('${summary.avgAttendance}%', 'AVG ATTENDANCE')
          : AppStatValue.success('${summary.avgAttendance}%', 'AVG ATTENDANCE'),
    ]);
  }
}

class _TrendRow extends StatelessWidget {
  final AttendanceTrendPoint point;
  final ColorScheme colorScheme;

  const _TrendRow({required this.point, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final barColor = point.pct < 75
        ? colorScheme.error
        : AppStatus.success;

    return Row(
      children: [
        SizedBox(
          width: 84,
          child: Text(
            point.date ?? '--',
            style: AppTheme.accent(size: 10, color: colorScheme.onSurface.withValues(alpha: 0.6)),
          ),
        ),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: (point.pct / 100).clamp(0, 1),
              minHeight: 10,
              backgroundColor: colorScheme.surfaceContainer,
              valueColor: AlwaysStoppedAnimation(barColor),
            ),
          ),
        ),
        SizedBox(
          width: 60,
          child: Text(
            '${point.pct}% · ${point.presentCount}/${point.enrolledCount}',
            textAlign: TextAlign.right,
            style: AppTheme.accent(size: 9, weight: FontWeight.w700, color: barColor),
          ),
        ),
      ],
    );
  }
}

class _StudentRow extends StatelessWidget {
  final StudentAttendanceStat student;
  final ColorScheme colorScheme;

  const _StudentRow({required this.student, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final isAtRisk = student.pct < 75;
    final accentColor = isAtRisk ? colorScheme.error : AppStatus.success;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: accentColor, width: 4)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  student.fullName,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  student.matricNumber,
                  style: AppTheme.accent(size: 10, color: colorScheme.onSurface.withValues(alpha: 0.5)),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                '${student.pct}%',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 15,
                  color: accentColor,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                '${student.attended}/${student.total}',
                style: AppTheme.accent(size: 9, color: colorScheme.onSurface.withValues(alpha: 0.5)),
              ),
            ],
          ),
        ],
      ),
    );
  }
}