import 'package:flutter/material.dart';

/// Shared present/late/absent/excused -> (color, label) mapping, used by
/// every screen that renders a RecentAttendance record (records list,
/// course detail, session detail) so the three can't drift out of sync.
Color attendanceStatusColor(String status) {
  switch (status) {
    case 'present':
      return const Color(0xFF10B981); // Emerald Green
    case 'late':
      return const Color(0xFFF59E0B); // Amber
    case 'excused':
      return const Color(0xFF6B7280); // Neutral Gray
    case 'absent':
    default:
      return const Color(0xFFEF4444); // Crimson Red
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
