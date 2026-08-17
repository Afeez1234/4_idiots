import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/week_schedule_provider.dart';
import '../../models/week_schedule_entry.dart';

const _dayNameToIndex = {
  'Monday': 0,
  'Tuesday': 1,
  'Wednesday': 2,
  'Thursday': 3,
  'Friday': 4,
  'Saturday': 5,
  'Sunday': 6,
};

// Reuses the already-loaded weekScheduleProvider -- filters by day rather
// than fetching separately, same reasoning as CourseDetailScreen reusing
// studentDashboardProvider.
class DayDetailScreen extends ConsumerWidget {
  final String day;

  const DayDetailScreen({super.key, required this.day});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(weekScheduleProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.entries.isEmpty) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    if (state.errorMessage != null && state.entries.isEmpty) {
      return Scaffold(
        appBar: AppBar(title: Text(day)),
        body: Center(child: Text(state.errorMessage!)),
      );
    }

    final dayIndex = _dayNameToIndex[day];
    final dayEntries =
        state.entries.where((e) => e.dayOfWeek == dayIndex).toList()..sort(
          (a, b) => (a.startTime ?? '').compareTo(b.startTime ?? ''),
        );

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: Text(day),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (dayEntries.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 40),
                child: Center(
                  child: Text(
                    'No classes scheduled for this day.',
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              )
            else
              ...dayEntries.map(
                (entry) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _ClassCard(entry: entry, colorScheme: colorScheme),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _ClassCard extends StatelessWidget {
  final WeekScheduleEntry entry;
  final ColorScheme colorScheme;

  const _ClassCard({required this.entry, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(color: colorScheme.primary, width: 4),
        ),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  entry.courseName,
                  style: const TextStyle(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 4),
                Text(
                  entry.room != null
                      ? '${entry.courseCode} · ${entry.room}'
                      : entry.courseCode,
                  style: TextStyle(
                    fontSize: 10,
                    fontFamily: 'JetBrains Mono',
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                ),
              ],
            ),
          ),
          Text(
            '${entry.startTime ?? '--:--'} – ${entry.endTime ?? '--:--'}',
            style: const TextStyle(
              fontFamily: 'JetBrains Mono',
              fontWeight: FontWeight.bold,
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}
