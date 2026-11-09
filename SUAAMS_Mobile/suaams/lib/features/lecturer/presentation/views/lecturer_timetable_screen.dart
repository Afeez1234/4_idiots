import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:suaams/features/lecturer/providers/lecturer_week_schedule_provider.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';
import 'package:suaams/shared/widgets/week_schedule_list.dart';

// Timetable tab root for the lecturer -- their own teaching week.
//
// This REPLACED the Sessions tab. That tab listed only currently-running
// sessions, so it was empty for the rest of the day, and the Home tab
// already carried a LIVE NOW stat tile plus a per-course workspace with the
// check-in list. What it could not answer was "what am I teaching, and
// when" -- which is the question a timetable exists to answer. Monitoring a
// live session remains reachable from Home and the course card.
//
// Structurally a mirror of StudentTimetableScreen; both render the week
// with the shared WeekScheduleList (2026-11-01), so they can't drift.
class LecturerTimetableScreen extends ConsumerWidget {
  const LecturerTimetableScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerWeekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.entries.isEmpty) {
      return const AppLoadingView(title: 'Timetable', rows: 3);
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
            ref.read(lecturerWeekScheduleProvider.notifier).loadWeekSchedule(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          // The "THIS WEEK" eyebrow above the list went with the redesign:
          // the app bar already says Timetable, and the list now starts
          // at Today, which says which week it is.
          child: state.errorMessage != null
              ? AppStateView(
                  kind: AppStateKind.error,
                  icon: Icons.calendar_month_rounded,
                  title: "Couldn't load your timetable",
                  message: state.errorMessage,
                  onRetry: () => ref
                      .read(lecturerWeekScheduleProvider.notifier)
                      .loadWeekSchedule(),
                )
              : state.isEmpty
              ? const AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.event_busy_rounded,
                  title: 'No classes scheduled',
                  message:
                      'Nothing appears here until a course you teach is '
                      'added to the timetable.',
                )
              : WeekScheduleList(
                  entries: state.entries,
                  dayRoute: '/lecturer/timetable/day',
                ),
        ),
      ),
    );
  }
}
