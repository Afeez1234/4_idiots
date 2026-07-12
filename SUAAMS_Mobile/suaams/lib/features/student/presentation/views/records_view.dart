import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../core/providers/theme_provider.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';

class RecordsView extends ConsumerWidget {
  const RecordsView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final themeMode = ref.watch(themeProvider);
    final isDarkMode = themeMode == ThemeMode.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final data = state.data;
    if (data == null) return const SizedBox.shrink();

    final records = data.recentAttendance;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'TERMINAL LEDGER',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 2,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          
          if (records.isEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainer,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
              ),
              child: Text(
                '> NO LOGS DETECTED IN DATABASE...',
                style: TextStyle(
                  fontFamily: 'JetBrains Mono', 
                  fontSize: 12,
                  color: colorScheme.onSurface.withValues(alpha: 0.5)
                ),
              ),
            )
          else
            ...records.map((record) => _buildLogEntry(record, colorScheme, isDarkMode)),
            
          const SizedBox(height: 120), // Padding for bottom nav
        ],
      ),
    );
  }

  Widget _buildLogEntry(RecentAttendance record, ColorScheme colorScheme, bool isDarkMode) {
    final isPresent = record.present;
    // Emerald for success, Crimson for failure
    final statusColor = isPresent ? const Color(0xFF10B981) : const Color(0xFFEF4444);
    final statusText = isPresent ? 'VERIFIED' : 'MISSED';

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        border: Border(
          left: BorderSide(color: statusColor, width: 3),
          top: BorderSide(color: colorScheme.outline.withValues(alpha: 0.05)),
          right: BorderSide(color: colorScheme.outline.withValues(alpha: 0.05)),
          bottom: BorderSide(color: colorScheme.outline.withValues(alpha: 0.05)),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  record.course,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 14,
                    letterSpacing: 1,
                  ),
                ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Icon(Icons.calendar_today_rounded, size: 12, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                    const SizedBox(width: 4),
                    Text(
                      record.date.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        fontFamily: 'JetBrains Mono',
                        fontWeight: FontWeight.bold,
                        color: colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Icon(Icons.access_time_rounded, size: 12, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                    const SizedBox(width: 4),
                    Text(
                      record.time,
                      style: TextStyle(
                        fontSize: 10,
                        fontFamily: 'JetBrains Mono',
                        fontWeight: FontWeight.bold,
                        color: colorScheme.onSurface.withValues(alpha: 0.6),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: statusColor.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: statusColor.withValues(alpha: 0.3)),
            ),
            child: Text(
              statusText,
              style: TextStyle(
                fontSize: 8,
                fontWeight: FontWeight.bold,
                letterSpacing: 1,
                color: statusColor,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

