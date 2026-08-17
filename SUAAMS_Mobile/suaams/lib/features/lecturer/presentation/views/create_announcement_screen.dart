import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/lecturer_provider.dart';
import '../../providers/announcements_provider.dart';

// Reuses the already-loaded lecturerDashboardProvider for the course
// picker -- same reasoning as ActiveSessionsScreen -- rather than a
// separate fetch just to list "your courses" again.
class CreateAnnouncementScreen extends ConsumerStatefulWidget {
  const CreateAnnouncementScreen({super.key});

  @override
  ConsumerState<CreateAnnouncementScreen> createState() =>
      _CreateAnnouncementScreenState();
}

class _CreateAnnouncementScreenState
    extends ConsumerState<CreateAnnouncementScreen> {
  final _titleController = TextEditingController();
  final _bodyController = TextEditingController();
  int? _selectedCourseId;
  bool _submitting = false;

  @override
  void dispose() {
    _titleController.dispose();
    _bodyController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final title = _titleController.text.trim();
    final body = _bodyController.text.trim();

    if (_selectedCourseId == null || title.isEmpty || body.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Pick a course and fill in both fields.'),
        ),
      );
      return;
    }

    setState(() => _submitting = true);
    final success = await ref
        .read(announcementsProvider.notifier)
        .postAnnouncement(_selectedCourseId!, title: title, body: body);
    if (!mounted) return;
    setState(() => _submitting = false);

    if (success) {
      Navigator.of(context).pop();
    } else {
      final error = ref.read(announcementsProvider).errorMessage;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error ?? 'Failed to post announcement.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final dashboardState = ref.watch(lecturerDashboardProvider);
    final colorScheme = Theme.of(context).colorScheme;
    final courses = dashboardState.data?.courses ?? const [];

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('New Announcement'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'COURSE',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 1.5,
                fontWeight: FontWeight.bold,
                color: colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(height: 8),
            DropdownButtonFormField<int>(
              // Keyed by the selected id so a selection change remounts
              // this field with the new initialValue -- DropdownButtonFormField
              // wraps its own FormFieldState that (like
              // TextFormField.initialValue) only reads initialValue on first
              // build, not on every rebuild. Without the key, the dropdown
              // silently reverted to unselected the moment any unrelated
              // rebuild happened (e.g. focusing the Title field below) --
              // found via an on-device tap-through, not the analyzer, since
              // initialValue is a perfectly valid, non-deprecated param so
              // nothing flagged it.
              key: ValueKey(_selectedCourseId),
              initialValue: _selectedCourseId,
              hint: const Text('Select a course'),
              isExpanded: true,
              decoration: InputDecoration(
                filled: true,
                fillColor: colorScheme.surfaceContainer,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: BorderSide.none,
                ),
                contentPadding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 4,
                ),
              ),
              items: courses
                  .map(
                    (c) => DropdownMenuItem(
                      value: c.id,
                      child: Text('${c.code} · ${c.title}'),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _selectedCourseId = value),
            ),
            const SizedBox(height: 24),
            Text(
              'TITLE',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 1.5,
                fontWeight: FontWeight.bold,
                color: colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(height: 8),
            RepaintBoundary(
              child: TextField(
                controller: _titleController,
                decoration: InputDecoration(
                  hintText: 'e.g. Class moved to LR 4',
                  filled: true,
                  fillColor: colorScheme.surfaceContainer,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 24),
            Text(
              'MESSAGE',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 1.5,
                fontWeight: FontWeight.bold,
                color: colorScheme.onSurface.withValues(alpha: 0.5),
              ),
            ),
            const SizedBox(height: 8),
            RepaintBoundary(
              child: TextField(
                controller: _bodyController,
                maxLines: 6,
                decoration: InputDecoration(
                  hintText: 'Write your announcement...',
                  filled: true,
                  fillColor: colorScheme.surfaceContainer,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 32),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: colorScheme.primary,
                foregroundColor: colorScheme.surface,
                minimumSize: const Size(double.infinity, 48),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                elevation: 0,
              ),
              onPressed: _submitting ? null : _submit,
              child: _submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text(
                      'POST ANNOUNCEMENT',
                      style: TextStyle(
                        letterSpacing: 2,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}
