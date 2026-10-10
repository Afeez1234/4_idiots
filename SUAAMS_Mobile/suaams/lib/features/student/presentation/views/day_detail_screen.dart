import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/features/student/providers/week_schedule_provider.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/core/theme/app_terminal.dart';

const _dayNameToIndex = {
  'Monday': 0,
  'Tuesday': 1,
  'Wednesday': 2,
  'Thursday': 3,
  'Friday': 4,
  'Saturday': 5,
  'Sunday': 6,
};

// Reuses the already-loaded weekScheduleProvider -- filters by day rather
// than fetching separately, same reasoning as CourseDetailScreen reusing
// studentDashboardProvider.
class DayDetailScreen extends ConsumerWidget {
  final String day;

  const DayDetailScreen({super.key, required this.day});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(weekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    // Shared by the loading and error states so the day's name is on screen
    // from the first frame, matching the loaded screen's app bar.
    final appBar = AppBar(
      title: Text(day),
      backgroundColor: colorScheme.surface,
      elevation: 0,
    );

    if (state.isLoading && state.entries.isEmpty) {
      // Usually never seen: this screen is pushed from the Timetable tab,
      // which already loaded the week. It appears on a deep link or after
      // the provider was disposed. Two cards is a typical day.
      return Scaffold(
        backgroundColor: colorScheme.surface,
        appBar: appBar,
        body: const Padding(
          padding: EdgeInsets.all(24),
          child: SkeletonList(count: 2, trailing: SkeletonTrailing.text),
        ),
      );
    }

    if (state.errorMessage != null && state.entries.isEmpty) {
      // Was the raw error string centred on a blank screen, with no retry.
      return Scaffold(
        backgroundColor: colorScheme.surface,
        appBar: appBar,
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.calendar_month_rounded,
          title: "Couldn't load $day's classes",
          message: isGenericServerMessage(state.errorMessage)
              ? 'Check your connection and try again.'
              : state.errorMessage,
          onRetry: () =>
              ref.read(weekScheduleProvider.notifier).loadWeekSchedule(),
        ),
      );
    }

    final dayIndex = _dayNameToIndex[day];
    final dayEntries =
        state.entries.where((e) => e.dayOfWeek == dayIndex).toList()
          ..sort((a, b) => (a.startTime ?? '').compareTo(b.startTime ?? ''));

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: appBar,
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (dayEntries.isEmpty)
              const AppStateView(
                kind: AppStateKind.empty,
                icon: Icons.beach_access_rounded,
                title: 'Nothing scheduled',
                message: 'No protocols are assigned to this day.',
                compact: true,
              )
            else
              ...dayEntries.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _ClassCard(entry: entry, colorScheme: colorScheme),
                ),
              ),
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
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border(left: BorderSide(color: terminal.accent, width: 4)),
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
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  entry.room != null
                      ? '${entry.courseCode} · ${entry.room}'
                      : entry.courseCode,
                  style: AppTheme.accent(
                    size: 10,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
          Text(
            '${entry.startTime ?? '--:--'} – ${entry.endTime ?? '--:--'}',
            style: AppTheme.accent(size: 12, weight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}
