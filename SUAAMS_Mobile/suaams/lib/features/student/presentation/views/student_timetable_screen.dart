import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/week_schedule_provider.dart';
import '../../models/week_schedule_entry.dart';

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
        onRefresh: () =>
            ref.read(weekScheduleProvider.notifier).loadWeekSchedule(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'THIS WEEK',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 2,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              if (state.errorMessage != null)
                Text(
                  'Could not load timetable.',
                  style: TextStyle(color: colorScheme.error, fontSize: 12),
                )
              else
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
                  style: TextStyle(
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono',
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
