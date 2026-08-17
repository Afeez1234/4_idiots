import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/models/available_course_model.dart';
import 'package:suaams/features/student/providers/course_registration_provider.dart';

// Self-service course registration -- see get_available_courses/
// register_course/drop_course in api/student.py. Scoped server-side to the
// student's own department + the active semester, so every row here is
// something this student is actually allowed to take.
class CourseRegistrationScreen extends ConsumerWidget {
  const CourseRegistrationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(courseRegistrationProvider);
    final colorScheme = Theme.of(context).colorScheme;

    // Mutation (register/drop) failures surface as a SnackBar rather than
    // replacing the list -- the list itself is still valid, only one
    // action on it failed.
    ref.listen(courseRegistrationProvider, (previous, next) {
      if (next.errorMessage != null &&
          next.errorMessage != previous?.errorMessage &&
          !next.isLoading) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(next.errorMessage!)),
        );
      }
    });

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Course Registration'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: RefreshIndicator(
        onRefresh: () =>
            ref.read(courseRegistrationProvider.notifier).loadAvailableCourses(),
        child: _buildBody(context, ref, state, colorScheme),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    WidgetRef ref,
    CourseRegistrationState state,
    ColorScheme colorScheme,
  ) {
    if (state.isLoading && state.courses.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (state.errorMessage != null && state.courses.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 80),
          Icon(
            Icons.error_outline_rounded,
            size: 40,
            color: colorScheme.onSurface.withValues(alpha: 0.3),
          ),
          const SizedBox(height: 12),
          Center(
            child: Text(
              state.errorMessage!,
              textAlign: TextAlign.center,
              style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.6)),
            ),
          ),
        ],
      );
    }

    if (state.courses.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          const SizedBox(height: 80),
          Center(
            child: Text(
              'No courses available for registration this semester.',
              textAlign: TextAlign.center,
              style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5)),
            ),
          ),
        ],
      );
    }

    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(24),
      itemCount: state.courses.length,
      itemBuilder: (context, index) {
        final course = state.courses[index];
        final isPending = state.pendingCourseIds.contains(course.id);
        return _CourseRow(
          course: course,
          isPending: isPending,
          colorScheme: colorScheme,
          onRegister: () =>
              ref.read(courseRegistrationProvider.notifier).register(course.id),
          onDrop: () =>
              ref.read(courseRegistrationProvider.notifier).drop(course.id),
        );
      },
    );
  }
}

class _CourseRow extends StatelessWidget {
  final AvailableCourse course;
  final bool isPending;
  final ColorScheme colorScheme;
  final VoidCallback onRegister;
  final VoidCallback onDrop;

  const _CourseRow({
    required this.course,
    required this.isPending,
    required this.colorScheme,
    required this.onRegister,
    required this.onDrop,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: colorScheme.surface,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
                      ),
                      child: Text(
                        course.courseCode,
                        style: const TextStyle(
                          fontFamily: 'JetBrains Mono',
                          fontSize: 12,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    if (course.creditUnits != null) ...[
                      const SizedBox(width: 8),
                      Text(
                        '${course.creditUnits} UNITS',
                        style: TextStyle(
                          fontSize: 10,
                          letterSpacing: 0.5,
                          fontWeight: FontWeight.bold,
                          color: colorScheme.onSurface.withValues(alpha: 0.4),
                        ),
                      ),
                    ],
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  course.courseTitle,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
                ),
                if (course.lecturer != null) ...[
                  const SizedBox(height: 4),
                  Text(
                    course.lecturer!,
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(width: 12),
          _ActionButton(
            enrolled: course.enrolled,
            isPending: isPending,
            onRegister: onRegister,
            onDrop: onDrop,
          ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final bool enrolled;
  final bool isPending;
  final VoidCallback onRegister;
  final VoidCallback onDrop;

  const _ActionButton({
    required this.enrolled,
    required this.isPending,
    required this.onRegister,
    required this.onDrop,
  });

  @override
  Widget build(BuildContext context) {
    if (isPending) {
      return const SizedBox(
        width: 36,
        height: 36,
        child: Padding(
          padding: EdgeInsets.all(8),
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }

    if (enrolled) {
      return OutlinedButton(
        onPressed: onDrop,
        style: OutlinedButton.styleFrom(
          foregroundColor: const Color(0xFFEF4444),
          side: const BorderSide(color: Color(0xFFEF4444)),
        ),
        child: const Text('DROP'),
      );
    }

    return FilledButton(
      onPressed: onRegister,
      child: const Text('REGISTER'),
    );
  }
}
