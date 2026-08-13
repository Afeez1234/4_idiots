import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/student_service.dart';
import '../models/student_dashboard_model.dart';
import '../../../core/network/auth_retry.dart';

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
    // We initialize the state here directly using the Notifier base class property
    state = StudentDashboardState();
    Future.microtask(() => loadDashboardData());
    return state;
  }

  Future<void> loadDashboardData() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

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

      state = state.copyWith(isLoading: false, data: dashboardData);
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }
}
