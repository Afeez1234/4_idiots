import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../providers/lecturer_provider.dart';
import '../../models/lecturer_dashboard_model.dart';

// Sessions tab root. Reuses the already-loaded lecturerDashboardProvider
// (LecturerCourse.hasActiveSession/activeSessionId) instead of a separate
// endpoint -- the dashboard already fetches this on Home tab load, and
// StatefulShellRoute.indexedStack keeps every branch's Navigator (and so
// every provider a branch is watching) alive when switching tabs, so
// there's nothing new to fetch here.
class ActiveSessionsScreen extends ConsumerWidget {
  const ActiveSessionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerDashboardProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Active Sessions')),
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
      );
    }

    final activeCourses = data.courses
        .where((c) => c.hasActiveSession)
        .toList();

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Active Sessions'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(lecturerDashboardProvider.notifier).loadDashboardData(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (activeCourses.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 40),
                  child: Center(
                    child: Text(
                      'No sessions are currently live.',
                      style: TextStyle(color: Colors.grey),
                    ),
                  ),
                )
              else
                ...activeCourses.map(
                  (course) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _ActiveCourseCard(
                      course: course,
                      colorScheme: colorScheme,
                      onTap: () =>
                          context.push('/lecturer/sessions/course/${course.id}'),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ActiveCourseCard extends StatelessWidget {
  final LecturerCourse course;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _ActiveCourseCard({
    required this.course,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: const Color(0xFF10B981).withValues(alpha: 0.35),
          ),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: Color(0xFF10B981),
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    course.title,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 15,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    '${course.code} · ${course.enrolledCount} enrolled',
                    style: TextStyle(
                      fontSize: 10,
                      fontFamily: 'JetBrains Mono',
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: colorScheme.onSurface.withValues(alpha: 0.3),
            ),
          ],
        ),
      ),
    );
  }
}
