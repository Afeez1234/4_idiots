import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/providers/theme_provider.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/lecturer_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';
import '../models/lecturer_dashboard_model.dart';

class LecturerDashboardScreen extends ConsumerWidget {
  const LecturerDashboardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerDashboardProvider);

    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
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
          // Same background pattern as student_dashboard_screen.dart --
          // RepaintBoundary isolates the static gradient/grid from
          // whatever's rebuilding on top of it.
          RepaintBoundary(
            child: _DashboardBackground(
              isDarkMode: isDarkMode,
              colorScheme: colorScheme,
            ),
          ),
          SafeArea(
            child: RefreshIndicator(
              onRefresh: () => ref.read(lecturerDashboardProvider.notifier).loadDashboardData(),
              child: SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
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

                    _StatsGrid(stats: data.stats, colorScheme: colorScheme),
                    const SizedBox(height: 32),

                    const Text(
                      'YOUR COURSES',
                      style: TextStyle(
                        fontSize: 10,
                        letterSpacing: 1.5,
                        color: Colors.grey,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 16),

                    if (data.courses.isEmpty)
                      const Text(
                        'No courses assigned yet.',
                        style: TextStyle(color: Colors.grey),
                      )
                    else
                      ...data.courses.map(
                        (course) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _CourseCard(
                            course: course,
                            colorScheme: colorScheme,
                            onTap: () => context.push('/lecturer/course/${course.id}'),
                          ),
                        ),
                      ),
                    const SizedBox(height: 32),
                  ],
                ),
              ),
            ),
          ),
        ],
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
          child: Container(decoration: BoxDecoration(color: colorScheme.surface)),
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
              painter: isDarkMode
                  ? const GridOverlayPainter(color: Colors.white)
                  : const GridOverlayPainter(color: Colors.black),
            ),
          ),
        ),
      ],
    );
  }
}

class _DashboardHeader extends ConsumerWidget {
  final LecturerProfile profile;
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
        title: const Text('Sign Out', style: TextStyle(fontWeight: FontWeight.bold)),
        content: const Text('Are you sure you want to log out of your session?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('CANCEL', style: TextStyle(color: colorScheme.onSurface)),
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
    final fallbackName = displayName.isNotEmpty ? displayName : 'Unknown Lecturer';
    final avatarLetter = displayName.isNotEmpty ? displayName[0].toUpperCase() : 'L';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'LECTURER PORTAL',
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
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              if (profile.department != null)
                Text(
                  profile.department!,
                  style: TextStyle(fontSize: 12, color: colorScheme.onSurface.withValues(alpha: 0.5)),
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
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  side: BorderSide(color: colorScheme.outline.withValues(alpha: 0.15)),
                ),
                icon: Icon(
                  isDarkMode ? Icons.light_mode_rounded : Icons.dark_mode_rounded,
                  color: colorScheme.primary,
                  size: 20,
                ),
                tooltip: isDarkMode ? 'Switch to light mode' : 'Switch to dark mode',
              ),
              const SizedBox(width: 8),
              GestureDetector(
                onTap: () => _showLogoutDialog(context, ref),
                child: CircleAvatar(
                  radius: 18,
                  backgroundColor: colorScheme.surfaceContainer,
                  child: Text(
                    avatarLetter,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
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

class _StatsGrid extends StatelessWidget {
  final LecturerStats stats;
  final ColorScheme colorScheme;

  const _StatsGrid({required this.stats, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _StatBox(val: '${stats.totalCourses}', label: 'COURSES', colorScheme: colorScheme),
        const SizedBox(width: 12),
        _StatBox(val: '${stats.activeSessions}', label: 'LIVE NOW', colorScheme: colorScheme, highlight: stats.activeSessions > 0),
        const SizedBox(width: 12),
        _StatBox(val: '${stats.todayCheckins}', label: 'CHECK-INS TODAY', colorScheme: colorScheme),
      ],
    );
  }
}

class _StatBox extends StatelessWidget {
  final String val;
  final String label;
  final ColorScheme colorScheme;
  final bool highlight;

  const _StatBox({
    required this.val,
    required this.label,
    required this.colorScheme,
    this.highlight = false,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 16),
        decoration: BoxDecoration(
          color: highlight
              ? const Color(0xFF10B981).withValues(alpha: 0.12)
              : colorScheme.surfaceContainer.withValues(alpha: 0.78),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: highlight
                ? const Color(0xFF10B981).withValues(alpha: 0.35)
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
                color: highlight ? const Color(0xFF10B981) : colorScheme.onSurface,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              label,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 8,
                letterSpacing: 1,
                fontWeight: FontWeight.bold,
                color: highlight
                    ? const Color(0xFF10B981).withValues(alpha: 0.9)
                    : colorScheme.onSurface.withValues(alpha: 0.55),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CourseCard extends StatelessWidget {
  final LecturerCourse course;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _CourseCard({
    required this.course,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: course.hasActiveSession
                ? const Color(0xFF10B981).withValues(alpha: 0.35)
                : colorScheme.outline.withValues(alpha: 0.1),
          ),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          course.title,
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      if (course.hasActiveSession) ...[
                        const SizedBox(width: 6),
                        Container(
                          width: 6,
                          height: 6,
                          decoration: const BoxDecoration(
                            color: Color(0xFF10B981),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${course.code} · ${course.enrolledCount} enrolled · ${course.avgAttendance}% avg',
                    style: TextStyle(
                      fontSize: 10,
                      fontFamily: 'JetBrains Mono',
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: colorScheme.onSurface.withValues(alpha: 0.3),
            ),
          ],
        ),
      ),
    );
  }
}
