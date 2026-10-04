// Backs the lecturer Timetable tab and the Home "TODAY" section.
//
// Kept separate from lecturerDashboardProvider, and reuses the student's
// WeekScheduleEntry model, because the two roles differ only in WHICH
// courses the schedule covers -- enrolled vs assigned. The wire format and
// the day-tile UI are identical, so the model is shared rather than
// duplicated (see get_lecturer_week_schedule in api/lecturer.py).
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';

class LecturerWeekScheduleState {
  final bool isLoading;
  final List<WeekScheduleEntry> entries;
  final String? errorMessage;

  LecturerWeekScheduleState({
    this.isLoading = false,
    this.entries = const [],
    this.errorMessage,
  });

  LecturerWeekScheduleState copyWith({
    bool? isLoading,
    List<WeekScheduleEntry>? entries,
    String? errorMessage,
  }) {
    return LecturerWeekScheduleState(
      isLoading: isLoading ?? this.isLoading,
      entries: entries ?? this.entries,
      errorMessage: errorMessage,
    );
  }

  /// Entries for one weekday. dayOfWeek is 0=Monday..6=Sunday throughout.
  List<WeekScheduleEntry> onDay(int dayOfWeek) =>
      entries.where((e) => e.dayOfWeek == dayOfWeek).toList();

  bool get isEmpty => entries.isEmpty;
}

final lecturerWeekScheduleProvider = NotifierProvider.autoDispose<
    LecturerWeekScheduleNotifier, LecturerWeekScheduleState>(
  LecturerWeekScheduleNotifier.new,
);

class LecturerWeekScheduleNotifier
    extends Notifier<LecturerWeekScheduleState> {
  @override
  LecturerWeekScheduleState build() {
    state = LecturerWeekScheduleState();
    Future.microtask(() => loadWeekSchedule());
    return state;
  }

  Future<void> loadWeekSchedule() async {
    // Only raise the loading flag when there is nothing on screen to keep,
    // same reasoning as todayScheduleProvider -- this is refetched on pull
    // and on tab re-entry, and blanking the tab each time reads as a glitch.
    final isBackgroundRefresh = state.entries.isNotEmpty;
    if (!isBackgroundRefresh) {
      state = state.copyWith(isLoading: true, errorMessage: null);
    }

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final entries = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchWeekSchedule(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, entries: entries);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
      );
    }
  }
}
