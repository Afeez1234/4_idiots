import 'package:flutter/material.dart';

import 'package:suaams/core/theme/app_theme.dart';

/// The unread count / "something is true here" marker used on both the
/// bottom nav and the home header's announcements button.
///
/// Split out because the nav's version was private to app_bottom_nav.dart,
/// and the announcements badge needs identical behaviour in a different
/// place -- two hand-rolled copies of a badge is how they drift apart.
///
/// Wrap with a `Stack(clipBehavior: Clip.none)`; this paints itself
/// outdented from its position in the stack, so it deliberately overflows.
class AppBadge extends StatelessWidget {
  /// Null or 0 renders nothing at all.
  final int? count;

  /// Renders a plain dot instead of a numbered pill. For states that are
  /// booleans -- "a session is live" -- where a "1" would imply a quantity
  /// that does not exist, and where the error-red pill would misread as a
  /// failure.
  final bool asDot;

  final Color background;
  final Color borderColor;

  const AppBadge.count({
    super.key,
    required this.count,
    required this.background,
    required this.borderColor,
  }) : asDot = false;

  const AppBadge.dot({
    super.key,
    required this.background,
    required this.borderColor,
  })  : asDot = true,
        count = null;

  @override
  Widget build(BuildContext context) {
    if (asDot) {
      return Container(
        width: 9,
        height: 9,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: background,
          // A ring in the surrounding surface colour, so the marker stays
          // legible where it overlaps the icon glyph instead of merging
          // into it.
          border: Border.all(color: borderColor, width: 1.5),
        ),
      );
    }

    final n = count;
    if (n == null || n <= 0) return const SizedBox.shrink();

    // Past 99 the exact number stops being useful and the pill would
    // overflow its slot.
    final label = n > 99 ? '99+' : '$n';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
      constraints: const BoxConstraints(minWidth: 15),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: borderColor, width: 1.5),
      ),
      child: Text(
        label,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontFamily: AppTheme.uiFont,
          fontSize: 9,
          height: 1.2,
          fontWeight: FontWeight.w700,
          color: Colors.white,
        ),
      ),
    );
  }
}
