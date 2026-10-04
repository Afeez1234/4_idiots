import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/features/student/models/today_protocol_entry.dart';
import 'package:suaams/features/student/presentation/views/nfc_broadcast_sheet.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/providers/today_schedule_provider.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/shared/utils/date_label.dart';
import 'package:suaams/features/student/providers/student_announcements_provider.dart';
import 'package:suaams/shared/widgets/app_badge.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/shared/widgets/dashboard_background.dart';
import 'package:suaams/shared/widgets/confirm_dialog.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/core/network/user_facing_error.dart';

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
      // The dashboard fetch failed and there is no cached data to fall back
      // on. This is the state a student sees if they're at the door on a
      // bad connection, so it gets a retry rather than a dead sentence.
      return Scaffold(
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title: "Couldn't load your dashboard",
          message: isGenericServerMessage(state.errorMessage)
                      ? 'Check your connection and try again.'
                      : state.errorMessage,
          onRetry: () =>
              ref.read(studentDashboardProvider.notifier).loadDashboardData(),
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
            child: SingleChildScrollView(
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

                  _NextSessionCard(colorScheme: colorScheme),
                  const SizedBox(height: 20),

                  _StatsGrid(stats: data.stats),
                  const SizedBox(height: 32),

                  Text(
                    'TODAY\'S PROTOCOL',
                    style: AppTheme.eyebrow(
                      colorScheme.onSurface.withValues(alpha: 0.55),
                    ),
                  ),
                  const SizedBox(height: 2),
                  // The schedule polls silently in the background, so
                  // without this an app left open since yesterday is
                  // indistinguishable from a current one. It is the only
                  // staleness signal on the screen.
                  Text(
                    todayLabel(),
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurface.withValues(alpha: 0.45),
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

  const _DashboardHeader({required this.profile, required this.colorScheme});

  Future<void> _showLogoutDialog(BuildContext context, WidgetRef ref) async {
    // Was a hand-rolled copy of this dialog -- one of four identical ones
    // across the student and lecturer shells, which had already drifted
    // apart (one said "terminal session", the rest said "session") and used
    // a third term, "Sign Out", alongside the profile tiles' "TERMINATE
    // SESSION" for the same action.
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
        : 'Unknown Student';
    final avatarLetter = displayName.isNotEmpty
        ? displayName[0].toUpperCase()
        : 'S';

    return Row(
      // top rather than center: the name can now wrap to two lines, and
      // centring would make a short name drift toward the middle of a tall
      // box while a long one sat correctly against the top.
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'WELCOME BACK',
                style: AppTheme.eyebrow(
                  colorScheme.onSurface.withValues(alpha: 0.55),
                ),
              ),
              const SizedBox(height: 2),
              Text(
                fallbackName,
                // Two lines, not one. A Nigerian name -- Chukwuemeka
                // Oluwatobi Adeyemi -- is around 380px at titleLarge, and
                // this box has never had that much room on a 360dp phone.
                // Ellipsising a person's name is worse than a tall header:
                // the name is the subject of the screen. Two lines clears
                // almost every real case, and the third would have been
                // cut anyway.
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w700,
                  height: 1.2,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 12),
        // The theme toggle that used to sit here was a duplicate: Profile
        // already carries it, labelled "Stealth Mode" / "Blueprint Mode"
        // (profile_view_screen.dart). Dropping the header copy reclaims
        // 48px for the name and loses no function.
        FittedBox(
          fit: BoxFit.scaleDown,
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Badge on the announcements button, not the bottom nav --
              // announcements are only reachable from this header, so
              // putting the count anywhere else would advertise something
              // you can't get to from where you're standing.
              //
              // select() for the same reason as the shells' session dot: the
              // announcements provider is autoDispose and refetched on
              // rebuild, so watching the whole state would rebuild the
              // header on every unrelated change to it.
              Builder(
                builder: (context) {
                  final unread = ref.watch(
                    studentAnnouncementsProvider.select(
                      (s) => s.unreadCount,
                    ),
                  );
                  return Stack(
                    clipBehavior: Clip.none,
                    children: [
                      IconButton(
                        onPressed: () => context
                            .push('/student/home/announcements'),
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
                        tooltip: unread > 0
                            ? 'Announcements ($unread unread)'
                            : 'Announcements',
                      ),
                      if (unread > 0)
                        Positioned(
                          right: -2,
                          top: -2,
                          child: AppBadge.count(
                            count: unread,
                            background: colorScheme.primary,
                            borderColor: colorScheme.surface,
                          ),
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(width: 8),
              // The avatar doubles as the LOG OUT control, so it gets a
              // real 48dp target and a ripple rather than the 36px
              // GestureDetector it replaced -- a destructive action
              // should not be the smallest target in the header.
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
                            // Explicit, and load-bearing. CircleAvatar
                            // derives its text colour as onPrimary, which
                            // measures 1.23:1 against surfaceContainer in
                            // dark mode and 1.00:1 in light -- black on
                            // near-black, then white on white. The initial
                            // was invisible in both themes until this was
                            // set. onSurface gives 17:1 either way.
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
    final terminal = terminalOf(context);
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

    final hasTimeRange = display?.startTime != null && display?.endTime != null;
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
              border: Border(left: BorderSide(color: borderColor, width: 4)),
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
                              : colorScheme.onSurface.withValues(alpha: 0.55),
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
                          ? terminal.accent
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
                    style: AppTheme.accent(
                      size: 11,
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
                        ? terminal.accent
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
                            ? terminal.onAccent
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
                              ? terminal.onAccent
                              : colorScheme.onSurface.withValues(alpha: 0.45),
                        ),
                      ),
                    ],
                  ),
                ),
                if (isLive) ...[
                  const SizedBox(height: 10),
                  // The biometric prompt is the single most surprising
                  // moment in the app: tapping this card used to open the
                  // sheet and then immediately throw an OS fingerprint
                  // dialog with nothing on screen having warned you. That
                  // prompt is not optional -- nfc_provider.dart throws
                  // "Hardware security mismatch" without it -- so it is
                  // named up front instead of arriving as a surprise.
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.fingerprint_rounded,
                        size: 14,
                        color: colorScheme.onSurface.withValues(alpha: 0.45),
                      ),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(
                          "You'll confirm with your fingerprint, then hold "
                          'your phone to the terminal.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(
                                color: colorScheme.onSurface.withValues(
                                  alpha: 0.45,
                                ),
                              ),
                        ),
                      ),
                    ],
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

  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return AppStatRow([
      AppStatValue('${stats.overallRate}%', 'OVERALL'),
      AppStatValue('${stats.attendanceCount}', 'SESSIONS'),
      // Was `final isWarning = label == 'MISSED'` inside the old private
      // _StatBox -- the warning styling was keyed off this display string,
      // so renaming the label would have silently dropped it. See
      // AppStatTone in shared/widgets/app_stat_box.dart.
      AppStatValue.warning('${stats.atRiskCount}', 'MISSED'),
    ]);
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
      // Same reasoning as the dashboard-level failure: this is the one that
      // happens on a bad connection, and a bare red sentence gave the
      // student nothing to do about it. refreshTodaySchedule() restarts the
      // poll as well as fetching once, so the retry doesn't leave the list
      // frozen on a stale error.
      return AppStateView(
        kind: AppStateKind.error,
        icon: Icons.event_busy_rounded,
        title: "Couldn't load today's schedule",
        message:
            'Your check-in card is still shown above if a session is live.',
        compact: true,
        onRetry: () =>
            ref.read(todayScheduleProvider.notifier).refreshTodaySchedule(),
      );
    }

    if (scheduleState.entries.isEmpty) {
      // Genuinely empty -- nothing on the timetable today. No retry button
      // here, because there is nothing to retry; the poll is already
      // running and will populate this on its own.
      return const AppStateView(
        kind: AppStateKind.empty,
        icon: Icons.beach_access_rounded,
        title: 'No protocols scheduled today',
        message:
            'Enjoy the free day — check-in opens when a lecturer starts a session.',
        compact: true,
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

    // Status colours come from the terminal palette rather than being
    // re-derived here. The raw hues this used (#10B981 on a 10% emerald
    // tint) score 2.31:1 in light mode -- the PRESENT label was failing AA
    // and had been since the pill was first written.
    final palette = terminalOf(context);
    final Color statusColor;
    final Color bgColor;
    final Color borderColor;
    if (isPresent) {
      statusColor = palette.successText;
      bgColor = AppStatus.success.withValues(alpha: 0.1);
      borderColor = AppStatus.success.withValues(alpha: 0.3);
    } else if (isAbsent) {
      statusColor = palette.dangerText;
      bgColor = AppStatus.danger.withValues(alpha: 0.1);
      borderColor = AppStatus.danger.withValues(alpha: 0.3);
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
                    style: AppTheme.accent(
                      size: 11,
                      color: colorScheme.onSurface.withValues(alpha: 0.55),
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
                      fontSize: 11,
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
