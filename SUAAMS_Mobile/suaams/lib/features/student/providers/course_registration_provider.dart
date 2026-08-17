// Backs the course registration screen. Kept as its own provider, same
// reasoning as notifications_provider.dart -- independently refreshable
// without touching dashboard/courses-tab state, and the dashboard's own
// CourseBreakdown list only ever contains courses already enrolled in, so
// it can't answer "what else is there to register for" on its own.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/available_course_model.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

class CourseRegistrationState {
  final bool isLoading;
  final List<AvailableCourse> courses;
  final String? semester;
  final String? errorMessage;
  // Course ids with a register/drop call currently in flight -- lets the
  // UI disable just that row's button instead of the whole screen.
  final Set<int> pendingCourseIds;

  CourseRegistrationState({
    this.isLoading = false,
    this.courses = const [],
    this.semester,
    this.errorMessage,
    this.pendingCourseIds = const {},
  });

  CourseRegistrationState copyWith({
    bool? isLoading,
    List<AvailableCourse>? courses,
    String? semester,
    String? errorMessage,
    Set<int>? pendingCourseIds,
  }) {
    return CourseRegistrationState(
      isLoading: isLoading ?? this.isLoading,
      courses: courses ?? this.courses,
      semester: semester ?? this.semester,
      errorMessage: errorMessage,
      pendingCourseIds: pendingCourseIds ?? this.pendingCourseIds,
    );
  }
}

final courseRegistrationProvider = NotifierProvider.autoDispose<
  CourseRegistrationNotifier,
  CourseRegistrationState
>(CourseRegistrationNotifier.new);

class CourseRegistrationNotifier extends Notifier<CourseRegistrationState> {
  @override
  CourseRegistrationState build() {
    state = CourseRegistrationState();
    Future.microtask(() => loadAvailableCourses());
    return state;
  }

  Future<void> loadAvailableCourses() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final studentService = ref.read(studentServiceProvider);
      final courses = await withAuthRetry(
        ref,
        (token) => studentService.fetchAvailableCourses(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, courses: courses);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }

  Future<void> register(int courseId) => _mutate(
    courseId: courseId,
    enrolledAfter: true,
    call: (token) =>
        ref.read(studentServiceProvider).registerCourse(token, courseId),
  );

  Future<void> drop(int courseId) => _mutate(
    courseId: courseId,
    enrolledAfter: false,
    call: (token) =>
        ref.read(studentServiceProvider).dropCourse(token, courseId),
  );

  // Shared register/drop plumbing: marks the row pending, calls the
  // backend, and only flips `enrolled` locally once the server confirms it
  // (unlike notifications' markRead, a failed registration/drop needs to be
  // visible -- silently trusting an optimistic flip here could tell a
  // student they're registered for a course they aren't).
  Future<void> _mutate({
    required int courseId,
    required bool enrolledAfter,
    required Future<void> Function(String token) call,
  }) async {
    state = state.copyWith(
      errorMessage: null,
      pendingCourseIds: {...state.pendingCourseIds, courseId},
    );

    try {
      await withAuthRetry(ref, call);

      if (!ref.mounted) return;
      state = state.copyWith(
        courses: [
          for (final c in state.courses)
            if (c.id == courseId) c.copyWith(enrolled: enrolledAfter) else c,
        ],
        pendingCourseIds: {...state.pendingCourseIds}..remove(courseId),
      );
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        errorMessage: e.toString().replaceAll('Exception: ', ''),
        pendingCourseIds: {...state.pendingCourseIds}..remove(courseId),
      );
    }
  }
}
