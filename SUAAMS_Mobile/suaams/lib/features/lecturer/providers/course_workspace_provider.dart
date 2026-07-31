// Backs the course workspace screen -- per-course, so this is the first
// Riverpod .family provider in this codebase. Riverpod 3.x removed the old
// FamilyNotifier base class (see riverpod's CHANGELOG, 3.0.0-dev.18): a
// family Notifier is just a regular Notifier<StateT> whose CONSTRUCTOR
// takes the family argument (here, courseId), not its build() method --
// `NotifierProvider.autoDispose.family<N, State, Arg>(N.new)` expects
// `N.new` to match `N Function(Arg arg)`, which a constructor tear-off
// does automatically. courseId is then just a stored field, readable from
// build() and every other method on the notifier.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/course_workspace_model.dart';
import 'lecturer_provider.dart';
import '../../../core/network/auth_retry.dart';

class CourseWorkspaceState {
  final bool isLoading;
  final CourseWorkspaceModel? data;
  final String? errorMessage;

  CourseWorkspaceState({
    this.isLoading = false,
    this.data,
    this.errorMessage,
  });

  CourseWorkspaceState copyWith({
    bool? isLoading,
    CourseWorkspaceModel? data,
    String? errorMessage,
  }) {
    return CourseWorkspaceState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final courseWorkspaceProvider = NotifierProvider.autoDispose
    .family<CourseWorkspaceNotifier, CourseWorkspaceState, int>(
      CourseWorkspaceNotifier.new,
    );

class CourseWorkspaceNotifier extends Notifier<CourseWorkspaceState> {
  final int courseId;

  CourseWorkspaceNotifier(this.courseId);

  @override
  CourseWorkspaceState build() {
    state = CourseWorkspaceState();
    Future.microtask(() => loadWorkspace());
    return state;
  }

  Future<void> loadWorkspace() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchCourseWorkspace(token, courseId),
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

  // Returns true/false rather than throwing so the calling screen can show
  // an inline error without needing a try/catch of its own -- same
  // convention as AuthNotifier.login/changePassword.
  Future<bool> startSession({String? plannedStart, String? plannedEnd}) async {
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      await withAuthRetry(
        ref,
        (token) => lecturerService.startSession(
          token,
          courseId,
          plannedStart: plannedStart,
          plannedEnd: plannedEnd,
        ),
      );
      await loadWorkspace();
      return true;
    } catch (e) {
      if (ref.mounted) {
        state = state.copyWith(errorMessage: e.toString().replaceAll('Exception: ', ''));
      }
      return false;
    }
  }

  Future<bool> endSession() async {
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      await withAuthRetry(
        ref,
        (token) => lecturerService.endSession(token, courseId),
      );
      await loadWorkspace();
      return true;
    } catch (e) {
      if (ref.mounted) {
        state = state.copyWith(errorMessage: e.toString().replaceAll('Exception: ', ''));
      }
      return false;
    }
  }
}
