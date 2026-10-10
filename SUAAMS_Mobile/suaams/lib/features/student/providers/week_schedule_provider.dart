// Backs both the Timetable tab's day list and Day Detail -- kept as its
// own provider (not folded into studentDashboardProvider) so both screens
// share one fetch, same reasoning as todayScheduleProvider.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/models/week_schedule_entry.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';

class WeekScheduleState {
  final bool isLoading;
  final List<WeekScheduleEntry> entries;
  final String? errorMessage;

  WeekScheduleState({
    this.isLoading = false,
    this.entries = const [],
    this.errorMessage,
  });

  WeekScheduleState copyWith({
    bool? isLoading,
    List<WeekScheduleEntry>? entries,
    String? errorMessage,
  }) {
    return WeekScheduleState(
      isLoading: isLoading ?? this.isLoading,
      entries: entries ?? this.entries,
      errorMessage: errorMessage,
    );
  }
}

final weekScheduleProvider =
    NotifierProvider.autoDispose<WeekScheduleNotifier, WeekScheduleState>(
      WeekScheduleNotifier.new,
    );

class WeekScheduleNotifier extends Notifier<WeekScheduleState> {
  @override
  WeekScheduleState build() {
    // Starts in the loading state: build() always kicks off a fetch, and
    // starting at isLoading=false gave watchers one frame of "not loading,
    // no data, no error" -- which screens rendered as the error or empty
    // view before the skeleton appeared.
    state = WeekScheduleState(isLoading: true);
    Future.microtask(() => loadWeekSchedule());
    return state;
  }

  Future<void> loadWeekSchedule() async {
    // Same rule as loadDashboardData / loadTodaySchedule: only show the
    // loading state when there's nothing on screen. A pull-to-refresh used
    // to set errorMessage on failure, and the timetable renders the error
    // INSTEAD of the week -- so one dropped request on a weak signal wiped
    // a perfectly good timetable off the screen.
    final isBackgroundRefresh = state.entries.isNotEmpty;
    if (!isBackgroundRefresh) {
      state = state.copyWith(isLoading: true, errorMessage: null);
    }

    try {
      final studentService = ref.read(studentServiceProvider);
      final entries = await withAuthRetry(
        ref,
        (token) => studentService.fetchWeekSchedule(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, entries: entries);
      }
    } catch (e) {
      if (!ref.mounted) return;
      // Keep the week on screen if a refresh fails; see the top of this
      // method. Only a failed first load shows the error view.
      if (isBackgroundRefresh) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
      );
    }
  }
}
