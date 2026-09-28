import 'package:flutter/material.dart';

/// The status palette, defined once.
///
/// These four values were previously re-typed at every call site -- 30
/// separate `Color(0xFF10B981)` literals across ten files, plus 0xFFEF4444
/// and 0xFFF59E0B scattered on top. Anything that needs "the success
/// colour" should come from here so a palette change is a one-line edit
/// rather than a sweep.
///
/// Note these are NOT in the ColorScheme. They are semantic status colours
/// rather than theme roles, and the app has no light/dark pair for them
/// yet -- see the ThemeExtension work queued against core/theme/i.html and
/// j.html, whose `terminal` palette defines successBg/successBorder/
/// successText for both themes.
class AppStatus {
  const AppStatus._();

  static const Color success = Color(0xFF10B981); // Emerald
  static const Color warning = Color(0xFFF59E0B); // Amber
  static const Color danger = Color(0xFFEF4444); // Crimson
  static const Color neutral = Color(0xFF6B7280); // Gray
}

/// Shared present/late/absent/excused -> (color, label) mapping, used by
/// every screen that renders a RecentAttendance record (records list,
/// course detail, session detail) so the three can't drift out of sync.
Color attendanceStatusColor(String status) {
  switch (status) {
    case 'present':
      return AppStatus.success;
    case 'late':
      return AppStatus.warning;
    case 'excused':
      return AppStatus.neutral;
    case 'absent':
    default:
      return AppStatus.danger;
  }
}

String attendanceStatusLabel(String status) {
  switch (status) {
    case 'present':
      return 'PRESENT';
    case 'late':
      return 'LATE';
    case 'excused':
      return 'EXCUSED';
    case 'absent':
    default:
      return 'ABSENT';
  }
}
