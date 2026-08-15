import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/shared/utils/attendance_status.dart';
import '../../../../core/providers/theme_provider.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';

class RecordsView extends ConsumerStatefulWidget {
  const RecordsView({super.key});

  @override
  ConsumerState<RecordsView> createState() => _RecordsViewState();
}

class _RecordsViewState extends ConsumerState<RecordsView> {
  String _selectedFilter = 'All';
  final List<String> _filters = ['All', 'This week', 'This month'];

  // PERF FIX: memoization cache for _getFilteredRecords/_groupRecordsByMonth
  // below. Both do O(n) work with per-record DateTime string-parsing, and
  // were previously re-run on every single build() call -- including builds
  // triggered by unrelated things like a theme toggle (this widget watches
  // themeProvider) -- even when neither the source records nor the selected
  // filter had changed. These fields cache the last computed result so the
  // real work only reruns when one of those two inputs actually changes.
  List<RecentAttendance>? _cachedSourceRecords;
  String? _cachedFilter;
  List<RecentAttendance> _cachedFilteredRecords = const [];
  Map<String, List<RecentAttendance>> _cachedGroupedRecords = const {};

  // --- Helper: Parse Date String ('14 Jul 2026') to DateTime ---
  DateTime? _parseDate(String dateStr) {
    try {
      final parts = dateStr.split(' ');
      if (parts.length != 3) return null;
      final day = int.parse(parts[0]);
      final monthStr = parts[1].toLowerCase();
      final year = int.parse(parts[2]);

      const months = {
        'jan': 1,
        'feb': 2,
        'mar': 3,
        'apr': 4,
        'may': 5,
        'jun': 6,
        'jul': 7,
        'aug': 8,
        'sep': 9,
        'oct': 10,
        'nov': 11,
        'dec': 12,
      };
      final month = months[monthStr] ?? 1;
      return DateTime(year, month, day);
    } catch (e) {
      return null;
    }
  }

  // --- Helper: Filter Records ---
  List<RecentAttendance> _getFilteredRecords(List<RecentAttendance> records) {
    final now = DateTime.now();

    return records.where((record) {
      if (_selectedFilter == 'All') return true;

      final dt = _parseDate(record.date);
      if (dt == null) return true; // Show unparseable dates by default

      if (_selectedFilter == 'This week') {
        final difference = now.difference(dt).inDays;
        return difference >= 0 && difference <= 7;
      } else if (_selectedFilter == 'This month') {
        return dt.month == now.month && dt.year == now.year;
      }
      return true;
    }).toList();
  }

  // --- Helper: Group Records by Month ---
  Map<String, List<RecentAttendance>> _groupRecordsByMonth(
    List<RecentAttendance> records,
  ) {
    final map = <String, List<RecentAttendance>>{};
    const monthNames = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];

    for (var record in records) {
      final dt = _parseDate(record.date);
      final key = dt != null
          ? '${monthNames[dt.month - 1]} ${dt.year}'
          : 'Archived Records';

      if (!map.containsKey(key)) {
        map[key] = [];
      }
      map[key]!.add(record);
    }
    return map;
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(studentDashboardProvider);
    final themeMode = ref.watch(themeProvider);
    final isDarkMode = themeMode == ThemeMode.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final data = state.data;
    if (data == null) return const SizedBox.shrink();

    // PERF FIX: only recompute filtering/grouping when the source list or
    // the selected filter actually changed (see field doc-comments above).
    if (!identical(_cachedSourceRecords, data.recentAttendance) ||
        _cachedFilter != _selectedFilter) {
      _cachedSourceRecords = data.recentAttendance;
      _cachedFilter = _selectedFilter;
      _cachedFilteredRecords = _getFilteredRecords(data.recentAttendance);
      _cachedGroupedRecords = _groupRecordsByMonth(_cachedFilteredRecords);
    }

    final filteredRecords = _cachedFilteredRecords;
    final groupedRecords = _cachedGroupedRecords;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          const Text(
            'ATTENDANCE HISTORY',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 2,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),

          // Filter Tabs
          _buildFilterTabs(colorScheme),
          const SizedBox(height: 24),

          // Empty State
          if (filteredRecords.isEmpty)
            _buildEmptyState(colorScheme)
          else
            // Grouped Lists
            ...groupedRecords.entries.map((entry) {
              return Padding(
                padding: const EdgeInsets.only(bottom: 24.0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Month Header
                    Text(
                      entry.key.toUpperCase(),
                      style: TextStyle(
                        fontSize: 11,
                        letterSpacing: 1.5,
                        fontWeight: FontWeight.w900,
                        color: colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Month's Records
                    ...entry.value.map(
                      (record) =>
                          _buildLogEntry(record, colorScheme, isDarkMode),
                    ),
                  ],
                ),
              );
            }),

          const SizedBox(height: 100), // Bottom padding
        ],
      ),
    );
  }

  // --- UI: Filter Tabs ---
  Widget _buildFilterTabs(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: Row(
        children: _filters.map((filter) {
          final isSelected = _selectedFilter == filter;
          return Expanded(
            child: GestureDetector(
              onTap: () => setState(() => _selectedFilter = filter),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 10),
                decoration: BoxDecoration(
                  color: isSelected ? colorScheme.primary : Colors.transparent,
                  borderRadius: BorderRadius.circular(8),
                  boxShadow: isSelected
                      ? [
                          BoxShadow(
                            color: colorScheme.primary.withValues(alpha: 0.3),
                            blurRadius: 8,
                            offset: const Offset(0, 2),
                          ),
                        ]
                      : [],
                ),
                child: Center(
                  child: Text(
                    filter.toUpperCase(),
                    style: TextStyle(
                      fontSize: 9,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1,
                      color: isSelected
                          ? colorScheme.surface
                          : colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  // --- UI: Empty State ---
  Widget _buildEmptyState(ColorScheme colorScheme) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: Column(
        children: [
          Icon(
            Icons.history_rounded,
            size: 48,
            color: colorScheme.onSurface.withValues(alpha: 0.2),
          ),
          const SizedBox(height: 16),
          Text(
            'NO RECORDS FOUND',
            style: TextStyle(
              fontFamily: 'JetBrains Mono',
              fontSize: 12,
              fontWeight: FontWeight.bold,
              color: colorScheme.onSurface.withValues(alpha: 0.5),
            ),
          ),
        ],
      ),
    );
  }

  // --- UI: Log Entry Card ---
  Widget _buildLogEntry(
    RecentAttendance record,
    ColorScheme colorScheme,
    bool isDarkMode,
  ) {
    final statusColor = attendanceStatusColor(record.status);
    final statusText = attendanceStatusLabel(record.status);

    final courseName = record.course.isEmpty ? 'UNKNOWN MODULE' : record.course;
    final dateText = record.date.isEmpty ? '--/--/----' : record.date;
    final timeText = record.time.isEmpty ? '--:--' : record.time;

    return InkWell(
      onTap: () => context.push(
        '/student/attendance/history/session/${record.sessionId}',
      ),
      borderRadius: BorderRadius.circular(16),
      child: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
        ),
        child: Row(
          children: [
            // The Status Dot
            Container(
              width: 12,
              height: 12,
              decoration: BoxDecoration(
                color: statusColor,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: statusColor.withValues(alpha: 0.4),
                    blurRadius: 6,
                    spreadRadius: 1,
                  ),
                ],
              ),
            ),
            const SizedBox(width: 16),

            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    courseName,
                    style: const TextStyle(
                      fontWeight: FontWeight.w900,
                      fontSize: 15,
                      letterSpacing: 0.5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Text(
                        dateText.toUpperCase(),
                        style: TextStyle(
                          fontSize: 10,
                          fontFamily: 'JetBrains Mono',
                          fontWeight: FontWeight.w600,
                          color: colorScheme.onSurface.withValues(alpha: 0.6),
                        ),
                      ),
                      Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: CircleAvatar(
                          radius: 2,
                          backgroundColor: colorScheme.onSurface.withValues(
                            alpha: 0.3,
                          ),
                        ),
                      ),
                      Text(
                        statusText,
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 1,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),

            // Time badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
              decoration: BoxDecoration(
                color: colorScheme.surface,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(
                  color: colorScheme.outline.withValues(alpha: 0.1),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    Icons.access_time_rounded,
                    size: 12,
                    color: colorScheme.onSurface.withValues(alpha: 0.5),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    timeText,
                    style: TextStyle(
                      fontSize: 11,
                      fontFamily: 'JetBrains Mono',
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onSurface.withValues(alpha: 0.8),
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
