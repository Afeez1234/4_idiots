import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../shared/widgets/app_bottom_nav.dart';

// Hosts the 5-tab student bottom nav (Home, Timetable, Attendance, ID Card,
// Profile). One StatefulShellBranch per tab in app_router.dart, each with
// its own Navigator stack -- so pushing e.g. a course detail screen from
// Home doesn't disturb Attendance's stack, and switching tabs keeps each
// one's scroll position/back-stack intact.
class StudentShellScreen extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const StudentShellScreen({super.key, required this.navigationShell});

  static const _items = [
    AppBottomNavItem(icon: Icons.grid_view_rounded, label: 'HOME'),
    AppBottomNavItem(icon: Icons.calendar_month_rounded, label: 'TIMETABLE'),
    AppBottomNavItem(icon: Icons.fact_check_rounded, label: 'ATTENDANCE'),
    AppBottomNavItem(icon: Icons.badge_rounded, label: 'ID CARD'),
    AppBottomNavItem(icon: Icons.person_rounded, label: 'PROFILE'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: AppBottomNav(
        items: _items,
        currentIndex: navigationShell.currentIndex,
        // initialLocation: true re-taps the tab back to its own root route
        // instead of just restoring wherever it was left mid-stack -- matches
        // the common "tap the active tab to go back to top" convention.
        onTap: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
      ),
    );
  }
}
