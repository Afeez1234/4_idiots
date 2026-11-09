import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

// Holds the app to DESIGN.md's colour and depth rules the way
// SUAAMS/tests/test_templates.py holds the portal to them. Added 2026-11-01,
// after a critique found green spent on "live", amber on a decorative chip
// and drop shadows on a flat UI -- each one a rule the docs already stated.

/// Every Dart file under lib/, as (path with forward slashes, source).
List<(String, String)> _sources() => Directory('lib')
    .listSync(recursive: true)
    .whereType<File>()
    .where((f) => f.path.endsWith('.dart'))
    .map((f) => (f.path.replaceAll(r'\', '/'), f.readAsStringSync()))
    .toList();

/// Files allowed to use the attendance colours. Green means present (or an
/// attendance figure at or above 75%), amber means late (or below 75%).
/// A new entry here should be an attendance figure or the check-in sheet's
/// outcome -- never a live class, a binding, a lifecycle state or
/// decoration. Those take indigo (`colorScheme.primary`) or neutral.
const _attendanceColourFiles = {
  'lib/shared/utils/attendance_status.dart', // the one map
  'lib/core/theme/app_terminal.dart', // defines successText/warningText
  'lib/shared/widgets/app_stat_box.dart', // success/warning stat tones
  'lib/features/student/presentation/views/nfc_broadcast_sheet.dart',
  'lib/features/student/presentation/student_home_screen.dart',
  'lib/features/student/presentation/views/courses_view.dart',
  'lib/features/student/presentation/views/course_detail_screen.dart',
  'lib/features/lecturer/presentation/views/course_analytics_screen.dart',
  'lib/features/lecturer/presentation/views/lecturer_session_history_screen.dart',
  // Amber only, for real warnings (no phone bound, passcode-only check-in).
  'lib/features/student/presentation/views/profile_view_screen.dart',
};

void main() {
  test('no raw Material status hues (use the theme or attendance map)', () {
    final raw = RegExp(r'Colors\.(amber|green|orange|red|yellow)\b');
    final hits = [
      for (final (path, src) in _sources())
        if (raw.hasMatch(src)) path,
    ];
    expect(hits, isEmpty, reason: 'raw status hues in: $hits');
  });

  test('no box shadows: app surfaces are flat, depth comes from tone', () {
    final hits = [
      for (final (path, src) in _sources())
        if (src.contains('boxShadow:')) path,
    ];
    expect(hits, isEmpty, reason: 'boxShadow in: $hits');
  });


  test('attendance colours stay on attendance', () {
    // Both spellings: the raw AppStatus hues and the theme's text shades
    // (terminal.successText), which is how live-in-green on lecturer Home
    // slipped past the first version of this test.
    final use = RegExp(
      r'AppStatus\.(success|warning)\b|\.(successText|warningText)\b',
    );
    final hits = [
      for (final (path, src) in _sources())
        if (use.hasMatch(src) && !_attendanceColourFiles.contains(path)) path,
    ];
    expect(
      hits,
      isEmpty,
      reason:
          'AppStatus.success/warning outside the attendance allowlist: $hits. '
          'Live is indigo; non-attendance states are neutral.',
    );
  });
}
