// Backs the course registration screen. Kept as its own provider, same
// reasoning as notifications_provider.dart -- independently refreshable
// without touching dashboard/courses-tab state, and the dashboard's own
// CourseBreakdown list only ever contains courses already enrolled in, so
// it can't answer "what else is there to register for" on its own.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/models/available_course_model.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/providers/today_schedule_provider.dart';
import 'package:suaams/features/student/providers/week_schedule_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';

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
        errorMessage: userFacingError(e),
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

  /// Drops the cached state of every view whose data is derived from the
  /// student's enrollment set, so a register/drop is reflected without
  /// needing a cold restart.
  ///
  /// All three are backed by endpoints that re-derive from
  /// `student.courses` on the server, so there is no server-side cache to
  /// clear -- the staleness here is purely client-side, and invalidating
  /// makes each one refetch on its next read.
  ///
  /// The invalidation has to be explicit because of how the tab shell
  /// works: this screen lives in the Attendance branch of a
  /// `StatefulShellRoute.indexedStack`, which keeps *every* branch's
  /// widget tree mounted at all times. That means the Timetable branch's
  /// `ref.watch(weekScheduleProvider)` is never unmounted, so the
  /// autoDispose provider is never disposed either and its one-shot
  /// `Future.microtask` load in build() never re-runs. Switching tabs
  /// looks like it should refetch and does not.
  ///
  /// Called only after the server confirms the mutation -- an earlier
  /// version invalidated optimistically, which refetched three endpoints
  /// on every tap and then landed stale data again if the call failed.
  ///
  /// Safe to call unconditionally: these are autoDispose, so invalidating
  /// one that is currently disposed is a no-op, not an error. Mirrors
  /// `_invalidateAttendanceViews` in nfc_provider.dart, which does the
  /// same thing after a check-in.
  void _invalidateEnrollmentViews() {
    // Timetable tab + Day Detail.
    ref.invalidate(weekScheduleProvider);
    // "Today's Protocol" list on the dashboard Home tab.
    ref.invalidate(todayScheduleProvider);
    // Courses tab (CourseBreakdown list) + dashboard stats.
    ref.invalidate(studentDashboardProvider);
  }

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
      // The flip above only updates *this* list. The timetable, today's
      // protocol, and the courses tab are separate providers fed by
      // separate endpoints, so they need telling.
      _invalidateEnrollmentViews();
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        errorMessage: userFacingError(e),
        pendingCourseIds: {...state.pendingCourseIds}..remove(courseId),
      );
    }
  }
}
