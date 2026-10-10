import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/features/student/providers/week_schedule_provider.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';

// Timetable tab root -- weekly view backed by weekScheduleProvider
// (dayOfWeek 0=Monday matches this list's index, per Timetable.day_of_week's
// documented convention in models.py).
class StudentTimetableScreen extends ConsumerWidget {
  const StudentTimetableScreen({super.key});

  static const _days = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(weekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    // Built once and shared by every state below, so the title is already
    // in place while the week loads instead of popping in with the data.
    final appBar = AppBar(
      title: const Text('Timetable'),
      backgroundColor: colorScheme.surface,
      elevation: 0,
    );

    if (state.isLoading && state.entries.isEmpty) {
      // Seven placeholder tiles, one per day -- the loaded screen always
      // shows all seven, so the skeleton is the exact shape of what's coming.
      return Scaffold(
        backgroundColor: colorScheme.surface,
        appBar: appBar,
        body: SingleChildScrollView(
          physics: const NeverScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: SkeletonPulse(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 13dp: the THIS WEEK eyebrow's line height, so the tiles
                // below start exactly where the real ones do.
                const SkeletonBox(width: 80, height: 13),
                const SizedBox(height: 16),
                for (var i = 0; i < _days.length; i++)
                  const SkeletonListCard(trailing: SkeletonTrailing.chevron),
              ],
            ),
          ),
        ),
      );
    }

    if (state.errorMessage != null && state.entries.isEmpty) {
      // Was a small red sentence under THIS WEEK with no way to retry
      // except discovering pull-to-refresh. A failed refresh no longer
      // reaches here -- loadWeekSchedule keeps the old week -- so this is
      // only a first load that never succeeded.
      return Scaffold(
        backgroundColor: colorScheme.surface,
        appBar: appBar,
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.calendar_month_rounded,
          title: "Couldn't load your timetable",
          message: isGenericServerMessage(state.errorMessage)
              ? 'Check your connection and try again.'
              : state.errorMessage,
          onRetry: () =>
              ref.read(weekScheduleProvider.notifier).loadWeekSchedule(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: appBar,
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(weekScheduleProvider.notifier).loadWeekSchedule(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'THIS WEEK',
                style: AppTheme.eyebrow(
                  colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              ),
              const SizedBox(height: 16),
              ..._days.asMap().entries.map((mapEntry) {
                final dayIndex = mapEntry.key;
                final dayName = mapEntry.value;
                final dayEntries = state.entries
                    .where((e) => e.dayOfWeek == dayIndex)
                    .toList();
                return _DayTile(
                  day: dayName,
                  entries: dayEntries,
                  colorScheme: colorScheme,
                );
              }),
            ],
          ),
        ),
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  final String day;
  final List<WeekScheduleEntry> entries;
  final ColorScheme colorScheme;

  const _DayTile({
    required this.day,
    required this.entries,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final hasClasses = entries.isNotEmpty;
    final subtitle = !hasClasses
        ? 'No classes'
        : entries.length == 1
        ? entries.first.courseCode
        : '${entries.length} classes';

    return InkWell(
      onTap: () => context.push('/student/timetable/day/$day'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: hasClasses
                ? colorScheme.primary.withValues(alpha: 0.25)
                : colorScheme.outline.withValues(alpha: 0.1),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  day.toUpperCase(),
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 13,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: AppTheme.accent(
                    size: 10,
                    color: hasClasses
                        ? colorScheme.primary
                        : colorScheme.onSurface.withValues(alpha: 0.4),
                  ),
                ),
              ],
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: colorScheme.onSurface.withValues(alpha: 0.3),
            ),
          ],
        ),
      ),
    );
  }
}
