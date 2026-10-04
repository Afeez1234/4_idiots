import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/lecturer/providers/lecturer_week_schedule_provider.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/shared/utils/date_label.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';

/// What the lecturer is doing right now.
///
/// The mirror of the student's live session card, and the reason the
/// Timetable tab earns its place. Sits directly under the stats because
/// "am I on now / what is next" is asked far more often than anything
/// further down the Home page.
class LecturerTodaySection extends ConsumerWidget {
  const LecturerTodaySection({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerWeekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;
    final terminal = terminalOf(context);

    // DateTime.weekday is 1=Monday; Timetable.day_of_week is 0=Monday.
    // This subtraction is the same conversion the student timetable uses.
    final today = DateTime.now().weekday - 1;
    final entries = state.onDay(today);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'TODAY',
          style: AppTheme.eyebrow(
            colorScheme.onSurface.withValues(alpha: 0.6),
          ),
        ),
        const SizedBox(height: 2),
        // The one place a lecturer can tell a stale screen from a live one.
        Text(
          formatDateLabel(DateTime.now()),
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: colorScheme.onSurface.withValues(alpha: 0.45),
          ),
        ),
        const SizedBox(height: 16),
        if (state.isLoading && entries.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Center(
              child: SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
            ),
          )
        else if (entries.isEmpty)
          // No retry here. An empty day is a real answer, and a button
          // promising to reload something that was never going to appear is
          // worse than saying so plainly. It only reads as a failure when
          // the fetch actually did fail.
          AppStateView(
            kind: state.errorMessage != null
                ? AppStateKind.error
                : AppStateKind.empty,
            icon: state.errorMessage != null
                ? Icons.cloud_off_rounded
                : Icons.beach_access_rounded,
            title: state.errorMessage != null
                ? "Couldn't load your timetable"
                : 'Nothing scheduled today',
            message: state.errorMessage ??
                'No classes are assigned to you for today.',
            compact: true,
          )
        else
          for (final entry in entries) ...[
            _TodayCard(entry: entry, terminal: terminal),
            const SizedBox(height: 10),
          ],
      ],
    );
  }
}

/// Where a class sits relative to the clock.
///
/// The distinction a lecturer actually cares about is whether they should
/// already be walking to the room, which "3 classes today" cannot express.
/// IN PROGRESS is deliberately green -- same token the student's PRESENT
/// uses, because it means the same thing.
({String label, bool live}) _timingFor(WeekScheduleEntry entry) {
  final start = entry.startTime;
  final end = entry.endTime;
  if (start == null || end == null) return (label: 'SCHEDULED', live: false);

  int? minutesOf(String hhmm) {
    final parts = hhmm.split(':');
    if (parts.length < 2) return null;
    final h = int.tryParse(parts[0]);
    final m = int.tryParse(parts[1]);
    if (h == null || m == null) return null;
    return h * 60 + m;
  }

  final s = minutesOf(start);
  final e = minutesOf(end);
  if (s == null || e == null) return (label: 'SCHEDULED', live: false);

  final now = DateTime.now();
  final nowMinutes = now.hour * 60 + now.minute;

  if (nowMinutes >= s && nowMinutes <= e) {
    return (label: 'IN PROGRESS', live: true);
  }
  if (nowMinutes < s) {
    final mins = s - nowMinutes;
    // Inside the hour is the window where "STARTS IN 40 MIN" actually
    // changes what someone does. Beyond that it is just "upcoming".
    if (mins <= 60) return (label: 'STARTS IN $mins MIN', live: false);
    return (label: 'UPCOMING', live: false);
  }
  return (label: 'ENDED', live: false);
}

class _TodayCard extends StatelessWidget {
  final WeekScheduleEntry entry;
  final AppTerminal terminal;

  const _TodayCard({required this.entry, required this.terminal});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final timing = _timingFor(entry);
    final accent = timing.live ? terminal.successText : colorScheme.primary;
    final timeRange = (entry.startTime != null && entry.endTime != null)
        ? '${entry.startTime} - ${entry.endTime}'
        : '--:-- - --:--';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(
            color: timing.live ? terminal.successText : colorScheme.outline,
            width: 4,
          ),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        entry.courseCode,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          fontSize: 14,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 6,
                        vertical: 1,
                      ),
                      decoration: BoxDecoration(
                        color: accent.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        timing.label,
                        style: TextStyle(
                          fontSize: 9,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.8,
                          color: accent,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  timeRange,
                  style: AppTheme.accent(
                    size: 12,
                    color: colorScheme.onSurface.withValues(alpha: 0.65),
                  ),
                ),
                if (entry.room != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    entry.room!,
                    style: TextStyle(
                      fontSize: 11,
                      color: colorScheme.onSurface.withValues(alpha: 0.45),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
