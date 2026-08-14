// Backs the notification inbox screen (notification_settings_screen.dart).
// Kept as its own provider, same reasoning as today_schedule_provider.dart --
// independently refreshable without touching dashboard state.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../models/notification_item.dart';
import '../providers/student_provider.dart';
import '../../../core/network/auth_retry.dart';

class NotificationsState {
  final bool isLoading;
  final List<NotificationItem> notifications;
  final String? errorMessage;

  NotificationsState({
    this.isLoading = false,
    this.notifications = const [],
    this.errorMessage,
  });

  int get unreadCount => notifications.where((n) => !n.read).length;

  NotificationsState copyWith({
    bool? isLoading,
    List<NotificationItem>? notifications,
    String? errorMessage,
  }) {
    return NotificationsState(
      isLoading: isLoading ?? this.isLoading,
      notifications: notifications ?? this.notifications,
      errorMessage: errorMessage,
    );
  }
}

final notificationsProvider =
    NotifierProvider.autoDispose<NotificationsNotifier, NotificationsState>(
      NotificationsNotifier.new,
    );

class NotificationsNotifier extends Notifier<NotificationsState> {
  @override
  NotificationsState build() {
    state = NotificationsState();
    Future.microtask(() => loadNotifications());
    return state;
  }

  Future<void> loadNotifications() async {
    state = state.copyWith(isLoading: true, errorMessage: null);

    try {
      final studentService = ref.read(studentServiceProvider);
      final notifications = await withAuthRetry(
        ref,
        (token) => studentService.fetchNotifications(token),
      );

      if (ref.mounted) {
        state = state.copyWith(isLoading: false, notifications: notifications);
      }
    } catch (e) {
      if (!ref.mounted) return;
      state = state.copyWith(
        isLoading: false,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );
    }
  }

  // Optimistic: flips the local `read` flag immediately (so the UI responds
  // instantly to a tap) rather than waiting on the round trip. If the
  // backend call fails, the row silently stays marked read locally until the
  // next loadNotifications() reconciles it -- a stale unread badge for one
  // item until the next refresh is an acceptable tradeoff against making
  // every tap feel laggy.
  Future<void> markRead(int notificationId) async {
    final target = state.notifications.where((n) => n.id == notificationId);
    if (target.isEmpty || target.first.read) return;

    state = state.copyWith(
      notifications: [
        for (final n in state.notifications)
          if (n.id == notificationId)
            NotificationItem(
              id: n.id,
              type: n.type,
              title: n.title,
              body: n.body,
              data: n.data,
              read: true,
              createdAt: n.createdAt,
            )
          else
            n,
      ],
    );

    try {
      final studentService = ref.read(studentServiceProvider);
      await withAuthRetry(
        ref,
        (token) => studentService.markNotificationRead(token, notificationId),
      );
    } catch (e) {
      // Swallowed deliberately -- see docstring above.
    }
  }
}
