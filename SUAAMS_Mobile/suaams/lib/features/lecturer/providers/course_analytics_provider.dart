// Per-course analytics -- .family by courseId, same reasoning as
// course_workspace_provider.dart / session_history_provider.dart.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/course_analytics_model.dart';
import 'lecturer_provider.dart';
import '../../../core/network/auth_retry.dart';

class CourseAnalyticsState {
  final bool isLoading;
  final CourseAnalyticsModel? data;
  final String? errorMessage;

  CourseAnalyticsState({this.isLoading = false, this.data, this.errorMessage});

  CourseAnalyticsState copyWith({
    bool? isLoading,
    CourseAnalyticsModel? data,
    String? errorMessage,
  }) {
    return CourseAnalyticsState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final courseAnalyticsProvider = NotifierProvider.autoDispose
    .family<CourseAnalyticsNotifier, CourseAnalyticsState, int>(
      CourseAnalyticsNotifier.new,
    );

class CourseAnalyticsNotifier extends Notifier<CourseAnalyticsState> {
  final int courseId;

  CourseAnalyticsNotifier(this.courseId);

  @override
  CourseAnalyticsState build() {
    state = CourseAnalyticsState();
    Future.microtask(() => loadAnalytics());
    return state;
  }

  Future<void> loadAnalytics() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchCourseAnalytics(token, courseId),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, data: data);
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
