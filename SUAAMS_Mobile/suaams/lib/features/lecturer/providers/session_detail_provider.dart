// Per-session detail. Needs two IDs (course + session) as the family key,
// so this uses a Dart record as the family arg -- records are value-typed
// (structural == / hashCode), which is exactly what Riverpod's family
// lookup needs, so this works the same way a single-int family arg does
// elsewhere in this codebase (see course_workspace_provider.dart).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/session_detail_model.dart';
import 'lecturer_provider.dart';
import '../../../core/network/auth_retry.dart';

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
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }
}
