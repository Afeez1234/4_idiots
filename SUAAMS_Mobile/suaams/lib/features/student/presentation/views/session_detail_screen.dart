import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Attendance > Session history > "Session detail
// (tap a session)".
class SessionDetailScreen extends StatelessWidget {
  final String sessionId;

  const SessionDetailScreen({super.key, required this.sessionId});

  @override
  Widget build(BuildContext context) {
    return ComingSoonScreen(
      title: 'Session Detail',
      subtitle: 'Detail view for session #$sessionId is coming soon.',
      icon: Icons.event_note_rounded,
    );
  }
}
