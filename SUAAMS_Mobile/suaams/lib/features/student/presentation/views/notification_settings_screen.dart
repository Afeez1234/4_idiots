import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Profile > "Notification settings".
class NotificationSettingsScreen extends StatelessWidget {
  const NotificationSettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComingSoonScreen(
      title: 'Notification Settings',
      subtitle: 'Notification preferences are coming soon.',
      icon: Icons.notifications_rounded,
    );
  }
}
