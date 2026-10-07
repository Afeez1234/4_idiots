import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/lecturer/providers/lecturer_week_schedule_provider.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';

const _dayNameToIndex = {
  'Monday': 0,
  'Tuesday': 1,
  'Wednesday': 2,
  'Thursday': 3,
  'Friday': 4,
  'Saturday': 5,
  'Sunday': 6,
};

// One day's classes for a lecturer. Reuses the already-loaded
// lecturerWeekScheduleProvider and filters by day rather than issuing a
// second request -- same reasoning as the student's DayDetailScreen.
class LecturerDayDetailScreen extends ConsumerWidget {
  final String day;

  const LecturerDayDetailScreen({super.key, required this.day});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerWeekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.entries.isEmpty) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final dayIndex = _dayNameToIndex[day];
    if (dayIndex == null) {
      return Scaffold(
        appBar: AppBar(title: Text(day)),
        body: const AppStateView(
          kind: AppStateKind.empty,
          icon: Icons.help_outline_rounded,
          title: 'Unknown day',
        ),
      );
    }

    final entries = state.onDay(dayIndex)
      ..sort((a, b) => (a.startTime ?? '').compareTo(b.startTime ?? ''));

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(day),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: entries.isEmpty
            ? AppStateView(
                kind: state.errorMessage != null
                    ? AppStateKind.error
                    : AppStateKind.empty,
                icon: state.errorMessage != null
                    ? Icons.cloud_off_rounded
                    : Icons.beach_access_rounded,
                title: state.errorMessage != null
                    ? "Couldn't load your timetable"
                    : 'Nothing scheduled',
                message: state.errorMessage,
                onRetry: state.errorMessage != null
                    ? () => ref
                        .read(lecturerWeekScheduleProvider.notifier)
                        .loadWeekSchedule()
                    : null,
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final entry in entries) ...[
                    _ClassCard(entry: entry, colorScheme: colorScheme),
                    const SizedBox(height: 12),
                  ],
                ],
              ),
      ),
    );
  }
}

class _ClassCard extends StatelessWidget {
  final WeekScheduleEntry entry;
  final ColorScheme colorScheme;

  const _ClassCard({required this.entry, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final terminal = terminalOf(context);
    final timeRange = (entry.startTime != null && entry.endTime != null)
        ? '${entry.startTime} - ${entry.endTime}'
        : '--:-- - --:--';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(color: terminal.accent, width: 4),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.courseName,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  entry.courseCode,
                  style: AppTheme.accent(size: 11, color: terminal.textMuted),
                ),
                if (entry.room != null) ...[
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Icon(
                        Icons.place_rounded,
                        size: 12,
                        color: colorScheme.onSurface.withValues(alpha: 0.4),
                      ),
                      const SizedBox(width: 4),
                      Text(
                        entry.room!,
                        style: TextStyle(
                          fontSize: 11,
                          color: colorScheme.onSurface.withValues(alpha: 0.55),
                        ),
                      ),
                    ],
                  ),
                ],
              ],
            ),
          ),
          Text(
            timeRange,
            style: AppTheme.accent(
              size: 12,
              weight: FontWeight.w700,
              color: colorScheme.onSurface.withValues(alpha: 0.75),
            ),
          ),
        ],
      ),
    );
  }
}
