import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';

class CoursesView extends ConsumerWidget {
  const CoursesView({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final data = state.data;
    if (data == null) return const SizedBox.shrink();

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'ACADEMIC MODULES',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 2,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          
          // Map through the actual courses from the backend
          ...data.courses.map((course) => _buildCourseCard(course, colorScheme, isDarkMode)),
          
          const SizedBox(height: 120), // Padding for the bottom navigation bar
        ],
      ),
    );
  }

  Widget _buildCourseCard(CourseBreakdown course, ColorScheme colorScheme, bool isDarkMode) {
    // Determine the health color based on the attendance percentage
    Color healthColor;
    if (course.pct >= 75) {
      healthColor = const Color(0xFF10B981); // Emerald (Safe)
    } else if (course.pct >= 50) {
      healthColor = const Color(0xFFF59E0B); // Amber (Warning)
    } else {
      healthColor = const Color(0xFFEF4444); // Crimson (Danger)
    }

    return Container(
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
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: colorScheme.surface,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
                ),
                child: Text(
                  course.code,
                  style: const TextStyle(
                    fontFamily: 'JetBrains Mono',
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              // Percentage Text
              Text(
                '${course.pct}%',
                style: TextStyle(
                  fontFamily: 'JetBrains Mono',
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                  color: healthColor,
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          
          // Course Name
          Text(
            course.name,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),
          
          // Progress Details
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'ATTENDANCE',
                style: TextStyle(
                  fontSize: 8,
                  letterSpacing: 1.5,
                  fontWeight: FontWeight.bold,
                  color: colorScheme.onSurface.withValues(alpha: 0.5),
                ),
              ),
              Text(
                '${course.attended} / ${course.total} SESSIONS',
                style: TextStyle(
                  fontSize: 10,
                  fontFamily: 'JetBrains Mono',
                  fontWeight: FontWeight.bold,
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
              border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                return Align(
                  alignment: Alignment.centerLeft,
                  child: Container(
                    width: constraints.maxWidth * (course.pct / 100).clamp(0.0, 1.0),
                    decoration: BoxDecoration(
                      color: healthColor,
                      borderRadius: BorderRadius.circular(3),
                      boxShadow: [
                        BoxShadow(
                          color: healthColor.withValues(alpha: 0.3),
                          blurRadius: 4,
                          offset: const Offset(0, 2),
                        )
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}