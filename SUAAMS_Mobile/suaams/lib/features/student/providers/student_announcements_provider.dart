// Backs the student Announcements screen. Same shape as
// notifications_provider.dart -- independently refreshable, read-only
// (students can't post/delete, unlike the lecturer-side announcementsProvider).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/student_announcement_model.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

class StudentAnnouncementsState {
  final bool isLoading;
  final List<StudentAnnouncement> announcements;
  final String? errorMessage;

  StudentAnnouncementsState({
    this.isLoading = false,
    this.announcements = const [],
    this.errorMessage,
  });

  StudentAnnouncementsState copyWith({
    bool? isLoading,
    List<StudentAnnouncement>? announcements,
    String? errorMessage,
  }) {
    return StudentAnnouncementsState(
      isLoading: isLoading ?? this.isLoading,
      announcements: announcements ?? this.announcements,
      errorMessage: errorMessage,
    );
  }
}

final studentAnnouncementsProvider = NotifierProvider.autoDispose<
    StudentAnnouncementsNotifier, StudentAnnouncementsState>(
  StudentAnnouncementsNotifier.new,
);

class StudentAnnouncementsNotifier
    extends Notifier<StudentAnnouncementsState> {
  @override
  StudentAnnouncementsState build() {
    state = StudentAnnouncementsState();
    Future.microtask(() => loadAnnouncements());
    return state;
  }

  Future<void> loadAnnouncements() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final studentService = ref.read(studentServiceProvider);
      final announcements = await withAuthRetry(
        ref,
        (token) => studentService.fetchAnnouncements(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, announcements: announcements);
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
