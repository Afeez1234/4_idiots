import 'package:flutter/material.dart';

import 'package:suaams/core/theme/app_terminal.dart';

/// Raw status hues, for the rare case that needs the saturated colour
/// itself rather than something meant to be read as text -- an icon fill, a
/// chart bar.
///
/// DO NOT use these for text or labels. Against the 10%-tinted fill the
/// status pills use, they score 2.31:1 (success), 1.99:1 (warning) and
/// 3.29:1 (danger) on a light surface -- all failing WCAG AA. For anything
/// that renders characters, use [attendanceStatusText].
class AppStatus {
  const AppStatus._();

  static const Color success = Color(0xFF10B981); // Emerald
  static const Color warning = Color(0xFFF59E0B); // Amber
  static const Color danger = Color(0xFFEF4444); // Crimson
  static const Color neutral = Color(0xFF6B7280); // Gray
}

/// The colour to render a status label IN -- theme-aware and contrast-
/// checked, unlike [attendanceStatusColor].
///
/// Passing the palette in rather than reading it from a BuildContext keeps
/// this usable from a pure function, and keeps the status map in one place
/// instead of spreading theme lookups across every call site.
Color attendanceStatusText(
  String status, [
  AppTerminal? palette,
]) {
  final t = palette ?? AppTerminal.dark;
  switch (status) {
    case 'present':
      return t.successText;
    case 'late':
      return t.warningText;
    case 'excused':
      return t.textSecondary;
    case 'absent':
    default:
      return t.dangerText;
  }
}

/// The background tint and border for a status pill, from the same palette.
({Color bg, Color border}) attendanceStatusSurface(
  String status, [
  AppTerminal? palette,
]) {
  final t = palette ?? AppTerminal.dark;
  switch (status) {
    case 'present':
      return (bg: t.successBg, border: t.successBorder);
    case 'late':
      return (bg: t.warningBg, border: t.warningBorder);
    case 'absent':
    default:
      return (bg: t.dangerBg, border: t.dangerBorder);
  }
}

/// Shared present/late/absent/excused -> label mapping, used by every screen
/// that renders a RecentAttendance record (records list, course detail,
/// session detail) so the four can't drift out of sync.
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
