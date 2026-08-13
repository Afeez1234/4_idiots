import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../../shared/widgets/app_bottom_nav.dart';

// Hosts the 5-tab lecturer bottom nav (Home, Sessions, Reports, Announce,
// Profile). Mirrors StudentShellScreen -- see its comment for why
// StatefulShellRoute.indexedStack (one Navigator per tab) instead of the
// single-Scaffold pattern the app used to use nowhere on the lecturer side
// at all (there was no bottom nav here before this redesign).
class LecturerShellScreen extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const LecturerShellScreen({super.key, required this.navigationShell});

  static const _items = [
    AppBottomNavItem(icon: Icons.grid_view_rounded, label: 'HOME'),
    AppBottomNavItem(icon: Icons.sensors_rounded, label: 'SESSIONS'),
    AppBottomNavItem(icon: Icons.summarize_rounded, label: 'REPORTS'),
    AppBottomNavItem(icon: Icons.campaign_rounded, label: 'ANNOUNCE'),
    AppBottomNavItem(icon: Icons.person_rounded, label: 'PROFILE'),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: AppBottomNav(
        items: _items,
        currentIndex: navigationShell.currentIndex,
        onTap: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
      ),
    );
  }
}
