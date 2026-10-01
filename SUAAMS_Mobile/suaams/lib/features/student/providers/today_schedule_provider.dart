// Backs the "TODAY'S PROTOCOL" list on the dashboard home tab. Kept as its
// own provider (not folded into studentDashboardProvider) so it can be
// refreshed independently -- a course's status here changes live as a
// lecturer starts/ends a session and the student checks in, while
// dashboard stats are historical and barely change.
import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/models/today_protocol_entry.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';

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
  // Polls for a lecturer starting/ending a session.
  //
  // This data is genuinely live -- a session can open at any moment without
  // the student touching anything -- and the dashboard's check-in card
  // depends on it. Without a poll, a student who leaves the app open across
  // a session start sees a stale card and can't check in until they
  // manually pull to refresh or navigate.
  //
  // 30s is a deliberate tradeoff. Short enough that a student who watches
  // the card flip to live finds it within half a minute; long enough that a
  // phone left on the dashboard all day costs a few hundred small GETs
  // rather than tens of thousands. The request is tiny (one query joined
  // against the student's own timetable rows).
  static const Duration _pollInterval = Duration(seconds: 30);

  // Kept as a field rather than a local in build() so refreshTodaySchedule()
  // below can cancel it on teardown, and so it survives the rebuilds that
  // Riverpod triggers while the provider stays alive.
  Timer? _pollTimer;

  @override
  TodayScheduleState build() {
    state = TodayScheduleState();
    Future.microtask(() {
      loadTodaySchedule();
      _startPolling();
    });
    // autoDispose tears the notifier down when the last listener (the
    // dashboard) unsubscribes. Cancelling here stops the timer from firing
    // against a disposed ref -- a Timer holding a live closure over a
    // disposed Notifier is exactly the leak Riverpod's cleanup hook
    // exists to prevent.
    ref.onDispose(_stopPolling);
    return state;
  }

  void _startPolling() {
    _pollTimer?.cancel();
    _pollTimer = Timer.periodic(_pollInterval, (_) {
      // Skip a poll that's already in flight rather than stacking them --
      // on a slow connection a 30s timer would otherwise outrun the request
      // and let concurrent writes race on `state`.
      if (state.isLoading) return;
      loadTodaySchedule();
    });
  }

  void _stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }

  /// Called when the app returns to the foreground. Polling is suspended
  /// by the OS in the background, so the first frame back can be arbitrarily
  /// stale -- this forces one immediate fetch instead of making the student
  /// wait out the remainder of the 30s window.
  ///
  /// Called from the dashboard's lifecycle observer, not from here, since
  /// only the widget knows about the app's foreground state.
  void refreshTodaySchedule() {
    _stopPolling();
    loadTodaySchedule();
    _startPolling();
  }

  Future<void> loadTodaySchedule() async {
    // Only raise the loading flag when there's nothing on screen to keep
    // showing. This method is now called by a 30s poll as well as by the
    // initial load and pull-to-refresh, and unconditionally setting
    // isLoading would blank the dashboard's protocol list and flip the
    // check-in card's subtitle back to "LOADING..." every half minute --
    // a visible flicker every poll, which is worse than slightly stale data.
    // Errors behave the same way: a failed background poll leaves the last
    // good data in place rather than replacing the tab with an error.
    final isBackgroundRefresh = state.entries.isNotEmpty;
    if (!isBackgroundRefresh) {
      state = state.copyWith(isLoading: true, errorMessage: null);
    }

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
        // Surface a background-poll failure only if we have nothing to
        // fall back on; otherwise the student keeps seeing real data and
        // the next tick can still succeed.
        //
        // Note copyWith always assigns errorMessage (it takes `String?`
        // without a `?? this.errorMessage` fallback), so passing a value
        // here preserves an existing error and the success path above
        // passing nothing clears it. `entries` is deliberately omitted --
        // copyWith keeps the existing list when it's not supplied.
        errorMessage: isBackgroundRefresh
            ? state.errorMessage
            : e.toString().replaceAll('Exception: ', ''),
      );
    }
  }
}
