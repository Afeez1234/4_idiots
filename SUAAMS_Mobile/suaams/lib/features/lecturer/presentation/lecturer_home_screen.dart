import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/dashboard_background.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';
import 'package:suaams/features/lecturer/models/lecturer_dashboard_model.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/shared/widgets/confirm_dialog.dart';
import 'package:suaams/shared/utils/attendance_status.dart';

// Home tab of the lecturer bottom nav. Was LecturerDashboardScreen, the
// only screen on the lecturer side before this redesign -- renamed since
// it's now specifically the Home tab (Sessions/Reports/Announce/Profile are
// new sibling tabs). Content and logic are unchanged; only the course-tap
// destination path changed to live under the Home branch
// (see student_shell_screen.dart's sibling comment for why
// StatefulShellRoute is used here).
class LecturerHomeScreen extends ConsumerWidget {
  const LecturerHomeScreen({super.key});

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
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title: 'Couldn''t load your dashboard',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () =>
              ref.read(lecturerDashboardProvider.notifier).loadDashboardData(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          RepaintBoundary(
            child: DashboardBackground(
              isDarkMode: isDarkMode,
              colorScheme: colorScheme,
            ),
          ),
          SafeArea(
            child: RefreshIndicator(
              onRefresh: () => ref
                  .read(lecturerDashboardProvider.notifier)
                  .loadDashboardData(),
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
                    ),
                    const SizedBox(height: 32),

                    _StatsGrid(stats: data.stats),
                    const SizedBox(height: 32),

                    Text(
                      'YOUR COURSES',
                      style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
                    ),
                    const SizedBox(height: 16),

                    if (data.courses.isEmpty)
                      AppStateView(
                        kind: AppStateKind.empty,
                        icon: Icons.school_rounded,
                        title: 'No courses assigned yet',
                        message:
                            'Courses appear here once the HOD assigns them to you.',
                        compact: true,
                      )
                    else
                      ...data.courses.map(
                        (course) => Padding(
                          padding: const EdgeInsets.only(bottom: 12),
                          child: _CourseCard(
                            course: course,
                            colorScheme: colorScheme,
                            onTap: () => context.push(
                              '/lecturer/home/course/${course.id}',
                            ),
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

class _DashboardHeader extends ConsumerWidget {
  final LecturerProfile profile;
  final ColorScheme colorScheme;

  const _DashboardHeader({
    required this.profile,
    required this.colorScheme,
  });

  Future<void> _showLogoutDialog(BuildContext context, WidgetRef ref) async {
    // One of four hand-rolled copies of this dialog; see
    // student_home_screen.dart's version for why they were consolidated.
    final confirmed = await showConfirmDialog(
      context,
      title: 'Log Out',
      message: 'Are you sure you want to log out of your account?',
      confirmLabel: 'LOG OUT',
      destructive: true,
    );
    if (confirmed) {
      await ref.read(authProvider.notifier).logout();
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final displayName = profile.fullName.trim();
    final fallbackName = displayName.isNotEmpty
        ? displayName
        : 'Unknown Lecturer';
    final avatarLetter = displayName.isNotEmpty
        ? displayName[0].toUpperCase()
        : 'L';

    return Row(
      // top-aligned: the name wraps to two lines, and centring would leave
      // a short name floating mid-height against a tall column.
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'LECTURER PORTAL',
                style: AppTheme.eyebrow(
                  colorScheme.onSurface.withValues(alpha: 0.55),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                fallbackName,
                // Same reasoning as the student header: a lecturer name is
                // just as long, and ellipsising the subject of the screen
                // is worse than letting the header grow a line.
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
              if (profile.department != null)
                Text(
                  profile.department!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        // Theme toggle removed for the same reason as the student header --
        // lecturer_profile_screen.dart already has it. The 48px goes to the
        // name instead.
        // Only the avatar is left here now that the theme toggle moved out
        // to the profile screen. The FittedBox stays as a guard: it keeps
        // the avatar from overflowing on a very narrow phone or at a large
        // system text scale, which is exactly the failure mode it was
        // introduced to prevent.
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // See student_home_screen.dart's equivalent: CircleAvatar
              // derives its text colour as onPrimary (1.23:1 dark, 1.00:1
              // light against surfaceContainer), and the 36px circle is
              // too small a target for a destructive action.
              SizedBox(
                width: 48,
                height: 48,
                child: Material(
                  color: colorScheme.surfaceContainer,
                  shape: const CircleBorder(),
                  clipBehavior: Clip.antiAlias,
                  child: InkWell(
                    onTap: () => _showLogoutDialog(context, ref),
                    child: Center(
                      child: Text(
                        avatarLetter,
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 13,
                          color: colorScheme.onSurface,
                        ),
                      ),
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

class _StatsGrid extends StatelessWidget {
  final LecturerStats stats;

  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return AppStatRow([
      AppStatValue('${stats.totalCourses}', 'COURSES'),
      // Green only while a session is genuinely live. The old copy took a
      // `highlight: stats.activeSessions > 0` bool, so the tone is chosen
      // at the call site rather than baked in.
      stats.activeSessions > 0
          ? AppStatValue.success('${stats.activeSessions}', 'LIVE NOW')
          : AppStatValue('${stats.activeSessions}', 'LIVE NOW'),
      AppStatValue('${stats.todayCheckins}', 'CHECK-INS TODAY'),
    ]);
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
                ? AppStatus.success.withValues(alpha: 0.35)
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
                          style: const TextStyle(
                            fontWeight: FontWeight.bold,
                            fontSize: 15,
                          ),
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
                            color: AppStatus.success,
                            shape: BoxShape.circle,
                          ),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${course.code} · ${course.enrolledCount} enrolled · ${course.avgAttendance}% avg',
                    style: AppTheme.accent(size: 10, color: colorScheme.onSurface.withValues(alpha: 0.5)),
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