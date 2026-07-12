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
            // Map through our records using the new bulletproof widget
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

    // Safe fallbacks in case the backend sends empty strings
    final courseName = record.course.isEmpty ? 'UNKNOWN MODULE' : record.course;
    final dateText = record.date.isEmpty ? '--/--/----' : record.date.toUpperCase();
    final timeText = record.time.isEmpty ? '--:--' : record.time;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias, // Ensures the hardcoded border stays rounded
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(12),
        // We use a uniform border all around to prevent Skia rendering bugs
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: IntrinsicHeight(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. Physical Left Border Accent (Guaranteed to render)
            Container(
              width: 4,
              color: statusColor,
            ),
            
            // 2. The Content Payload
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Text(
                            courseName,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: 14,
                              letterSpacing: 1,
                              // EXPLICIT COLOR: Fixes the invisible text bug
                              color: colorScheme.onSurface, 
                            ),
                          ),
                          const SizedBox(height: 8),
                          // Wrap prevents horizontal overflow if the date string is unusually long
                          Wrap(
                            spacing: 12,
                            runSpacing: 4,
                            crossAxisAlignment: WrapCrossAlignment.center,
                            children: [
                              Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.calendar_today_rounded, size: 12, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                                  const SizedBox(width: 4),
                                  Text(
                                    dateText,
                                    style: TextStyle(
                                      fontSize: 10,
                                      fontFamily: 'JetBrains Mono',
                                      fontWeight: FontWeight.bold,
                                      color: colorScheme.onSurface.withValues(alpha: 0.6),
                                    ),
                                  ),
                                ],
                              ),
                              Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(Icons.access_time_rounded, size: 12, color: colorScheme.onSurface.withValues(alpha: 0.4)),
                                  const SizedBox(width: 4),
                                  Text(
                                    timeText,
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
                        ],
                      ),
                    ),
                    
                    // 3. The Status Pill
                    const SizedBox(width: 8),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
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
                          color: statusColor, // Explicitly enforce the Emerald/Crimson color
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}