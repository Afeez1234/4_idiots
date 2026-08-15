// Per-course attendance history for this student -- .family by courseId,
// same reasoning as the lecturer feature's course_workspace_provider.dart.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/course_attendance_history_model.dart';
import 'student_provider.dart';
import '../../../core/network/auth_retry.dart';

class CourseAttendanceHistoryState {
  final bool isLoading;
  final CourseAttendanceHistoryModel? data;
  final String? errorMessage;

  CourseAttendanceHistoryState({
    this.isLoading = false,
    this.data,
    this.errorMessage,
  });

  CourseAttendanceHistoryState copyWith({
    bool? isLoading,
    CourseAttendanceHistoryModel? data,
    String? errorMessage,
  }) {
    return CourseAttendanceHistoryState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final courseAttendanceHistoryProvider = NotifierProvider.autoDispose
    .family<
      CourseAttendanceHistoryNotifier,
      CourseAttendanceHistoryState,
      int
    >(CourseAttendanceHistoryNotifier.new);

class CourseAttendanceHistoryNotifier
    extends Notifier<CourseAttendanceHistoryState> {
  final int courseId;

  CourseAttendanceHistoryNotifier(this.courseId);

  @override
  CourseAttendanceHistoryState build() {
    state = CourseAttendanceHistoryState();
    Future.microtask(() => loadHistory());
    return state;
  }

  Future<void> loadHistory() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final studentService = ref.read(studentServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => studentService.fetchCourseAttendanceHistory(token, courseId),
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
