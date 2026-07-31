import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/course_workspace_provider.dart';
import '../../models/course_workspace_model.dart';

class CourseWorkspaceScreen extends ConsumerStatefulWidget {
  final int courseId;

  const CourseWorkspaceScreen({super.key, required this.courseId});

  @override
  ConsumerState<CourseWorkspaceScreen> createState() => _CourseWorkspaceScreenState();
}

class _CourseWorkspaceScreenState extends ConsumerState<CourseWorkspaceScreen> {
  TimeOfDay? _plannedStart;
  TimeOfDay? _plannedEnd;
  bool _submitting = false;

  // TimeOfDay -> "HH:MM", matching the format api/lecturer.py's
  // start_session parses via datetime.strptime(value, '%H:%M').
  String _formatTime(TimeOfDay t) =>
      '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

  Future<void> _pickTime(bool isStart) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: (isStart ? _plannedStart : _plannedEnd) ?? TimeOfDay.now(),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _plannedStart = picked;
      } else {
        _plannedEnd = picked;
      }
    });
  }

  Future<void> _startSession() async {
    setState(() => _submitting = true);
    final success = await ref.read(courseWorkspaceProvider(widget.courseId).notifier).startSession(
          plannedStart: _plannedStart != null ? _formatTime(_plannedStart!) : null,
          plannedEnd: _plannedEnd != null ? _formatTime(_plannedEnd!) : null,
        );
    if (!mounted) return;
    setState(() => _submitting = false);
    if (!success) {
      final error = ref.read(courseWorkspaceProvider(widget.courseId)).errorMessage;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error ?? 'Failed to start session.')),
      );
    }
  }

  Future<void> _endSession() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('End Session'),
        content: const Text('Are you sure you want to end the active session?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('CANCEL')),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('END SESSION')),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _submitting = true);
    final success = await ref.read(courseWorkspaceProvider(widget.courseId).notifier).endSession();
    if (!mounted) return;
    setState(() => _submitting = false);
    if (!success) {
      final error = ref.read(courseWorkspaceProvider(widget.courseId)).errorMessage;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error ?? 'Failed to end session.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(courseWorkspaceProvider(widget.courseId));
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(),
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(data.course.title),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.read(courseWorkspaceProvider(widget.courseId).notifier).loadWorkspace(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                data.course.code,
                style: TextStyle(
                  fontSize: 11,
                  fontFamily: 'JetBrains Mono',
                  letterSpacing: 1,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              const SizedBox(height: 24),

              _WorkspaceStatsGrid(stats: data.stats, colorScheme: colorScheme),
              const SizedBox(height: 32),

              _SessionControls(
                activeSession: data.activeSession,
                colorScheme: colorScheme,
                submitting: _submitting,
                plannedStart: _plannedStart,
                plannedEnd: _plannedEnd,
                onPickStart: () => _pickTime(true),
                onPickEnd: () => _pickTime(false),
                onStart: _startSession,
                onEnd: _endSession,
              ),

              if (data.activeSession != null) ...[
                const SizedBox(height: 32),
                const Text(
                  'LIVE ATTENDANCE',
                  style: TextStyle(
                    fontSize: 10,
                    letterSpacing: 1.5,
                    color: Colors.grey,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const SizedBox(height: 16),
                if (data.liveAttendance.isEmpty)
                  const Text(
                    'No check-ins yet. Waiting for students to scan…',
                    style: TextStyle(color: Colors.grey),
                  )
                else
                  ...data.liveAttendance.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: _LiveAttendanceCard(entry: entry, colorScheme: colorScheme),
                    ),
                  ),
              ],
              const SizedBox(height: 32),
            ],
          ),
        ),
      ),
    );
  }
}

class _WorkspaceStatsGrid extends StatelessWidget {
  final WorkspaceStats stats;
  final ColorScheme colorScheme;

  const _WorkspaceStatsGrid({required this.stats, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        _StatBox(val: '${stats.enrolledCount}', label: 'ENROLLED', colorScheme: colorScheme),
        const SizedBox(width: 12),
        _StatBox(val: '${stats.avgAttendance}%', label: 'AVG ATTENDANCE', colorScheme: colorScheme),
        const SizedBox(width: 12),
        _StatBox(val: '${stats.presentNow}', label: 'PRESENT NOW', colorScheme: colorScheme, highlight: stats.presentNow > 0),
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

class _SessionControls extends StatelessWidget {
  final ActiveSessionInfo? activeSession;
  final ColorScheme colorScheme;
  final bool submitting;
  final TimeOfDay? plannedStart;
  final TimeOfDay? plannedEnd;
  final VoidCallback onPickStart;
  final VoidCallback onPickEnd;
  final VoidCallback onStart;
  final VoidCallback onEnd;

  const _SessionControls({
    required this.activeSession,
    required this.colorScheme,
    required this.submitting,
    required this.plannedStart,
    required this.plannedEnd,
    required this.onPickStart,
    required this.onPickEnd,
    required this.onStart,
    required this.onEnd,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border(
          left: BorderSide(
            color: activeSession != null ? const Color(0xFF10B981) : colorScheme.primary,
            width: 4,
          ),
        ),
      ),
      child: activeSession != null ? _buildActive(context) : _buildIdle(context),
    );
  }

  Widget _buildActive(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.circle, size: 8, color: Color(0xFF10B981)),
            SizedBox(width: 8),
            Text('SESSION ACTIVE', style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 1.5, fontSize: 12)),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'Planned ${activeSession!.plannedStart ?? '--:--'} – ${activeSession!.plannedEnd ?? '--:--'}',
          style: TextStyle(fontSize: 12, color: colorScheme.onSurface.withValues(alpha: 0.6)),
        ),
        const SizedBox(height: 20),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: colorScheme.error,
            foregroundColor: colorScheme.onError,
            minimumSize: const Size(double.infinity, 48),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            elevation: 0,
          ),
          onPressed: submitting ? null : onEnd,
          child: submitting
              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('END SESSION', style: TextStyle(letterSpacing: 2, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }

  Widget _buildIdle(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text(
          'NO ACTIVE SESSION',
          style: TextStyle(fontSize: 10, letterSpacing: 1.5, color: Colors.grey, fontWeight: FontWeight.bold),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            Expanded(
              child: _TimePickerField(
                label: 'Planned Start (optional)',
                value: plannedStart,
                onTap: onPickStart,
                colorScheme: colorScheme,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: _TimePickerField(
                label: 'Planned End (optional)',
                value: plannedEnd,
                onTap: onPickEnd,
                colorScheme: colorScheme,
              ),
            ),
          ],
        ),
        const SizedBox(height: 20),
        ElevatedButton(
          style: ElevatedButton.styleFrom(
            backgroundColor: colorScheme.primary,
            foregroundColor: colorScheme.surface,
            minimumSize: const Size(double.infinity, 48),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            elevation: 0,
          ),
          onPressed: submitting ? null : onStart,
          child: submitting
              ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('START SESSION', style: TextStyle(letterSpacing: 2, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}

class _TimePickerField extends StatelessWidget {
  final String label;
  final TimeOfDay? value;
  final VoidCallback onTap;
  final ColorScheme colorScheme;

  const _TimePickerField({
    required this.label,
    required this.value,
    required this.onTap,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: colorScheme.surface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(label, style: TextStyle(fontSize: 9, color: colorScheme.onSurface.withValues(alpha: 0.5))),
            const SizedBox(height: 2),
            Text(
              value?.format(context) ?? '--:--',
              style: const TextStyle(fontFamily: 'JetBrains Mono', fontWeight: FontWeight.bold),
            ),
          ],
        ),
      ),
    );
  }
}

class _LiveAttendanceCard extends StatelessWidget {
  final LiveAttendanceEntry entry;
  final ColorScheme colorScheme;

  const _LiveAttendanceCard({required this.entry, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    final isPresent = entry.status.toLowerCase() == 'present';
    final statusColor = isPresent ? const Color(0xFF10B981) : colorScheme.onSurface.withValues(alpha: 0.5);

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
                Text(entry.fullName, style: const TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Text(
                  entry.matricNumber,
                  style: TextStyle(fontSize: 10, color: colorScheme.onSurface.withValues(alpha: 0.5), fontFamily: 'JetBrains Mono'),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                entry.timeIn ?? '--:--',
                style: const TextStyle(fontFamily: 'JetBrains Mono', fontWeight: FontWeight.bold, fontSize: 12),
              ),
              const SizedBox(height: 4),
              Text(
                entry.status.toUpperCase(),
                style: TextStyle(fontSize: 9, fontWeight: FontWeight.bold, color: statusColor, letterSpacing: 0.5),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
