// Backs the "TODAY'S PROTOCOL" list on the dashboard home tab. Kept as its
// own provider (not folded into studentDashboardProvider) so it can be
// refreshed independently -- a course's status here changes live as a
// lecturer starts/ends a session and the student checks in, while
// dashboard stats are historical and barely change.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/today_protocol_entry.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

class TodayScheduleState {
  final bool isLoading;
  final List<TodayProtocolEntry> entries;
  final String? errorMessage;

  TodayScheduleState({
    this.isLoading = false,
    this.entries = const [],
    this.errorMessage,
  });

  TodayScheduleState copyWith({
    bool? isLoading,
    List<TodayProtocolEntry>? entries,
    String? errorMessage,
  }) {
    return TodayScheduleState(
      isLoading: isLoading ?? this.isLoading,
      entries: entries ?? this.entries,
      errorMessage: errorMessage,
    );
  }
}

final todayScheduleProvider =
    NotifierProvider.autoDispose<TodayScheduleNotifier, TodayScheduleState>(
      TodayScheduleNotifier.new,
    );

class TodayScheduleNotifier extends Notifier<TodayScheduleState> {
  @override
  TodayScheduleState build() {
    state = TodayScheduleState();
    Future.microtask(() => loadTodaySchedule());
    return state;
  }

  Future<void> loadTodaySchedule() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      // Reuses studentServiceProvider (already declared in
      // student_provider.dart for the dashboard fetch) rather than
      // creating a second StudentService instance/provider.
      final studentService = ref.read(studentServiceProvider);
      // FIX: this provider previously had NO expiry handling at all (unlike
      // student_provider.dart, which at least force-logged-out on a raw
      // "expired"/"unauthorized" string match) -- an expired token here
      // just surfaced a raw error and left stale data on screen. Routing
      // through withAuthRetry brings it in line with every other
      // authenticated call: silent refresh-and-retry on a 401, logout only
      // if that also fails.
      final entries = await withAuthRetry(
        ref,
        (token) => studentService.fetchTodaySchedule(token),
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
