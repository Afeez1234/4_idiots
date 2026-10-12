// Per-session detail. Needs two IDs (course + session) as the family key,
// so this uses a Dart record as the family arg -- records are value-typed
// (structural == / hashCode), which is exactly what Riverpod's family
// lookup needs, so this works the same way a single-int family arg does
// elsewhere in this codebase (see course_workspace_provider.dart).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/lecturer/models/session_detail_model.dart';
import 'package:suaams/features/lecturer/data/lecturer_service.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';
import 'package:suaams/features/lecturer/providers/course_workspace_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';

typedef SessionDetailArgs = ({int courseId, int sessionId});

class SessionDetailState {
  final bool isLoading;
  final SessionDetailModel? data;
  final String? errorMessage;

  SessionDetailState({this.isLoading = false, this.data, this.errorMessage});

  SessionDetailState copyWith({
    bool? isLoading,
    SessionDetailModel? data,
    String? errorMessage,
  }) {
    return SessionDetailState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final sessionDetailProvider = NotifierProvider.autoDispose
    .family<SessionDetailNotifier, SessionDetailState, SessionDetailArgs>(
      SessionDetailNotifier.new,
    );

class SessionDetailNotifier extends Notifier<SessionDetailState> {
  final SessionDetailArgs args;

  SessionDetailNotifier(this.args);

  @override
  SessionDetailState build() {
    state = SessionDetailState();
    Future.microtask(() => loadDetail());
    return state;
  }

  Future<void> loadDetail() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchSessionDetail(
          token,
          args.courseId,
          args.sessionId,
        ),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, data: data);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
      );
    }
  }

  /// Lecturer marks one student present by hand. Returns null on success,
  /// or a message for the screen to show. Returned rather than written to
  /// state.errorMessage, because that field drives the full-screen error
  /// view -- a failed mark shouldn't replace the whole register.
  Future<String?> markPresent(int studentId) async {
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      await withAuthRetry(
        ref,
        (token) => lecturerService.markStudentPresent(
          token,
          args.courseId,
          args.sessionId,
          studentId,
        ),
      );
    } catch (e) {
      return userFacingError(e);
    }

    if (!ref.mounted) return null;
    // The course workspace's live list shows the same session's records,
    // so it would be stale until its own pull-to-refresh otherwise.
    ref.invalidate(courseWorkspaceProvider(args.courseId));
    await loadDetail();
    return null;
  }

  /// Accept or reject one offline tap. Returns the message to show either
  /// way (the server's on success, the error otherwise) -- same reasoning
  /// as markPresent for not writing to state.errorMessage.
  Future<String> reviewOfflineTap(int tapId, {required bool accept}) async {
    return _runAndReload(
      (service, token) => service.reviewOfflineTap(
        token,
        args.courseId,
        args.sessionId,
        tapId,
        accept: accept,
      ),
    );
  }

  /// Accept every pending offline tap for this session.
  Future<String> acceptAllOfflineTaps() async {
    return _runAndReload(
      (service, token) =>
          service.acceptAllOfflineTaps(token, args.courseId, args.sessionId),
    );
  }

  Future<String> _runAndReload(
    Future<String> Function(LecturerService service, String token) call,
  ) async {
    final String message;
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      message = await withAuthRetry(
        ref,
        (token) => call(lecturerService, token),
      );
    } catch (e) {
      return userFacingError(e);
    }

    if (!ref.mounted) return message;
    // Accepted taps become attendance, so the workspace's live list changes too.
    ref.invalidate(courseWorkspaceProvider(args.courseId));
    await loadDetail();
    return message;
  }
}
