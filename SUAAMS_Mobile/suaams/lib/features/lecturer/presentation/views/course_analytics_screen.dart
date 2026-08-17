import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/course_analytics_provider.dart';
import '../../models/course_analytics_model.dart';

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
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono',
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),

              _SummaryGrid(summary: data.summary, colorScheme: colorScheme),
              const SizedBox(height: 32),

              const Text(
                'ATTENDANCE TREND',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.5,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              if (data.trend.isEmpty)
                const Text(
                  'No completed sessions yet.',
                  style: TextStyle(color: Colors.grey),
                )
              else
                ...data.trend.map(
                  (point) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _TrendRow(point: point, colorScheme: colorScheme),
                  ),
                ),
              const SizedBox(height: 32),

              const Text(
                'STUDENT BREAKDOWN',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 1.5,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              if (data.students.isEmpty)
                const Text(
                  'No students enrolled yet.',
                  style: TextStyle(color: Colors.grey),
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
  final ColorScheme colorScheme;

  const _SummaryGrid({required this.summary, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final isLow = summary.avgAttendance < 75;
    return Row(
      children: [
        _StatBox(
          val: '${summary.enrolledCount}',
          label: 'ENROLLED',
          colorScheme: colorScheme,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${summary.totalSessions}',
          label: 'SESSIONS',
          colorScheme: colorScheme,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${summary.avgAttendance}%',
          label: 'AVG ATTENDANCE',
          colorScheme: colorScheme,
          highlight: !isLow,
          warning: isLow,
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
  final bool warning;

  const _StatBox({
    required this.val,
    required this.label,
    required this.colorScheme,
    this.highlight = false,
    this.warning = false,
  });

  @override
  Widget build(BuildContext context) {
    final accentColor = warning ? colorScheme.error : const Color(0xFF10B981);
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: (highlight || warning)
              ? accentColor.withValues(alpha: 0.12)
              : colorScheme.surfaceContainer.withValues(alpha: 0.78),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: (highlight || warning)
                ? accentColor.withValues(alpha: 0.35)
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
                color: (highlight || warning)
                    ? accentColor
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
                color: (highlight || warning)
                    ? accentColor.withValues(alpha: 0.9)
                    : colorScheme.onSurface.withValues(alpha: 0.55),
              ),
            ),
          ],
        ),
      ),
    );
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
        : const Color(0xFF10B981);

    return Row(
      children: [
        SizedBox(
          width: 84,
          child: Text(
            point.date ?? '--',
            style: TextStyle(
              fontSize: 10,
              fontFamily: 'JetBrains Mono',
              color: colorScheme.onSurface.withValues(alpha: 0.6),
            ),
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
            style: TextStyle(
              fontSize: 9,
              fontWeight: FontWeight.bold,
              fontFamily: 'JetBrains Mono',
              color: barColor,
            ),
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
    final accentColor = isAtRisk ? colorScheme.error : const Color(0xFF10B981);

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
                  style: TextStyle(
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono',
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
                style: TextStyle(
                  fontSize: 9,
                  fontFamily: 'JetBrains Mono',
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
