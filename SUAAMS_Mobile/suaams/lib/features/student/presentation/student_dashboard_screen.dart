import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../core/providers/theme_provider.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/student_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';
import '../models/student_dashboard_model.dart';
import 'views/profile_view_screen.dart'; 
import 'views/courses_view.dart'; // <-- Ensure this points to your new file

// Bottom tab selection state for the dashboard navigation bar.
final selectedDashboardTabProvider =
    NotifierProvider<SelectedDashboardTabNotifier, int>(
      SelectedDashboardTabNotifier.new,
    );

class SelectedDashboardTabNotifier extends Notifier<int> {
  @override
  int build() {
    return 0;
  }

  void setTab(int tabIndex) {
    state = tabIndex;
  }
}

class StudentDashboardScreen extends ConsumerWidget {
  const StudentDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final selectedTab = ref.watch(selectedDashboardTabProvider);

    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          _DashboardBackground(
            isDarkMode: isDarkMode,
            colorScheme: colorScheme,
          ),
          SafeArea(
            child: SizedBox.expand(
              // Using a Builder makes routing between tabs incredibly clean!
              child: Builder(
                builder: (context) {
                  // Tab 1: COURSES
                  if (selectedTab == 1) {
                    return const CoursesView();
                  }
                  
                  // Tab 3: PROFILE
                  if (selectedTab == 3) {
                    return const ProfileView();
                  }

                  // Tab 2 (RECORDS) is not built yet
                  if (selectedTab != 0) {
                    return const Center(
                      child: Text(
                        'MODULE UNDER CONSTRUCTION',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2,
                        ),
                      ),
                    );
                  }

                  // Tab 0: HOME (Default)
                  return SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _DashboardHeader(
                          profile: data.profile,
                          colorScheme: colorScheme,
                          isDarkMode: isDarkMode,
                        ),
                        const SizedBox(height: 32),

                        _NextSessionCard(
                          course: data.courses.isNotEmpty
                              ? data.courses.first
                              : null,
                          colorScheme: colorScheme,
                        ),
                        const SizedBox(height: 20),

                        _StatsGrid(
                          stats: data.stats,
                          colorScheme: colorScheme,
                        ),
                        const SizedBox(height: 32),

                        const Text(
                          'TODAY\'S PROTOCOL',
                          style: TextStyle(
                            fontSize: 10,
                            letterSpacing: 1.5,
                            color: Colors.grey,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        const SizedBox(height: 16),

                        _ProtocolList(
                          courses: data.courses,
                          colorScheme: colorScheme,
                        ),
                        const SizedBox(height: 120), // Bottom padding
                      ],
                    ),
                  );
                },
              ),
            ),
          ),
        ],
      ),
      bottomNavigationBar: _DashboardBottomNav(
        selectedTab: selectedTab,
        colorScheme: colorScheme,
      ),
    );
  }
}

class _DashboardBackground extends StatelessWidget {
  final bool isDarkMode;
  final ColorScheme colorScheme;

  const _DashboardBackground({
    required this.isDarkMode,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Positioned.fill(
          child: Container(
            decoration: BoxDecoration(color: colorScheme.surface),
          ),
        ),
        Positioned(
          top: -55,
          right: -45,
          child: Container(
            width: 170,
            height: 170,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF0A0A14).withValues(alpha: 0.6)
                  : const Color(0xFFE0E7FF).withValues(alpha: 0.75),
            ),
          ),
        ),
        Positioned(
          bottom: -35,
          left: -25,
          child: Container(
            width: 130,
            height: 130,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF080810).withValues(alpha: 0.65)
                  : const Color(0xFFFEF3C7).withValues(alpha: 0.55),
            ),
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              painter: GridOverlayPainter(
                color: isDarkMode ? Colors.white : Colors.black,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _DashboardHeader extends ConsumerWidget {
  final StudentProfile profile;
  final ColorScheme colorScheme;
  final bool isDarkMode;

  const _DashboardHeader({
    required this.profile,
    required this.colorScheme,
    required this.isDarkMode,
  });

  void _showLogoutDialog(BuildContext context, WidgetRef ref) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainer,
        title: const Text(
          'Sign Out',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        content: const Text(
          'Are you sure you want to log out of your session?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'CANCEL',
              style: TextStyle(color: colorScheme.onSurface),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: colorScheme.error,
              foregroundColor: colorScheme.onError,
            ),
            onPressed: () {
              Navigator.pop(context);
              ref.read(authProvider.notifier).logout();
            },
            child: const Text('SIGN OUT'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final displayName = profile.fullName.trim();
    final fallbackName = displayName.isNotEmpty
        ? displayName
        : 'Unknown Student';
    final avatarLetter = displayName.isNotEmpty
        ? displayName[0].toUpperCase()
        : 'S';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'WELCOME BACK',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 2,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                fallbackName,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconButton(
                onPressed: () => ref.read(themeProvider.notifier).toggleTheme(),
                style: IconButton.styleFrom(
                  backgroundColor: colorScheme.surfaceContainer,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  side: BorderSide(
                    color: colorScheme.outline.withValues(alpha: 0.15),
                  ),
                ),
                icon: Icon(
                  isDarkMode
                      ? Icons.light_mode_rounded
                      : Icons.dark_mode_rounded,
                  color: colorScheme.primary,
                  size: 20,
                ),
                tooltip: isDarkMode
                    ? 'Switch to light mode'
                    : 'Switch to dark mode',
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () => _showLogoutDialog(context, ref),
                child: CircleAvatar(
                  radius: 18,
                  backgroundColor: colorScheme.surfaceContainer,
                  child: Text(
                    avatarLetter,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _NextSessionCard extends StatelessWidget {
  final CourseBreakdown? course;
  final ColorScheme colorScheme;

  const _NextSessionCard({this.course, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border(left: BorderSide(color: colorScheme.primary, width: 4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'NEXT SESSION IN 15 MIN',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 1.5,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            course?.name ?? 'No Upcoming Sessions',
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          const SizedBox(height: 20),
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
            onPressed: () {},
            child: const Text(
              'INITIATE SCAN',
              style: TextStyle(letterSpacing: 2, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
    );
  }
}

class _StatsGrid extends StatelessWidget {
  final DashboardStats stats;
  final ColorScheme colorScheme;

  const _StatsGrid({required this.stats, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _StatBox(
          val: '${stats.overallRate}%',
          label: 'OVERALL',
          colorScheme: colorScheme,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${stats.attendanceCount}',
          label: 'SESSIONS',
          colorScheme: colorScheme,
        ),
        const SizedBox(width: 12),
        _StatBox(
          val: '${stats.atRiskCount}',
          label: 'MISSED',
          colorScheme: colorScheme,
        ),
      ],
    );
  }
}

class _StatBox extends StatelessWidget {
  final String val;
  final String label;
  final ColorScheme colorScheme;

  const _StatBox({
    required this.val,
    required this.label,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final isWarning = label == 'MISSED';

    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: isWarning
              ? colorScheme.errorContainer.withValues(alpha: 0.12)
              : colorScheme.surfaceContainer.withValues(alpha: 0.78),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: isWarning
                ? colorScheme.error.withValues(alpha: 0.35)
                : colorScheme.outline.withValues(alpha: 0.14),
          ),
        ),
        child: Column(
          children: [
            Text(
              val,
              style: TextStyle(
                fontWeight: FontWeight.bold,
                fontSize: 18,
                color: isWarning ? colorScheme.error : colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 8,
                letterSpacing: 1,
                fontWeight: FontWeight.bold,
                color: isWarning
                    ? colorScheme.error.withValues(alpha: 0.9)
                    : colorScheme.onSurface.withValues(alpha: 0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ProtocolList extends StatelessWidget {
  final List<CourseBreakdown> courses;
  final ColorScheme colorScheme;

  const _ProtocolList({required this.courses, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    if (courses.isEmpty) {
      return const Text(
        'No protocols scheduled for today.',
        style: TextStyle(color: Colors.grey),
      );
    }

    return Column(
      children: courses.asMap().entries.map((entry) {
        final index = entry.key;
        final course = entry.value;
        // Mocking dynamic status for the UI preview
        final status = index == 0 ? 'PENDING' : 'PRESENT';
        // TODO: Replace with real session times from today's schedule API
        final time = index == 0 ? '10:00 AM - 12:00 PM' : '08:00 AM - 09:30 AM';

        return _ProtocolCard(
          title: course.name,
          time: time,
          status: status,
          colorScheme: colorScheme,
        );
      }).toList(),
    );
  }
}

class _ProtocolCard extends StatelessWidget {
  final String title;
  final String time;
  final String status;
  final ColorScheme colorScheme;

  const _ProtocolCard({
    required this.title,
    required this.time,
    required this.status,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final isPresent = status == 'PRESENT';

    final statusColor = isPresent
        ? const Color(0xFF10B981)
        : colorScheme.onSurface.withValues(alpha: 0.5);
    final bgColor = isPresent
        ? const Color(0xFF10B981).withValues(alpha: 0.1)
        : colorScheme.surface.withValues(alpha: 0.45);
    final borderColor = isPresent
        ? const Color(0xFF10B981).withValues(alpha: 0.3)
        : colorScheme.outline.withValues(alpha: 0.1);

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: borderColor),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  time,
                  style: const TextStyle(
                    fontSize: 10,
                    color: Colors.grey,
                    fontFamily: 'JetBrains Mono',
                  ),
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
            decoration: BoxDecoration(
              color: bgColor,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: borderColor),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (isPresent) ...[
                  Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(
                      color: statusColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 6),
                ],
                Text(
                  status.toUpperCase(),
                  style: TextStyle(
                    fontSize: 8,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1,
                    color: statusColor,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DashboardBottomNav extends ConsumerWidget {
  final int selectedTab;
  final ColorScheme colorScheme;

  const _DashboardBottomNav({
    required this.selectedTab,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: colorScheme.surface,
          border: Border(
            top: BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _BottomNavItem(
              icon: Icons.grid_view_rounded,
              label: 'HOME',
              active: selectedTab == 0,
              colorScheme: colorScheme,
              onTap: () =>
                  ref.read(selectedDashboardTabProvider.notifier).setTab(0),
            ),
            _BottomNavItem(
              icon: Icons.description_rounded,
              label: 'COURSES',
              active: selectedTab == 1,
              colorScheme: colorScheme,
              onTap: () =>
                  ref.read(selectedDashboardTabProvider.notifier).setTab(1),
            ),
            _BottomNavItem(
              icon: Icons.fact_check_rounded,
              label: 'RECORDS',
              active: selectedTab == 2,
              colorScheme: colorScheme,
              onTap: () =>
                  ref.read(selectedDashboardTabProvider.notifier).setTab(2),
            ),
            _BottomNavItem(
              icon: Icons.person_rounded,
              label: 'PROFILE',
              active: selectedTab == 3,
              colorScheme: colorScheme,
              onTap: () =>
                  ref.read(selectedDashboardTabProvider.notifier).setTab(3),
            ),
          ],
        ),
      ),
    );
  }
}

class _BottomNavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final bool active;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _BottomNavItem({
    required this.icon,
    required this.label,
    required this.active,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: active
              ? colorScheme.primary.withValues(alpha: 0.05)
              : Colors.transparent,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              icon,
              size: 20,
              color: active
                  ? colorScheme.primary
                  : colorScheme.onSurface.withValues(alpha: 0.45),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              style: TextStyle(
                fontSize: 8,
                fontWeight: FontWeight.bold,
                color: active
                    ? colorScheme.primary
                    : colorScheme.onSurface.withValues(alpha: 0.45),
                letterSpacing: 1,
              ),
            ),
          ],
        ),
      ),
    );
  }
}