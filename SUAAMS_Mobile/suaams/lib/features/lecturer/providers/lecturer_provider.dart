import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/lecturer_service.dart';
import '../models/lecturer_dashboard_model.dart';
import '../../../core/network/auth_retry.dart';

class LecturerDashboardState {
  final bool isLoading;
  final LecturerDashboardModel? data;
  final String? errorMessage;

  LecturerDashboardState({
    this.isLoading = false,
    this.data,
    this.errorMessage,
  });

  LecturerDashboardState copyWith({
    bool? isLoading,
    LecturerDashboardModel? data,
    String? errorMessage,
  }) {
    return LecturerDashboardState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final lecturerServiceProvider = Provider<LecturerService>((ref) => LecturerService());

final lecturerDashboardProvider =
    NotifierProvider.autoDispose<LecturerDashboardNotifier, LecturerDashboardState>(
      LecturerDashboardNotifier.new,
    );

class LecturerDashboardNotifier extends Notifier<LecturerDashboardState> {
  @override
  LecturerDashboardState build() {
    state = LecturerDashboardState();
    Future.microtask(() => loadDashboardData());
    return state;
  }

  Future<void> loadDashboardData() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final dashboardData = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchDashboardData(token),
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
