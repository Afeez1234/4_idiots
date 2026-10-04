import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/lecturer/providers/lecturer_week_schedule_provider.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';

// Timetable tab root for the lecturer -- their own teaching week.
//
// This REPLACED the Sessions tab. That tab listed only currently-running
// sessions, so it was empty for the rest of the day, and the Home tab
// already carried a LIVE NOW stat tile plus a per-course workspace with the
// check-in list. What it could not answer was "what am I teaching, and
// when" -- which is the question a timetable exists to answer. Monitoring a
// live session remains reachable from Home and the course card.
//
// Structurally a mirror of StudentTimetableScreen; they differ only in
// which provider supplies the week.
class LecturerTimetableScreen extends ConsumerWidget {
  const LecturerTimetableScreen({super.key});

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
    final state = ref.watch(lecturerWeekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.entries.isEmpty) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Timetable'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () => ref
            .read(lecturerWeekScheduleProvider.notifier)
            .loadWeekSchedule(),
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
              if (state.errorMessage != null)
                AppStateView(
                  kind: AppStateKind.error,
                  icon: Icons.calendar_month_rounded,
                  title: "Couldn't load your timetable",
                  message: state.errorMessage,
                  onRetry: () => ref
                      .read(lecturerWeekScheduleProvider.notifier)
                      .loadWeekSchedule(),
                )
              else if (state.isEmpty)
                const AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.event_busy_rounded,
                  title: 'No classes scheduled',
                  message:
                      'Nothing appears here until a course you teach is '
                      'added to the timetable.',
                )
              else
                ..._days.asMap().entries.map((mapEntry) {
                  final dayIndex = mapEntry.key;
                  final dayName = mapEntry.value;
                  return _DayTile(
                    day: dayName,
                    entries: state.onDay(dayIndex),
                    isToday: DateTime.now().weekday - 1 == dayIndex,
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
  final bool isToday;
  final ColorScheme colorScheme;

  const _DayTile({
    required this.day,
    required this.entries,
    required this.isToday,
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
      onTap: () => context.push('/lecturer/timetable/day/$day'),
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
                Row(
                  children: [
                    Text(
                      day.toUpperCase(),
                      style: const TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                      ),
                    ),
                    // "Today" is marked rather than implied by ordering --
                    // a lecturer opening the tab on a Thursday otherwise
                    // has to count tiles to work out which one is now.
                    if (isToday) ...[
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 6,
                          vertical: 1,
                        ),
                        decoration: BoxDecoration(
                          color: colorScheme.primary.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(6),
                        ),
                        child: Text(
                          'TODAY',
                          style: TextStyle(
                            fontSize: 9,
                            fontWeight: FontWeight.w700,
                            letterSpacing: 0.8,
                            color: colorScheme.primary,
                          ),
                        ),
                      ),
                    ],
                  ],
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
