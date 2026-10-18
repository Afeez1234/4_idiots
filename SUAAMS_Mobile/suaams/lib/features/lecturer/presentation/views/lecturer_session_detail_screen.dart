import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/lecturer/providers/session_detail_provider.dart';
import 'package:suaams/features/lecturer/models/session_detail_model.dart';
import 'package:suaams/shared/widgets/app_stat_box.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import 'package:suaams/core/network/user_facing_error.dart';
import 'package:suaams/shared/widgets/confirm_dialog.dart';

String _fmtTime(String? raw) {
  if (raw == null || raw.length < 5) return '--:--';
  return raw.substring(0, 5);
}

class LecturerSessionDetailScreen extends ConsumerWidget {
  final int courseId;
  final String sessionId;

  const LecturerSessionDetailScreen({
    super.key,
    required this.courseId,
    required this.sessionId,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final args = (courseId: courseId, sessionId: int.parse(sessionId));
    final state = ref.watch(sessionDetailProvider(args));
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Session Detail')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load the session',
          message: isGenericServerMessage(state.errorMessage)
                      ? 'Check your connection and try again.'
                      : state.errorMessage,
          onRetry: () =>
              ref.read(sessionDetailProvider(args).notifier).loadDetail(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(data.session.date ?? data.course.title),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(sessionDetailProvider(args).notifier).loadDetail(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${data.course.code} · ${_fmtTime(data.session.plannedStart)}–${_fmtTime(data.session.plannedEnd)}',
                style: AppTheme.accent(
                  size: 11,
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),

              _StatsGrid(stats: data.stats),
              const SizedBox(height: 32),

              Text(
                'ATTENDANCE',
                style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),

              if (data.attendance.isEmpty)
                const AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.contactless_rounded,
                  title: 'No check-ins yet',
                  message: 'Students appear here as they tap the terminal.',
                  compact: true,
                )
              else
                ...data.attendance.map(
                  (record) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _AttendanceCard(
                      record: record,
                      colorScheme: colorScheme,
                    ),
                  ),
                ),
              const SizedBox(height: 32),

              // Taps the terminal read while it couldn't reach the server.
              // Hidden when there's nothing to review.
              if (data.offlineTaps.isNotEmpty) ...[
                _OfflineTapsSection(args: args, taps: data.offlineTaps),
                const SizedBox(height: 32),
              ],

              // Manual marking: the fallback for a student whose phone
              // can't check in. Offered on ended sessions too, so the
              // register can be corrected after class.
              _NotCheckedInSection(args: args, students: data.notCheckedIn),
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatsGrid extends StatelessWidget {
  final SessionDetailStats stats;

  const _StatsGrid({required this.stats});

  @override
  Widget build(BuildContext context) {
    return AppStatRow([
      // ABSENT is left neutral here on purpose. It reads like it wants to
      // be the red box, but the old copy highlighted PRESENT green and
      // left ABSENT plain, and changing that is a visual decision, not a
      // refactor. Flagged rather than silently altered.
      AppStatValue.success('${stats.presentCount}', 'PRESENT'),
      AppStatValue('${stats.absentCount}', 'ABSENT'),
      AppStatValue('${stats.enrolledCount}', 'ENROLLED'),
    ]);
  }
}

class _AttendanceCard extends StatelessWidget {
  final SessionAttendanceRecord record;
  final ColorScheme colorScheme;

  const _AttendanceCard({required this.record, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    // The shared status map (attendance_status.dart), like every other
    // screen: this card coloured PRESENT green and everything else -- late,
    // absent, excused -- the same grey, and used the raw AppStatus hue,
    // which fails contrast as text in light mode.
    final status = record.status.toLowerCase();
    final statusColor = attendanceStatusText(status, terminalOf(context));

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  record.fullName,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  record.matricNumber,
                  style: AppTheme.accent(
                    size: 10,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                record.timeIn ?? '--:--',
                style: AppTheme.accent(size: 12, weight: FontWeight.w700),
              ),
              const SizedBox(height: 4),
              Text(
                attendanceStatusLabel(status),
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: statusColor,
                  letterSpacing: 0.5,
                ),
              ),
              // Only the non-default methods are labelled: a hand mark has
              // no device evidence behind it, and a Bluetooth code is weaker
              // evidence than a tap. An NFC tap is the normal case.
              if (_methodLabel(record.method) case final label?) ...[
                const SizedBox(height: 4),
                Text(
                  label,
                  style: AppTheme.accent(
                    size: 9,
                    letterSpacing: 0.5,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
              // A reader in another room took this check-in.
              if (record.wrongRoom) ...[
                const SizedBox(height: 4),
                Text(
                  'WRONG ROOM',
                  style: AppTheme.accent(
                    size: 9,
                    letterSpacing: 0.5,
                    color: colorScheme.error,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
}

String? _methodLabel(String? method) => switch (method) {
  'manual' => 'BY LECTURER',
  'ble' => 'BLUETOOTH',
  'offline' => 'OFFLINE TAP',
  _ => null,
};

class _NotCheckedInSection extends ConsumerStatefulWidget {
  final SessionDetailArgs args;
  final List<NotCheckedInStudent> students;

  const _NotCheckedInSection({required this.args, required this.students});

  @override
  ConsumerState<_NotCheckedInSection> createState() =>
      _NotCheckedInSectionState();
}

class _NotCheckedInSectionState extends ConsumerState<_NotCheckedInSection> {
  // The student whose mark is in flight. Disables every button meanwhile,
  // so a double tap can't fire two requests.
  int? _busyStudentId;

  Future<void> _markPresent(NotCheckedInStudent student) async {
    // A manual mark vouches for presence under the lecturer's name with
    // no device evidence, so it's confirmed rather than one-tap.
    final confirmed = await showConfirmDialog(
      context,
      title: 'Mark present?',
      message:
          'Mark ${student.fullName} present for this session? '
          'Only do this if you can see them in class. '
          'It is recorded under your name.',
      confirmLabel: 'MARK PRESENT',
    );
    if (!confirmed || !mounted) return;

    setState(() => _busyStudentId = student.studentId);
    final error = await ref
        .read(sessionDetailProvider(widget.args).notifier)
        .markPresent(student.studentId);
    if (!mounted) return;
    setState(() => _busyStudentId = null);

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(error ?? '${student.fullName} marked present.'),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'NOT CHECKED IN',
          style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
        ),
        const SizedBox(height: 16),
        if (widget.students.isEmpty)
          const AppStateView(
            kind: AppStateKind.empty,
            icon: Icons.task_alt_rounded,
            title: 'Everyone is accounted for',
            message: 'Every enrolled student has a record for this session.',
            compact: true,
          )
        else
          ...widget.students.map(
            (student) => Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
                decoration: BoxDecoration(
                  color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: colorScheme.outline.withValues(alpha: 0.1),
                  ),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            student.fullName,
                            style: const TextStyle(fontWeight: FontWeight.bold),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            student.matricNumber,
                            style: AppTheme.accent(
                              size: 10,
                              color: colorScheme.onSurface.withValues(
                                alpha: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (_busyStudentId == student.studentId)
                      const Padding(
                        padding: EdgeInsets.all(12),
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      )
                    else
                      TextButton(
                        onPressed: _busyStudentId == null
                            ? () => _markPresent(student)
                            : null,
                        child: const Text('MARK PRESENT'),
                      ),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}

class _OfflineTapsSection extends ConsumerStatefulWidget {
  final SessionDetailArgs args;
  final List<OfflineTap> taps;

  const _OfflineTapsSection({required this.args, required this.taps});

  @override
  ConsumerState<_OfflineTapsSection> createState() =>
      _OfflineTapsSectionState();
}

class _OfflineTapsSectionState extends ConsumerState<_OfflineTapsSection> {
  // The tap whose review is in flight, or -1 while "accept all" runs.
  // Disables every button meanwhile, so a double tap can't fire twice.
  int? _busyTapId;
  static const _acceptingAll = -1;

  SessionDetailNotifier get _notifier =>
      ref.read(sessionDetailProvider(widget.args).notifier);

  Future<void> _run(int busyId, Future<String> Function() action) async {
    setState(() => _busyTapId = busyId);
    final message = await action();
    if (!mounted) return;
    setState(() => _busyTapId = null);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _accept(OfflineTap tap) =>
      _run(tap.id, () => _notifier.reviewOfflineTap(tap.id, accept: true));

  Future<void> _reject(OfflineTap tap) async {
    // Rejecting throws away the only evidence the student was there, so it
    // asks first. Accepting a genuine signed tap is the expected action.
    final confirmed = await showConfirmDialog(
      context,
      title: 'Reject tap?',
      message:
          "Reject ${tap.fullName}'s offline tap? "
          "They won't be marked present for this session.",
      confirmLabel: 'REJECT',
      destructive: true,
    );
    if (!confirmed || !mounted) return;
    await _run(tap.id, () => _notifier.reviewOfflineTap(tap.id, accept: false));
  }

  Future<void> _acceptAll() async {
    final confirmed = await showConfirmDialog(
      context,
      title: 'Accept all taps?',
      message:
          'Accept all ${widget.taps.length} offline taps? Each student is '
          'marked at the time they tapped, under your name.',
      confirmLabel: 'ACCEPT ALL',
    );
    if (!confirmed || !mounted) return;
    await _run(_acceptingAll, _notifier.acceptAllOfflineTaps);
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final idle = _busyTapId == null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'TAPS WHILE OFFLINE (${widget.taps.length})',
                style: AppTheme.eyebrow(
                  colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              ),
            ),
            // Only worth a bulk action when there's more than one.
            if (widget.taps.length > 1)
              _busyTapId == _acceptingAll
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  : TextButton(
                      onPressed: idle ? _acceptAll : null,
                      child: const Text('ACCEPT ALL'),
                    ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          "The terminal read these phones but couldn't reach the server. "
          'Accepted taps count at the time shown.',
          style: TextStyle(
            fontSize: 12,
            color: colorScheme.onSurface.withValues(alpha: 0.5),
          ),
        ),
        const SizedBox(height: 16),
        ...widget.taps.map(
          (tap) => Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 8, 8),
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: colorScheme.outline.withValues(alpha: 0.1),
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          tap.fullName,
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          '${tap.matricNumber} · ${tap.tappedAt ?? '--:--'}',
                          style: AppTheme.accent(
                            size: 10,
                            color: colorScheme.onSurface.withValues(
                              alpha: 0.5,
                            ),
                          ),
                        ),
                        // Read by a reader in another room: shown before
                        // the lecturer decides.
                        if (tap.wrongRoom) ...[
                          const SizedBox(height: 4),
                          Text(
                            'WRONG ROOM',
                            style: AppTheme.accent(
                              size: 9,
                              letterSpacing: 0.5,
                              color: colorScheme.error,
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                  if (_busyTapId == tap.id)
                    const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    )
                  else ...[
                    IconButton(
                      tooltip: 'Reject',
                      onPressed: idle ? () => _reject(tap) : null,
                      icon: const Icon(Icons.close_rounded),
                    ),
                    TextButton(
                      onPressed: idle ? () => _accept(tap) : null,
                      child: const Text('ACCEPT'),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }
}
