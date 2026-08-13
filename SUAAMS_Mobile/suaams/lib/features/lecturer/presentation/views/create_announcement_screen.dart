import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Announce > "Create announcement (select course, write
// message)".
class CreateAnnouncementScreen extends StatelessWidget {
  const CreateAnnouncementScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComingSoonScreen(
      title: 'New Announcement',
      subtitle: 'Composing announcements is coming soon.',
      icon: Icons.edit_note_rounded,
    );
  }
}
