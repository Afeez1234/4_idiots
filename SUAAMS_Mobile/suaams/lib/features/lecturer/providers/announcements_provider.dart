import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/announcement_model.dart';
import 'lecturer_provider.dart';
import '../../../core/network/auth_retry.dart';

class AnnouncementsState {
  final bool isLoading;
  final List<AnnouncementItem> announcements;
  final String? errorMessage;

  AnnouncementsState({
    this.isLoading = false,
    this.announcements = const [],
    this.errorMessage,
  });

  AnnouncementsState copyWith({
    bool? isLoading,
    List<AnnouncementItem>? announcements,
    String? errorMessage,
  }) {
    return AnnouncementsState(
      isLoading: isLoading ?? this.isLoading,
      announcements: announcements ?? this.announcements,
      errorMessage: errorMessage,
    );
  }
}

final announcementsProvider =
    NotifierProvider.autoDispose<AnnouncementsNotifier, AnnouncementsState>(
      AnnouncementsNotifier.new,
    );

class AnnouncementsNotifier extends Notifier<AnnouncementsState> {
  @override
  AnnouncementsState build() {
    state = AnnouncementsState();
    Future.microtask(() => loadAnnouncements());
    return state;
  }

  Future<void> loadAnnouncements() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      final announcements = await withAuthRetry(
        ref,
        (token) => lecturerService.fetchAnnouncements(token),
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

  // Returns true/false rather than throwing, same convention as
  // CourseWorkspaceNotifier.startSession -- the calling screen shows an
  // inline error without needing its own try/catch.
  Future<bool> postAnnouncement(
    int courseId, {
    required String title,
    required String body,
  }) async {
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      await withAuthRetry(
        ref,
        (token) => lecturerService.createAnnouncement(
          token,
          courseId,
          title: title,
          body: body,
        ),
      );
      await loadAnnouncements();
      return true;
    } catch (e) {
      if (ref.mounted) {
        state = state.copyWith(
          errorMessage: e.toString().replaceAll('Exception: ', ''),
        );
      }
      return false;
    }
  }

  // Same true/false + reload-after-mutate convention as postAnnouncement
  // above. Reloading (rather than removing the id locally) keeps this in
  // sync with the server's is_active filter as the source of truth, same
  // reasoning as CourseRegistrationNotifier only flipping its local
  // `enrolled` flag after the server confirms the mutation.
  Future<bool> deleteAnnouncement(int announcementId) async {
    try {
      final lecturerService = ref.read(lecturerServiceProvider);
      await withAuthRetry(
        ref,
        (token) => lecturerService.deleteAnnouncement(token, announcementId),
      );
      await loadAnnouncements();
      return true;
    } catch (e) {
      if (ref.mounted) {
        state = state.copyWith(
          errorMessage: e.toString().replaceAll('Exception: ', ''),
        );
      }
      return false;
    }
  }
}
