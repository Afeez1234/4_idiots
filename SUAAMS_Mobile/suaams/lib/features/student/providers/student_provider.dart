import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/data/student_service.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';

class StudentDashboardState {
  final bool isLoading;
  final StudentDashboardModel? data;
  final String? errorMessage;

  StudentDashboardState({this.isLoading = false, this.data, this.errorMessage});

  StudentDashboardState copyWith({
    bool? isLoading,
    StudentDashboardModel? data,
    String? errorMessage,
  }) {
    return StudentDashboardState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

// Service provider
final studentServiceProvider = Provider<StudentService>(
  (ref) => StudentService(),
);

// Updated to 3.3+ compliant syntax
final studentDashboardProvider =
    NotifierProvider.autoDispose<
      StudentDashboardNotifier,
      StudentDashboardState
    >(StudentDashboardNotifier.new);

class StudentDashboardNotifier extends Notifier<StudentDashboardState> {
  @override
  StudentDashboardState build() {
    // Starts in the loading state: build() always kicks off a fetch, and
    // starting at isLoading=false gave watchers one frame of "not loading,
    // no data, no error" -- which screens rendered as the error or empty
    // view before the skeleton appeared.
    state = StudentDashboardState(isLoading: true);
    Future.microtask(() => loadDashboardData());
    return state;
  }

  Future<void> loadDashboardData() async {
    // Same rule as loadTodaySchedule: only raise isLoading when there's
    // nothing on screen yet. A refresh after a check-in or a course
    // registration used to blank every tab watching this provider back to
    // its loading state for a round-trip, even though the old data was
    // still perfectly good to show until the new data arrived.
    final isBackgroundRefresh = state.data != null;
    if (!isBackgroundRefresh) {
      state = state.copyWith(isLoading: true, errorMessage: null);
    }

    try {
      final studentService = ref.read(studentServiceProvider);
      // withAuthRetry replaces the old manual token-read + expired/
      // unauthorized string-match + logout() dance -- it now silently
      // attempts a token refresh on a 401 and retries once before giving up
      // (see lib/core/network/auth_retry.dart), instead of immediately
      // forcing a logout the moment the access token expires.
      final dashboardData = await withAuthRetry(
        ref,
        (token) => studentService.fetchDashboardData(token),
      );

      // autoDispose: every tab watching this may have gone away while the
      // request was in flight, and writing state to a disposed notifier
      // throws.
      if (!ref.mounted) return;
      // copyWith always takes errorMessage as given, so this also clears
      // any error left from an earlier failed first load.
      state = state.copyWith(isLoading: false, data: dashboardData);
    } catch (e) {
      if (!ref.mounted) return;
      // A failed background refresh keeps the last good data rather than
      // swapping the screen for an error -- slightly stale numbers beat a
      // dead end. The next refresh will try again.
      if (isBackgroundRefresh) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
      );
    }
  }
}
