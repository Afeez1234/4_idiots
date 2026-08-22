import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/student_announcements_provider.dart';
import '../../models/student_announcement_model.dart';

// Reached from the Home tab's app bar (see student_home_screen.dart).
// Read-only -- unlike the lecturer side's AnnouncementsListScreen, a student
// can't post or delete, only see what applies to them (university-wide,
// their department, or a course they're enrolled in).
class AnnouncementsScreen extends ConsumerWidget {
  const AnnouncementsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentAnnouncementsProvider);
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Announcements'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(studentAnnouncementsProvider.notifier).loadAnnouncements(),
        child: _buildBody(context, state, colorScheme),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    StudentAnnouncementsState state,
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
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 32),
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

class _AnnouncementCard extends StatelessWidget {
  final StudentAnnouncement item;
  final ColorScheme colorScheme;

  const _AnnouncementCard({required this.item, required this.colorScheme});

  // Scope tells the reader why they're seeing this: their own course, their
  // department, or the whole university. Falls back to whichever specific
  // name the backend sent; 'UNIVERSITY' when nothing more specific applies.
  String get _badgeLabel {
    if (item.scope == 'course' && item.courseCode != null) {
      return item.courseCode!;
    }
    if (item.scope == 'department' && item.departmentName != null) {
      return item.departmentName!.toUpperCase();
    }
    return 'UNIVERSITY';
  }

  String? get _formattedDate {
    if (item.createdAt == null) return null;
    try {
      final dt = DateTime.parse(item.createdAt!).toLocal();
      const months = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
      ];
      final hour = dt.hour.toString().padLeft(2, '0');
      final minute = dt.minute.toString().padLeft(2, '0');
      return '${dt.day} ${months[dt.month - 1]} ${dt.year}, $hour:$minute';
    } catch (_) {
      // Malformed/unexpected date string -- fall back to the raw value
      // rather than crashing the card.
      return item.createdAt;
    }
  }

  @override
  Widget build(BuildContext context) {
    final formattedDate = _formattedDate;

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
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  item.title,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 15,
                  ),
                ),
              ),
              const SizedBox(width: 8),
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
                  _badgeLabel,
                  style: TextStyle(
                    fontSize: 9,
                    fontFamily: 'JetBrains Mono',
                    fontWeight: FontWeight.bold,
                    color: colorScheme.primary,
                  ),
                ),
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
          if (formattedDate != null) ...[
            const SizedBox(height: 10),
            Text(
              formattedDate,
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
