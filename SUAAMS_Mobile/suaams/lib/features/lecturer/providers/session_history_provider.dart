// Per-course session history -- same .family reasoning as
// course_workspace_provider.dart (courseId is the constructor arg, not a
// build() param, per Riverpod 3.x's family pattern).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/session_history_model.dart';
import 'lecturer_provider.dart';
import '../../../core/network/auth_retry.dart';

class SessionHistoryState {
  final bool isLoading;
  final SessionHistoryModel? data;
  final String? errorMessage;

  SessionHistoryState({this.isLoading = false, this.data, this.errorMessage});

  SessionHistoryState copyWith({
    bool? isLoading,
    SessionHistoryModel? data,
    String? errorMessage,
  }) {
    return SessionHistoryState(
      isLoading: isLoading ?? this.isLoading,
      data: data ?? this.data,
      errorMessage: errorMessage,
    );
  }
}

final sessionHistoryProvider = NotifierProvider.autoDispose
    .family<SessionHistoryNotifier, SessionHistoryState, int>(
      SessionHistoryNotifier.new,
    );

class SessionHistoryNotifier extends Notifier<SessionHistoryState> {
  final int courseId;

  SessionHistoryNotifier(this.courseId);

  @override
  SessionHistoryState build() {
    state = SessionHistoryState();
    Future.microtask(() => loadHistory());
    return state;
  }

  Future<void> loadHistory() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final data = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchSessionHistory(token, courseId),
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
