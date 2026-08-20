import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/announcements_provider.dart';
import '../../models/announcement_model.dart';

// Announce tab root. Course-scoped announcements only (scope='university'/
// 'department' stay admin-only, see get_lecturer_announcements's
// doc-comment in api/lecturer.py).
class AnnouncementsListScreen extends ConsumerWidget {
  const AnnouncementsListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(announcementsProvider);
    final colorScheme = Theme.of(context).colorScheme;

    // Delete failures (e.g. a network drop, or the announcement having
    // already been removed) surface as a SnackBar -- same convention as
    // course_registration_screen.dart's mutation errors. The list itself
    // is still valid either way, only the one delete attempt failed.
    ref.listen(announcementsProvider, (previous, next) {
      if (next.errorMessage != null &&
          next.errorMessage != previous?.errorMessage &&
          !next.isLoading) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next.errorMessage!)),
        );
      }
    });

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Announcements'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(announcementsProvider.notifier).loadAnnouncements(),
        child: _buildBody(context, state, colorScheme),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/lecturer/announce/create'),
        icon: const Icon(Icons.add_rounded),
        label: const Text('NEW'),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    AnnouncementsState state,
    ColorScheme colorScheme,
  ) {
    if (state.isLoading && state.announcements.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.errorMessage != null && state.announcements.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Padding(
            padding: const EdgeInsets.all(32),
            child: Center(
              child: Text(
                state.errorMessage!,
                style: TextStyle(color: colorScheme.error),
              ),
            ),
          ),
        ],
      );
    }

    if (state.announcements.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 120),
            child: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.campaign_rounded,
                    size: 48,
                    color: colorScheme.onSurface.withValues(alpha: 0.2),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'NO ANNOUNCEMENTS YET',
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
          ),
        ],
      );
    }

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 96),
      children: state.announcements
          .map(
            (a) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: _AnnouncementCard(item: a, colorScheme: colorScheme),
            ),
          )
          .toList(),
    );
  }
}

class _AnnouncementCard extends ConsumerWidget {
  final AnnouncementItem item;
  final ColorScheme colorScheme;

  const _AnnouncementCard({required this.item, required this.colorScheme});

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainer,
        title: const Text('Delete Announcement', style: TextStyle(fontWeight: FontWeight.bold)),
        content: Text('Delete "${item.title}"? This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('CANCEL', style: TextStyle(color: colorScheme.onSurface)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: colorScheme.error,
              foregroundColor: colorScheme.onError,
            ),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('DELETE'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      ref.read(announcementsProvider.notifier).deleteAnnouncement(item.id);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  item.title,
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                ),
              ),
              if (item.courseCode != null) ...[
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: colorScheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    item.courseCode!,
                    style: TextStyle(
                      fontSize: 9,
                      fontFamily: 'JetBrains Mono',
                      fontWeight: FontWeight.bold,
                      color: colorScheme.primary,
                    ),
                  ),
                ),
                const SizedBox(width: 4),
              ],
              IconButton(
                onPressed: () => _confirmDelete(context, ref),
                icon: const Icon(Icons.delete_outline_rounded, size: 20),
                color: colorScheme.onSurface.withValues(alpha: 0.4),
                tooltip: 'Delete announcement',
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            item.body,
            style: TextStyle(
              fontSize: 13,
              height: 1.4,
              color: colorScheme.onSurface.withValues(alpha: 0.8),
            ),
          ),
          if (item.createdAt != null) ...[
            const SizedBox(height: 10),
            Text(
              item.createdAt!,
              style: TextStyle(
                fontSize: 10,
                fontFamily: 'JetBrains Mono',
                color: colorScheme.onSurface.withValues(alpha: 0.4),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
