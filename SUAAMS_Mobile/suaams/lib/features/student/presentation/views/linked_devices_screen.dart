import 'package:flutter/material.dart';
import '../../../../shared/widgets/coming_soon_screen.dart';

// Placeholder for Profile > "Linked devices". Per the device-binding threat
// model (see CLAUDE.md), resetting a binding is admin-only via the web
// dashboard -- this screen would show the currently bound device_id and
// explain that flow, once built.
class LinkedDevicesScreen extends StatelessWidget {
  const LinkedDevicesScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ComingSoonScreen(
      title: 'Linked Devices',
      subtitle: 'Device binding management is coming soon.',
      icon: Icons.phonelink_lock_rounded,
    );
  }
}
