import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../models/notification_item.dart';
import '../../providers/notifications_provider.dart';

// Profile > "Notification Settings" -- was a ComingSoonScreen placeholder;
// now the real notification inbox (list.dart + Notification model backing
// GET/POST /student/notifications, see push_notifications.py on the
// backend). Named "settings" in the router/profile menu still, but there
// are no granular per-category toggles yet -- only the three triggers
// actually wired server-side (attendance marked, device unlocked, device
// lockout alert) exist to have preferences about, and none of them are
// safe to let a student opt out of (the lockout alert in particular is a
// security notice, not a marketing ping) -- so this is a read/mark-read
// inbox, not a preferences form.
class NotificationSettingsScreen extends ConsumerWidget {
  const NotificationSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(notificationsProvider);
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Notifications'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(notificationsProvider.notifier).loadNotifications(),
        child: _buildBody(context, ref, state, colorScheme),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    WidgetRef ref,
    NotificationsState state,
    ColorScheme colorScheme,
  ) {
    if (state.isLoading && state.notifications.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.errorMessage != null && state.notifications.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 96, horizontal: 32),
            child: Column(
              children: [
                Icon(
                  Icons.error_outline_rounded,
                  size: 48,
                  color: colorScheme.error.withValues(alpha: 0.5),
                ),
                const SizedBox(height: 16),
                Text(
                  state.errorMessage!,
                  textAlign: TextAlign.center,
                  style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.6)),
                ),
              ],
            ),
          ),
        ],
      );
    }

    if (state.notifications.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 96, horizontal: 32),
            child: Column(
              children: [
                Icon(
                  Icons.notifications_none_rounded,
                  size: 48,
                  color: colorScheme.onSurface.withValues(alpha: 0.2),
                ),
                const SizedBox(height: 16),
                Text(
                  'NO NOTIFICATIONS YET',
                  style: TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
        ],
      );
    }

    return ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(16),
      itemCount: state.notifications.length,
      separatorBuilder: (context, index) => const SizedBox(height: 10),
      itemBuilder: (context, index) {
        final item = state.notifications[index];
        return _NotificationTile(
          item: item,
          colorScheme: colorScheme,
          onTap: () => ref.read(notificationsProvider.notifier).markRead(item.id),
        );
      },
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final NotificationItem item;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _NotificationTile({
    required this.item,
    required this.colorScheme,
    required this.onTap,
  });

  (IconData, Color) _iconFor(String type, ColorScheme colorScheme) {
    switch (type) {
      case 'attendance_marked':
        return (Icons.check_circle_rounded, colorScheme.primary);
      case 'device_unlocked':
        return (Icons.lock_open_rounded, colorScheme.primary);
      case 'device_lockout_alert':
        return (Icons.warning_amber_rounded, colorScheme.error);
      default:
        return (Icons.notifications_rounded, colorScheme.primary);
    }
  }

  String _relativeTime(DateTime dt) {
    final diff = DateTime.now().toUtc().difference(dt.toUtc());
    if (diff.inMinutes < 1) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.day}/${dt.month}/${dt.year}';
  }

  @override
  Widget build(BuildContext context) {
    final (icon, iconColor) = _iconFor(item.type, colorScheme);

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: item.read
              ? colorScheme.surfaceContainer.withValues(alpha: 0.5)
              : colorScheme.primary.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: item.read
                ? colorScheme.outline.withValues(alpha: 0.1)
                : colorScheme.primary.withValues(alpha: 0.2),
          ),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: iconColor, size: 22),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          item.title,
                          style: TextStyle(
                            fontWeight: item.read ? FontWeight.w600 : FontWeight.bold,
                            fontSize: 14,
                          ),
                        ),
                      ),
                      if (!item.read)
                        Container(
                          width: 8,
                          height: 8,
                          margin: const EdgeInsets.only(left: 8, top: 4),
                          decoration: BoxDecoration(
                            color: colorScheme.primary,
                            shape: BoxShape.circle,
                          ),
                        ),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    item.body,
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    _relativeTime(item.createdAt),
                    style: TextStyle(
                      fontSize: 10,
                      fontFamily: 'JetBrains Mono',
                      color: colorScheme.onSurface.withValues(alpha: 0.4),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
