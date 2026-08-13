import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../core/providers/theme_provider.dart';
import '../../../shared/widgets/dashboard_background.dart';
import '../../auth/providers/auth_provider.dart';
import '../providers/student_provider.dart';
import '../providers/today_schedule_provider.dart';
import '../models/student_dashboard_model.dart';
import '../models/today_protocol_entry.dart';
import 'views/nfc_broadcast_sheet.dart';

// The Home tab of the student bottom nav. This used to be one of four
// manually-switched bodies inside StudentDashboardScreen (see git history);
// that screen has been split up so each bottom-nav tab is a real routed
// screen with its own back-stack (see student_shell_screen.dart +
// app_router.dart). This file keeps only the original "Home" body --
// header, next-session card, stats grid, today's protocol list.
class StudentHomeScreen extends ConsumerWidget {
  const StudentHomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);

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
          RepaintBoundary(
            child: DashboardBackground(
              isDarkMode: isDarkMode,
              colorScheme: colorScheme,
            ),
          ),
          SafeArea(
            child: SingleChildScrollView(
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

                  _NextSessionCard(colorScheme: colorScheme),
                  const SizedBox(height: 20),

                  _StatsGrid(stats: data.stats, colorScheme: colorScheme),
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

                  _ProtocolList(colorScheme: colorScheme),
                  const SizedBox(height: 32),
                ],
              ),
            ),
          ),
        ],
      ),
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

class _NextSessionCard extends ConsumerWidget {
  final ColorScheme colorScheme;

  const _NextSessionCard({required this.colorScheme});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheduleState = ref.watch(todayScheduleProvider);

    TodayProtocolEntry? nextSession;
    for (final entry in scheduleState.entries) {
      if (entry.status == 'PENDING') {
        nextSession = entry;
        break;
      }
    }

    final subtitle = scheduleState.isLoading
        ? 'LOADING TODAY\'S SCHEDULE...'
        : nextSession != null
        ? 'NEXT SESSION TODAY'
        : 'NO UPCOMING SESSIONS';

    final title = nextSession?.courseName ?? 'No Upcoming Sessions';

    final hasTimeRange =
        nextSession?.startTime != null && nextSession?.endTime != null;
    final timeRange = hasTimeRange
        ? '${nextSession!.startTime} - ${nextSession.endTime}'
              '${nextSession.room != null ? ' · ${nextSession.room}' : ''}'
        : null;

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
          Text(
            subtitle,
            style: const TextStyle(
              fontSize: 10,
              letterSpacing: 1.5,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            title,
            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          ),
          if (timeRange != null) ...[
            const SizedBox(height: 4),
            Text(
              timeRange,
              style: TextStyle(
                fontSize: 11,
                fontFamily: 'JetBrains Mono',
                color: colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
          ],
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

            onPressed: () => NfcBroadcastSheet.show(context),
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

class _ProtocolList extends ConsumerWidget {
  final ColorScheme colorScheme;

  const _ProtocolList({required this.colorScheme});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheduleState = ref.watch(todayScheduleProvider);

    if (scheduleState.isLoading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(
          child: SizedBox(
            width: 20,
            height: 20,
            child: CircularProgressIndicator(strokeWidth: 2),
          ),
        ),
      );
    }

    if (scheduleState.errorMessage != null) {
      return Text(
        'Could not load today\'s schedule.',
        style: TextStyle(color: colorScheme.error, fontSize: 12),
      );
    }

    if (scheduleState.entries.isEmpty) {
      return const Text(
        'No protocols scheduled for today.',
        style: TextStyle(color: Colors.grey),
      );
    }

    return Column(
      children: scheduleState.entries.map((entry) {
        final timeRange = (entry.startTime != null && entry.endTime != null)
            ? '${entry.startTime} - ${entry.endTime}'
            : '--:-- - --:--';

        return _ProtocolCard(
          courseId: entry.courseId,
          title: entry.courseName,
          time: timeRange,
          status: entry.status,
          colorScheme: colorScheme,
        );
      }).toList(),
    );
  }
}

class _ProtocolCard extends StatelessWidget {
  final int courseId;
  final String title;
  final String time;
  final String status;
  final ColorScheme colorScheme;

  const _ProtocolCard({
    required this.courseId,
    required this.title,
    required this.time,
    required this.status,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final isPresent = status == 'PRESENT';
    final isAbsent = status == 'ABSENT';

    final Color statusColor;
    final Color bgColor;
    final Color borderColor;
    if (isPresent) {
      statusColor = const Color(0xFF10B981);
      bgColor = const Color(0xFF10B981).withValues(alpha: 0.1);
      borderColor = const Color(0xFF10B981).withValues(alpha: 0.3);
    } else if (isAbsent) {
      statusColor = const Color(0xFFEF4444);
      bgColor = const Color(0xFFEF4444).withValues(alpha: 0.1);
      borderColor = const Color(0xFFEF4444).withValues(alpha: 0.3);
    } else {
      statusColor = colorScheme.onSurface.withValues(alpha: 0.5);
      bgColor = colorScheme.surface.withValues(alpha: 0.45);
      borderColor = colorScheme.outline.withValues(alpha: 0.1);
    }

    return InkWell(
      // Tapping a course's today-entry opens the Home-tab course detail
      // screen (see the "Course detail (tap a course)" node under Home in
      // the navigation map), pushed within this tab's own stack.
      onTap: () => context.push('/student/home/course/$courseId'),
      borderRadius: BorderRadius.circular(12),
      child: Container(
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
                  if (isPresent || isAbsent) ...[
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
      ),
    );
  }
}
