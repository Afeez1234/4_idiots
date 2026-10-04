import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';
import 'package:suaams/shared/widgets/app_bottom_nav.dart';

// Hosts the 5-tab lecturer bottom nav (Home, Sessions, Reports, Announce,
// Profile). Mirrors StudentShellScreen -- see its comment for why
// StatefulShellRoute.indexedStack (one Navigator per tab) instead of the
// single-Scaffold pattern the app used to use nowhere on the lecturer side
// at all (there was no bottom nav here before this redesign).
//
// A Consumer only so the Sessions tab can carry a live-session dot; the
// select() in build is what keeps that cheap.
class LecturerShellScreen extends ConsumerWidget {
  final StatefulNavigationShell navigationShell;

  const LecturerShellScreen({super.key, required this.navigationShell});

  static const _nav = <({IconData icon, String label})>[
    (icon: Icons.grid_view_rounded, label: 'Home'),
    (icon: Icons.calendar_month_rounded, label: 'Timetable'),
    (icon: Icons.summarize_rounded, label: 'Reports'),
    (icon: Icons.campaign_rounded, label: 'Announce'),
    (icon: Icons.person_rounded, label: 'Profile'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Same reasoning as the student shell: a running session is the most
    // time-sensitive fact here, and without this a lecturer who left a
    // session running and moved to another tab had no signal it was still
    // live. The select() keeps the shell from rebuilding on every dashboard
    // poll -- it only rebuilds when this flips between zero and non-zero.
    final hasLiveSession = ref.watch(
      lecturerDashboardProvider.select(
        (state) => (state.data?.stats.activeSessions ?? 0) > 0,
      ),
    );

    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: AppBottomNav(
        items: [
          for (final item in _nav)
            AppBottomNavItem(
              icon: item.icon,
              label: item.label,
              // A running session is the case a lecturer most needs to be
              // able to see at a glance, so the dot goes on Sessions rather
              // than Home.
              showDot: item.label == 'Sessions' && hasLiveSession,
            ),
        ],
        currentIndex: navigationShell.currentIndex,
        onTap: (index) => navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        ),
      ),
    );
  }
}
