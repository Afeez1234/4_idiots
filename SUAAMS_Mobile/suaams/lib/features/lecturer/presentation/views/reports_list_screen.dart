import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart';
import 'package:suaams/features/lecturer/providers/course_export_provider.dart';
import 'package:suaams/features/lecturer/models/lecturer_dashboard_model.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:suaams/core/theme/app_theme.dart';

// Reports tab root -- reuses the already-loaded lecturerDashboardProvider
// course list (same reasoning as ActiveSessionsScreen) rather than a
// separate fetch, since the dashboard already has everything this list
// needs (title/code/enrolled_count/avg_attendance).
class ReportsListScreen extends ConsumerWidget {
  const ReportsListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerDashboardProvider);
    final colorScheme = Theme.of(context).colorScheme;
    final exportingCourseId = ref.watch(courseExportProvider);

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Reports')),
        body: AppStateView(
          kind: AppStateKind.error,
          icon: Icons.cloud_off_rounded,
          title:
              'Couldn'
              't load your reports',
          message: state.errorMessage ?? 'Check your connection and try again.',
          onRetry: () =>
              ref.read(lecturerDashboardProvider.notifier).loadDashboardData(),
        ),
      );
    }

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Reports'),
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
              const Text(
                'COURSE REPORTS',
                style: TextStyle(
                  fontSize: 10,
                  letterSpacing: 2,
                  color: Colors.grey,
                  fontWeight: FontWeight.bold,
                ),
              ),
              const SizedBox(height: 16),
              if (data.courses.isEmpty)
                AppStateView(
                  kind: AppStateKind.empty,
                  icon: Icons.summarize_rounded,
                  title: 'No reports yet',
                  message: 'A report is generated once you have run a session.',
                  compact: true,
                )
              else
                ...data.courses.map(
                  (course) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _ReportCard(
                      course: course,
                      colorScheme: colorScheme,
                      isExporting: exportingCourseId == course.id,
                      onExport: () async {
                        final messenger = ScaffoldMessenger.of(context);
                        final error = await ref
                            .read(courseExportProvider.notifier)
                            .exportRegister(course.id, course.code);
                        if (error != null) {
                          messenger.showSnackBar(
                            SnackBar(content: Text('Export failed: $error')),
                          );
                        }
                      },
                      onTap: () =>
                          context.push('/lecturer/reports/course/${course.id}'),
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

class _ReportCard extends StatelessWidget {
  final LecturerCourse course;
  final ColorScheme colorScheme;
  final VoidCallback onTap;
  final VoidCallback onExport;
  final bool isExporting;

  const _ReportCard({
    required this.course,
    required this.colorScheme,
    required this.onTap,
    required this.onExport,
    required this.isExporting,
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
          border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
        ),
        child: Row(
          children: [
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
                    '${course.code} · ${course.enrolledCount} enrolled · ${course.avgAttendance}% avg',
                    style: AppTheme.accent(
                      size: 10,
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
            ),
            // Per-student attendance register CSV (exam eligibility list).
            isExporting
                ? const Padding(
                    padding: EdgeInsets.all(12),
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    ),
                  )
                : IconButton(
                    tooltip: 'Export attendance register (CSV)',
                    icon: const Icon(Icons.download_rounded),
                    onPressed: onExport,
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
