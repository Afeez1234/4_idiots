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
//
// Stateful purely to observe app lifecycle. Today's protocol is polled
// every 30s, but the OS suspends timers in the background, so the first
// frame back after a long background can be arbitrarily stale -- a student
// who left the app open through a class wouldn't see the check-in card go
// live until they pulled to refresh. Refetching on resume closes that gap.
class StudentHomeScreen extends ConsumerStatefulWidget {
  const StudentHomeScreen({super.key});

  @override
  ConsumerState<StudentHomeScreen> createState() => _StudentHomeScreenState();
}

class _StudentHomeScreenState extends ConsumerState<StudentHomeScreen>
    with WidgetsBindingObserver {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    // Must remove the observer as well as dropping the widget: the binding
    // outlives this State, so a leftover registration would keep calling
    // into a disposed element and throw on the next resume.
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    // AutoDispose means the poll timer is cancelled once this tab's
    // listeners go away, so on resume there may be no timer left to fire
    // one. refreshTodaySchedule() restarts it and fetches immediately.
    ref.read(todayScheduleProvider.notifier).refreshTodaySchedule();
  }

  @override
  Widget build(BuildContext context) {
    final ref = this.ref;
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
              IconButton(
                onPressed: () => context.push('/student/home/announcements'),
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
                  Icons.campaign_rounded,
                  color: colorScheme.primary,
                  size: 20,
                ),
                tooltip: 'Announcements',
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

// The dashboard's primary call to action: tap to check in.
//
// This is a StatefulWidget purely to hold the press-down flag that drives
// the scale animation. It watches todayScheduleProvider for the live
// session, but the session lookup itself is unchanged from the previous
// ConsumerWidget version.
//
// Three states, distinguished by `sessionLive` rather than by `status`:
//   - sessionLive -- a lecturer has the session running and this student
//     hasn't checked in, so a check-in would succeed. The whole card
//     becomes the tap target.
//   - Scheduled -- the course is on today's timetable but no Session row
//     exists yet, so a check-in would be rejected. Inert, but still shows
//     the course and its start time, so the card stays informative during
//     the (much longer) part of the day when nothing is running.
//   - Nothing at all on today's timetable. Inert and blank.
//
// The previous version armed the tap target on any PENDING entry. Since
// PENDING is also the backend's default for "no session exists", that
// meant a student could burn a biometric prompt (and a radio window) on a
// check-in guaranteed to fail server-side -- and the card would claim the
// session was live when it wasn't.
class _NextSessionCard extends ConsumerStatefulWidget {
  final ColorScheme colorScheme;

  const _NextSessionCard({required this.colorScheme});

  @override
  ConsumerState<_NextSessionCard> createState() => _NextSessionCardState();
}

class _NextSessionCardState extends ConsumerState<_NextSessionCard> {
  // Drives the press-down scale. Deliberately a plain bool + AnimatedScale
  // rather than an explicit AnimationController: this is a 120ms tap
  // reaction, so the built-in implicit animation is enough and avoids
  // holding a Ticker alive in the tree.
  bool _isPressed = false;

  void _setPressed(bool value) {
    // Guarded because the tap-down/up pair can straddle a rebuild (the
    // schedule polls and this card is above it in the tree).
    if (_isPressed == value) return;
    setState(() => _isPressed = value);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = widget.colorScheme;
    final scheduleState = ref.watch(todayScheduleProvider);

    // Pick the entry the student could actually check into RIGHT NOW.
    //
    // Gated on `sessionLive`, not on `status == 'PENDING'`. Those are not
    // the same thing: the backend assigns PENDING as its default and only
    // narrows it once a Session row exists, so PENDING covers both "a
    // session is running, go check in" and "the lecturer hasn't started
    // anything yet" -- the latter being the normal state for most of the
    // day. Gating on PENDING would arm the tap target at 8am for a 2pm
    // lecture and claim the session is live when no session exists.
    TodayProtocolEntry? nextSession;
    for (final entry in scheduleState.entries) {
      if (entry.sessionLive) {
        nextSession = entry;
        break;
      }
    }

    // Nothing live to check into. Fall back to the next course still on
    // today's timetable, purely to display its scheduled time -- the card
    // stays informative instead of going blank, and says *when* the
    // session is due rather than implying one is running.
    TodayProtocolEntry? nextScheduled;
    if (nextSession == null) {
      for (final entry in scheduleState.entries) {
        if (entry.status == 'PENDING') {
          nextScheduled = entry;
          break;
        }
      }
    }

    final isLive = !scheduleState.isLoading && nextSession != null;
    final display = nextSession ?? nextScheduled;

    // An ad-hoc session (lecturer started a class with no scheduled slot
    // today) is checkable exactly like a scheduled one, so it arms the same
    // way -- it's just labelled differently, since a student who never saw
    // it on their timetable would otherwise be confused by an unexpected
    // card. See the union block in api/student.py's get_today_schedule.
    final isAdHoc = display?.adHoc ?? false;

    final hasTimeRange =
        display?.startTime != null && display?.endTime != null;
    final timeRange = hasTimeRange
        ? '${display!.startTime} - ${display.endTime}'
              '${display.room != null ? ' · ${display.room}' : ''}'
        : null;

    final subtitle = scheduleState.isLoading
        ? 'LOADING TODAY\'S SCHEDULE...'
        : isLive
        ? isAdHoc
              ? 'EXTRA SESSION · CHECK IN NOW'
              : 'SESSION LIVE · CHECK IN NOW'
        : nextScheduled != null
        ? 'SCHEDULED · SESSION NOT STARTED'
        : 'NO UPCOMING SESSIONS';

    final title = display?.courseName ?? 'No Upcoming Sessions';

    // In the dead states the card recedes: dimmed background, muted accent
    // stripe, greyed type. The stripe stays so the card keeps its shape
    // rather than shifting layout between states.
    final borderColor = isLive
        ? colorScheme.primary
        : colorScheme.outline.withValues(alpha: 0.35);

    return AnimatedScale(
      // Press feedback -- pairs with the haptic the sheet fires on open.
      scale: _isPressed ? 0.98 : 1.0,
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
      child: Material(
        color: isLive
            ? colorScheme.surfaceContainer
            : colorScheme.surfaceContainer.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(16),
        child: InkWell(
          // The entire card is the target, not a button nested inside it.
          // The old layout's affordance was the flat rectangle while the
          // hit area was a 48px button in the middle, which read as a
          // mismatch once you started aiming for the card itself.
          onTap: isLive ? () => NfcBroadcastSheet.show(context) : null,
          onHighlightChanged: isLive ? _setPressed : null,
          borderRadius: BorderRadius.circular(16),
          splashColor: colorScheme.primary.withValues(alpha: 0.08),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(16),
              border: Border(
                left: BorderSide(color: borderColor, width: 4),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        subtitle,
                        style: TextStyle(
                          fontSize: 10,
                          letterSpacing: 1.5,
                          fontWeight: FontWeight.bold,
                          color: isLive
                              ? colorScheme.primary
                              : Colors.grey.withValues(alpha: 0.7),
                        ),
                      ),
                    ),
                    // The contactless glyph is the whole point of the
                    // interaction -- it was absent from the old button,
                    // so nothing on the card said "NFC" until the sheet
                    // was already open.
                    Icon(
                      Icons.contactless_rounded,
                      size: 22,
                      color: isLive
                          ? colorScheme.primary
                          : colorScheme.onSurface.withValues(alpha: 0.25),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  title,
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                    color: isLive
                        ? null
                        : colorScheme.onSurface.withValues(alpha: 0.45),
                  ),
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
                // Call-to-action strip. Reads as the target in both states
                // so the card doesn't change height as the session starts
                // and ends -- that reflow was part of what made the old
                // version feel unstable.
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: isLive
                        ? colorScheme.primary
                        : colorScheme.onSurface.withValues(alpha: 0.06),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.nfc_rounded,
                        size: 16,
                        color: isLive
                            ? colorScheme.surface
                            : colorScheme.onSurface.withValues(alpha: 0.35),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        isLive
                            ? 'TAP TO CHECK IN'
                            : nextScheduled != null
                            // Start time, not "no session" -- there IS a
                            // session on the timetable, it just hasn't begun.
                            ? 'STARTS ${nextScheduled.startTime ?? '--:--'}'
                            : 'NO ACTIVE SESSION',
                        style: TextStyle(
                          letterSpacing: 2,
                          fontWeight: FontWeight.bold,
                          fontSize: 12,
                          color: isLive
                              ? colorScheme.surface
                              : colorScheme.onSurface.withValues(alpha: 0.45),
                        ),
                      ),
                    ],
                  ),
                ),
                if (isLive) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Hold the back of your phone near the terminal.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 11,
                      color: colorScheme.onSurface.withValues(alpha: 0.45),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
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
