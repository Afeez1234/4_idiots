import 'package:flutter/material.dart';
import 'profile_view_screen.dart';

// Profile tab root. ProfileView itself has no Scaffold -- it used to be
// embedded directly inside StudentDashboardScreen's single shared Scaffold
// (background, SafeArea) alongside the other tab bodies. Now that it's a
// routed branch root in its own right, it needs that chrome itself.
class StudentProfileScreen extends StatelessWidget {
  const StudentProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Profile'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: const SafeArea(child: ProfileView()),
    );
  }
}
