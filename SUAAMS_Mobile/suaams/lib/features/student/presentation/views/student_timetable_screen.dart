import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/shared/widgets/week_schedule_list.dart';
import 'package:suaams/features/student/providers/week_schedule_provider.dart';

// Timetable tab root -- weekly view backed by weekScheduleProvider
// (dayOfWeek 0=Monday, per Timetable.day_of_week's documented convention in
// models.py). The week itself is the shared WeekScheduleList (2026-11-01),
// the same one the lecturer tab uses, with who teaches each class added.
class StudentTimetableScreen extends ConsumerWidget {
  const StudentTimetableScreen({super.key});

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
      return const AppLoadingView(title: 'Timetable', rows: 3);
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
          child: WeekScheduleList(
            entries: state.entries,
            dayRoute: '/student/timetable/day',
            showLecturer: true,
          ),
        ),
      ),
    );
  }
}
