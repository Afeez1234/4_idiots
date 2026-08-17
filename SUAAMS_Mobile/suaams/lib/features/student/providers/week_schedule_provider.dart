// Backs both the Timetable tab's day list and Day Detail -- kept as its
// own provider (not folded into studentDashboardProvider) so both screens
// share one fetch, same reasoning as todayScheduleProvider.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/week_schedule_entry.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

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
    state = WeekScheduleState();
    Future.microtask(() => loadWeekSchedule());
    return state;
  }

  Future<void> loadWeekSchedule() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

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
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }
}
