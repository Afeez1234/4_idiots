import 'package:flutter/material.dart';

import 'package:suaams/core/theme/app_theme.dart';

/// A label on the left, a value on the right — the read-only detail line
/// used on the ID card, the session detail sheet, and profile info cards.
///
/// This was three private copies: `_IdRow` (student_id_card_screen) and
/// `_InfoRow` (lecturer_profile_screen) were byte-identical, and
/// `_DetailRow` (session_detail_screen) was the same shape at a different
/// size that also hardcoded `Colors.grey` for its label — roughly 2.8:1
/// against a white surface in light mode, well under the 4.5:1 AA floor
/// for body text. The label now reads from the theme instead.
///
/// The value is the accent face, because these values are data: matric
/// numbers, session ids, registration codes.
class AppLabelValueRow extends StatelessWidget {
  final String label;
  final String value;
  final EdgeInsetsGeometry padding;

  /// Whether to uppercase the value. The ID card wants this (matric
  /// numbers are printed in caps); the session detail did not.
  final bool uppercaseValue;

  const AppLabelValueRow(
    this.label,
    this.value, {
    super.key,
    this.padding = EdgeInsets.zero,
    this.uppercaseValue = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Padding(
      padding: padding,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: textTheme.labelSmall?.copyWith(
              letterSpacing: 1.0,
              color: colorScheme.onSurface.withValues(alpha: 0.55),
            ),
          ),
          const SizedBox(width: 12),
          Flexible(
            child: Text(
              uppercaseValue ? value.toUpperCase() : value,
              textAlign: TextAlign.end,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppTheme.accent(
                size: 14,
                weight: FontWeight.w700,
                color: colorScheme.onSurface,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
