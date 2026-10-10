import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/shared/widgets/app_skeleton.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';

// First-load placeholder for the Attendance tab: the heading and three
// cards shaped like _buildCourseCard (code badge + percentage, course name,
// ATTENDANCE / sessions line, progress bar), with the same padding and
// gaps so nothing moves when the real cards arrive.
class _CoursesSkeleton extends StatelessWidget {
  const _CoursesSkeleton();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      physics: const NeverScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      child: SkeletonPulse(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SkeletonBox(width: 140, height: 10),
            const SizedBox(height: 16),
            for (var i = 0; i < 3; i++)
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.all(20),
                decoration: BoxDecoration(
                  color: colorScheme.surfaceContainer,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: colorScheme.outline.withValues(alpha: 0.15),
                  ),
                ),
                child: const Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        SkeletonBox(width: 72, height: 24),
                        SkeletonBox(width: 48, height: 20),
                      ],
                    ),
                    SizedBox(height: 16),
                    FractionallySizedBox(
                      widthFactor: 0.7,
                      child: SkeletonBox(height: 16),
                    ),
                    SizedBox(height: 16),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        SkeletonBox(width: 80, height: 10),
                        SkeletonBox(width: 90, height: 10),
                      ],
                    ),
                    SizedBox(height: 8),
                    SkeletonBox(width: double.infinity, height: 6, radius: 3),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class CoursesView extends ConsumerWidget {
  const CoursesView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final data = state.data;
    // Was an empty SizedBox for both loading and a failed load, so the
    // Attendance tab could sit blank with no way to retry. Same fix as
    // records_view.dart.
    if (data == null) {
      if (state.errorMessage == null) return const _CoursesSkeleton();
      return AppStateView(
        kind: AppStateKind.error,
        icon: Icons.school_rounded,
        title: "Couldn't load your courses",
        message: isGenericServerMessage(state.errorMessage)
            ? 'Check your connection and try again.'
            : state.errorMessage,
        onRetry: () =>
            ref.read(studentDashboardProvider.notifier).loadDashboardData(),
      );
    }

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'ACADEMIC MODULES',
            style: AppTheme.eyebrow(
              colorScheme.onSurface.withValues(alpha: 0.6),
            ),
          ),
          const SizedBox(height: 16),

          // Map through the actual courses from the backend
          ...data.courses.map(
            (course) =>
                _buildCourseCard(context, course, colorScheme, isDarkMode),
          ),

          const SizedBox(height: 120), // Padding for the bottom navigation bar
        ],
      ),
    );
  }

  Widget _buildCourseCard(
    BuildContext context,
    CourseBreakdown course,
    ColorScheme colorScheme,
    bool isDarkMode,
  ) {
    // Two colours, not one. `healthColor` paints the progress bar and
    // chips, where the saturated hue is correct. `healthText` renders the
    // percentage, where the raw hue fails: emerald measures 2.54:1 and
    // amber 2.15:1 on a white card, against a 3:1 floor for 18px bold.
    // Dark mode was fine in both, which is why it wasn't obvious.
    final palette = terminalOf(context);
    late final Color healthColor;
    late final Color healthText;
    if (course.pct >= 75) {
      healthColor = AppStatus.success;
      healthText = palette.successText;
    } else if (course.pct >= 50) {
      healthColor = AppStatus.warning;
      healthText = palette.warningText;
    } else {
      healthColor = AppStatus.danger;
      healthText = palette.dangerText;
    }

    return InkWell(
      // Tapping a course here opens the attendance-specific course detail
      // (see the "Course attendance detail (tap a course)" node under
      // Attendance in the navigation map) -- distinct from the general
      // course detail reachable from Home.
      onTap: () => context.push('/student/attendance/course/${course.id}'),
      borderRadius: BorderRadius.circular(16),
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: colorScheme.outline.withValues(alpha: 0.15),
            width: 1,
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Course Code Badge
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 4,
                  ),
                  decoration: BoxDecoration(
                    color: colorScheme.surface,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: colorScheme.outline.withValues(alpha: 0.1),
                    ),
                  ),
                  child: Text(
                    course.code,
                    style: AppTheme.accent(size: 12, weight: FontWeight.w700),
                  ),
                ),
                // Percentage Text
                Text(
                  '${course.pct}%',
                  style: AppTheme.accent(
                    size: 18,
                    weight: FontWeight.w700,
                    color: healthText,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),

            // Course Name
            Text(
              course.name,
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),

            // Progress Details
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'ATTENDANCE',
                  style: TextStyle(
                    fontSize: 11,
                    letterSpacing: 1.5,
                    fontWeight: FontWeight.bold,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
                Text(
                  '${course.attended} / ${course.total} SESSIONS',
                  style: AppTheme.accent(
                    size: 10,
                    weight: FontWeight.w700,
                    color: colorScheme.onSurface.withValues(alpha: 0.7),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Terminal-style Progress Bar
            Container(
              height: 6,
              width: double.infinity,
              decoration: BoxDecoration(
                color: colorScheme.surface,
                borderRadius: BorderRadius.circular(3),
                border: Border.all(
                  color: colorScheme.outline.withValues(alpha: 0.1),
                ),
              ),
              child: LayoutBuilder(
                builder: (context, constraints) {
                  return Align(
                    alignment: Alignment.centerLeft,
                    child: Container(
                      width:
                          constraints.maxWidth *
                          (course.pct / 100).clamp(0.0, 1.0),
                      decoration: BoxDecoration(
                        color: healthColor,
                        borderRadius: BorderRadius.circular(3),
                        boxShadow: [
                          BoxShadow(
                            color: healthColor.withValues(alpha: 0.3),
                            blurRadius: 4,
                            offset: const Offset(0, 2),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
