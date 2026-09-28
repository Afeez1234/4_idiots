import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:suaams/features/student/providers/today_schedule_provider.dart';
import 'package:suaams/shared/widgets/app_bottom_nav.dart';

// Hosts the 5-tab student bottom nav (Home, Timetable, Attendance, ID Card,
// Profile). One StatefulShellBranch per tab in app_router.dart, each with
// its own Navigator stack -- so pushing e.g. a course detail screen from
// Home doesn't disturb Attendance's stack, and switching tabs keeps each
// one's scroll position/back-stack intact.
//
// This is a Consumer rather than a StatelessWidget only so the Home tab
// can carry a "session live" dot. See the select() note in build.
class StudentShellScreen extends ConsumerWidget {
  final StatefulNavigationShell navigationShell;

  const StudentShellScreen({super.key, required this.navigationShell});

  // "RECORDS" rather than "ATTENDANCE": this is the longest string in the
  // bar, and with five tabs on a 360dp phone it was setting the width of
  // every tile. Shortening it buys back more room than any font or
  // spacing change could.
  //
  // Kept as a template rather than a const list because the Home badge is
  // computed per-build.
  static const _nav = <({IconData icon, String label})>[
    (icon: Icons.grid_view_rounded, label: 'Home'),
    (icon: Icons.calendar_month_rounded, label: 'Timetable'),
    (icon: Icons.fact_check_rounded, label: 'Records'),
    (icon: Icons.badge_rounded, label: 'ID Card'),
    (icon: Icons.person_rounded, label: 'Profile'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // A live session is the single most time-sensitive fact in the app, and
    // until now it was only visible on the Home tab itself -- start a class
    // from four tabs away and nothing told you.
    //
    // The select() is load-bearing. todayScheduleProvider re-emits on every
    // 30-second poll whether or not anything changed, so a plain ref.watch
    // here would rebuild this whole shell -- and with it every tab's bottom
    // bar -- twice a minute for no reason. Selecting down to a single bool
    // means the shell only rebuilds when live-ness actually flips.
    final hasLiveSession = ref.watch(
      todayScheduleProvider.select(
        (state) => state.entries.any((entry) => entry.sessionLive),
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
              // Dot rather than a count: "something is live" is a boolean,
              // and a "1" would imply a quantity that doesn't exist -- and
              // would paint it in the error red reserved for failures.
              showDot: item.label == 'Home' && hasLiveSession,
            ),
        ],
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
