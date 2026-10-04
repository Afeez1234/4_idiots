// Backs the student Announcements screen AND the unread badge on the home
// header's announcements button. Same shape as notifications_provider.dart --
// independently refreshable, read-only (students can't post/delete, unlike
// the lecturer-side announcementsProvider).
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/models/student_announcement_model.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/network/user_facing_error.dart';

class StudentAnnouncementsState {
  final bool isLoading;
  final List<StudentAnnouncement> announcements;
  final String? errorMessage;

  /// Server-defined count of unread announcements, driving the badge.
  /// Kept as its own field rather than derived from the list at each render
  /// site so the badge and the list can't disagree.
  final int unreadCount;

  StudentAnnouncementsState({
    this.isLoading = false,
    this.announcements = const [],
    this.errorMessage,
    this.unreadCount = 0,
  });

  StudentAnnouncementsState copyWith({
    bool? isLoading,
    List<StudentAnnouncement>? announcements,
    String? errorMessage,
    int? unreadCount,
  }) {
    return StudentAnnouncementsState(
      isLoading: isLoading ?? this.isLoading,
      announcements: announcements ?? this.announcements,
      errorMessage: errorMessage,
      unreadCount: unreadCount ?? this.unreadCount,
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
      final result = await withAuthRetry(
        ref,
        (token) => studentService.fetchAnnouncements(token),
      );

      if (ref.mounted) {
        state = state.copyWith(
          isLoading: false,
          announcements: result.items,
          unreadCount: result.unreadCount,
        );
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: userFacingError(e),
      );
    }
  }

  /// Called when the student opens the announcements screen. Clears the
  /// badge immediately and tells the server in the background -- waiting on
  /// the round-trip would make the badge visibly lag the tap that cleared
  /// it, and a failure here self-corrects on the next fetch.
  Future<void> markAllSeen() async {
    if (state.unreadCount == 0 || state.announcements.isEmpty) return;

    final newestId = state.announcements.first.id;
    // Optimistic. The list is ordered newest-first server-side, so the head
    // is the highest id -- which is exactly what the watermark takes.
    state = state.copyWith(
      unreadCount: 0,
      announcements: state.announcements
          .map((a) => StudentAnnouncement(
                id: a.id,
                title: a.title,
                body: a.body,
                scope: a.scope,
                departmentName: a.departmentName,
                courseCode: a.courseCode,
                createdAt: a.createdAt,
                isRead: true,
              ))
          .toList(),
    );

    try {
      final studentService = ref.read(studentServiceProvider);
      await withAuthRetry(
        ref,
        (token) => studentService.markAnnouncementsSeen(token, newestId),
      );
    } catch (_) {
      // Swallowed deliberately -- see above. The optimistic state stays, and
      // the next loadAnnouncements() restores the truth from the server.
    }
  }
}
