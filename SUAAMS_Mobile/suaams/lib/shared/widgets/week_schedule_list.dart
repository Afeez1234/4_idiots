import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';

// The week on the student and lecturer Timetable tabs (shared 2026-11-01;
// each screen had its own copy of the same seven-tile list).
//
// It used to be seven equal cards, Monday first, each saying only "MCT 402"
// or "No classes". On a Sunday today was the last card, and finding out
// when or where a class was meant opening its day. Now the week starts at
// today, a day with classes lists each one with its time and room, and an
// empty day is one quiet line that goes nowhere.

/// Weekday names, index 0 = Monday (Timetable.day_of_week's convention).
/// Also the `:day` segment of the day-detail routes.
const weekdayNames = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

/// A day's classes in start-time order; entries with no time go last.
List<WeekScheduleEntry> classesOn(List<WeekScheduleEntry> entries, int day) {
  final list = entries.where((e) => e.dayOfWeek == day).toList();
  // "HH:MM" strings sort correctly as text.
  list.sort((a, b) => (a.startTime ?? '99').compareTo(b.startTime ?? '99'));
  return list;
}

/// The first class after today, looking up to six days ahead, or null when
/// the week has nothing outside today.
WeekScheduleEntry? nextClassAfterToday(
  List<WeekScheduleEntry> entries,
  DateTime now,
) {
  final today = now.weekday - 1;
  for (var i = 1; i < 7; i++) {
    final day = classesOn(entries, (today + i) % 7);
    if (day.isNotEmpty) return day.first;
  }
  return null;
}

/// "10:00–12:00", or "Time not set" when the timetable has none.
String timeRangeOf(WeekScheduleEntry e) =>
    (e.startTime != null && e.endTime != null)
    ? '${e.startTime}–${e.endTime}'
    : 'Time not set';

class WeekScheduleList extends StatelessWidget {
  final List<WeekScheduleEntry> entries;

  /// Day-detail route without the day, e.g. '/student/timetable/day'.
  final String dayRoute;

  /// Students see who teaches each class; a lecturer's own week doesn't
  /// need their name on every row.
  final bool showLecturer;

  /// Injectable for tests; defaults to now.
  final DateTime? now;

  const WeekScheduleList({
    super.key,
    required this.entries,
    required this.dayRoute,
    this.showLecturer = false,
    this.now,
  });

  @override
  Widget build(BuildContext context) {
    final today = (now ?? DateTime.now()).weekday - 1;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < 7; i++)
          _Day(
            label: switch (i) {
              0 => 'Today',
              1 => 'Tomorrow',
              _ => weekdayNames[(today + i) % 7],
            },
            day: (today + i) % 7,
            isToday: i == 0,
            classes: classesOn(entries, (today + i) % 7),
            dayRoute: dayRoute,
            showLecturer: showLecturer,
          ),
      ],
    );
  }
}

class _Day extends StatelessWidget {
  final String label;
  final int day;
  final bool isToday;
  final List<WeekScheduleEntry> classes;
  final String dayRoute;
  final bool showLecturer;

  const _Day({
    required this.label,
    required this.day,
    required this.isToday,
    required this.classes,
    required this.dayRoute,
    required this.showLecturer,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final muted = colorScheme.onSurface.withValues(alpha: 0.6);
    // "Today" and "Tomorrow" also name the weekday, so the list still
    // reads as a calendar.
    final weekday = weekdayNames[day];
    final heading = label == weekday ? label : '$label · $weekday';

    if (classes.isEmpty) {
      // One line, not a card: nothing to open, so nothing to tap.
      return Padding(
        padding: const EdgeInsets.fromLTRB(4, 10, 4, 14),
        child: Row(
          children: [
            Expanded(
              child: Text(
                heading,
                style: textTheme.titleSmall?.copyWith(
                  color: isToday ? colorScheme.onSurface : muted,
                ),
              ),
            ),
            Text(
              'No classes',
              style: textTheme.bodySmall?.copyWith(color: muted),
            ),
          ],
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Material(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(
            // Indigo marks "you are here" on today's card only.
            color: isToday
                ? colorScheme.primary.withValues(alpha: 0.5)
                : colorScheme.outline.withValues(alpha: 0.1),
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: () => context.push('$dayRoute/$weekday'),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        heading,
                        style: textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    Icon(
                      Icons.chevron_right_rounded,
                      color: colorScheme.onSurface.withValues(alpha: 0.3),
                    ),
                  ],
                ),
                for (final c in classes) ...[
                  const SizedBox(height: 12),
                  _ClassRow(entry: c, showLecturer: showLecturer),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ClassRow extends StatelessWidget {
  final WeekScheduleEntry entry;
  final bool showLecturer;

  const _ClassRow({required this.entry, required this.showLecturer});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final muted = colorScheme.onSurface.withValues(alpha: 0.6);
    final details = [
      if (entry.room != null && entry.room!.isNotEmpty) entry.room!,
      if (showLecturer && entry.lecturer != null) entry.lecturer!,
    ].join(' · ');

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Times and codes are machine data, so mono; the rest is sans.
        SizedBox(
          width: 96,
          child: Text(
            timeRangeOf(entry),
            style: AppTheme.accent(size: 12, color: colorScheme.onSurface),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                entry.courseCode,
                style: AppTheme.accent(
                  size: 12,
                  weight: FontWeight.w700,
                  color: colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                entry.courseName,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: textTheme.bodyMedium,
              ),
              if (details.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  details,
                  style: textTheme.bodySmall?.copyWith(color: muted),
                ),
              ],
            ],
          ),
        ),
      ],
    );
  }
}
