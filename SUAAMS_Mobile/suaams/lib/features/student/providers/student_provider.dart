import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/student_service.dart';
import '../models/student_dashboard_model.dart';
import '../../auth/providers/auth_provider.dart';

class StudentDashboardState {
  final bool isLoading;
  final StudentDashboardModel? data;
  final String? errorMessage;

  StudentDashboardState({
    this.isLoading = false,
    this.data,
    this.errorMessage,
  });

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
final studentServiceProvider = Provider<StudentService>((ref) => StudentService());

// Updated to 3.3+ compliant syntax
final studentDashboardProvider = NotifierProvider.autoDispose<StudentDashboardNotifier, StudentDashboardState>(
  StudentDashboardNotifier.new,
);

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
      final user = ref.read(authProvider).user;
      final token = user?.token;

      if (token == null) {
        throw Exception('Authentication token missing');
      }

      final studentService = ref.read(studentServiceProvider);
      final dashboardData = await studentService.fetchDashboardData(token);
      
      state = state.copyWith(isLoading: false, data: dashboardData);
    } catch (e) {
      final errorMsg = e.toString().replaceAll('Exception: ', '');

      // LINE BELOW: We check the string for "expired" or "unauthorized" from the Flask-JWT-Extended error response.
      if (errorMsg.toLowerCase().contains('expired') || errorMsg.toLowerCase().contains('unauthorized')) {
        ref.read(authProvider.notifier).logout();
      }

      state = state.copyWith(
        isLoading: false,
        errorMessage: errorMsg,
      );
    }
  }
}