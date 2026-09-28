import 'package:flutter/material.dart';

import 'package:suaams/shared/utils/attendance_status.dart';

/// How a stat box reads. Replaces the two incompatible conventions the
/// five private `_StatBox` copies had grown:
///
///   * a `highlight` bool meaning "make it green" (4 copies), and
///   * `final isWarning = label == 'MISSED'` -- deriving a visual state
///     from a display string (student_home_screen). Rename that label and
///     the red treatment silently disappears.
///
/// Tone is explicit and survives copy edits.
enum AppStatTone { neutral, success, warning }

/// One stat: a value and the label under it.
class AppStatValue {
  final String value;
  final String label;
  final AppStatTone tone;

  const AppStatValue(this.value, this.label, {this.tone = AppStatTone.neutral});

  const AppStatValue.success(this.value, this.label)
    : tone = AppStatTone.success;

  const AppStatValue.warning(this.value, this.label)
    : tone = AppStatTone.warning;
}

/// A row of stat boxes, evenly spaced and equal width.
///
/// There were four private grid variants (`_StatsGrid` x2, `_SummaryGrid`,
/// `_WorkspaceStatsGrid`) that differed only in which model they read and
/// in whether they passed `highlight`. The data-shaping stays at the call
/// site; only the layout lives here.
class AppStatRow extends StatelessWidget {
  final List<AppStatValue> stats;
  final double gap;

  const AppStatRow(this.stats, {super.key, this.gap = 12});

  @override
  Widget build(BuildContext context) {
    // IntrinsicHeight is load-bearing, not an optimisation. The Row below
    // uses CrossAxisAlignment.stretch to give every box the same height, and
    // stretch needs a BOUNDED cross axis -- but this row is laid out inside
    // a SingleChildScrollView on both home screens, which is unbounded on
    // the vertical. Without IntrinsicHeight to supply a bounded height,
    // RenderFlex throws during layout and takes the whole column with it.
    //
    // The cost is one extra layout pass over three small boxes, which is
    // not measurable against a network round-trip.
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < stats.length; i++) ...[
            if (i > 0) SizedBox(width: gap),
            Expanded(child: AppStatBox(stats[i])),
          ],
        ],
      ),
    );
  }
}

class AppStatBox extends StatelessWidget {
  final AppStatValue stat;

  const AppStatBox(this.stat, {super.key});

  @override
  Widget build(BuildContext context) {
    // One Theme.of lookup rather than two -- each registers the same
    // dependency, so splitting it buys nothing.
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    final textTheme = theme.textTheme;

    final Color accent;
    switch (stat.tone) {
      case AppStatTone.success:
        accent = AppStatus.success;
      case AppStatTone.warning:
        accent = colorScheme.error;
      case AppStatTone.neutral:
        accent = colorScheme.onSurface;
    }

    final isNeutral = stat.tone == AppStatTone.neutral;

    return Container(
      padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 6),
      decoration: BoxDecoration(
        color: isNeutral
            ? colorScheme.surfaceContainer.withValues(alpha: 0.78)
            : accent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isNeutral
              ? colorScheme.outline.withValues(alpha: 0.14)
              : accent.withValues(alpha: 0.35),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            stat.value,
            maxLines: 1,
            // No FittedBox here on purpose. These values are percentages and
            // counts -- "92%", "1248" -- at titleLarge in roughly a third of
            // the screen width, none of which come close to overflowing on a
            // 360dp phone. A FittedBox would measure the child unbounded and
            // then scale, which is a second measuring pass, and it sits
            // INSIDE the IntrinsicHeight above, so the two stack. A 4-digit
            // number is ~45px against ~100px of space. If a value ever does
            // grow, ellipsising it here is a visible bug worth finding, which
            // is the better outcome anyway.
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w700,
              color: accent,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            stat.label,
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            // labelSmall is 11sp -- up from the 8sp these boxes used, which
            // was the floor violation flagged in the design review. Uppercase
            // is kept here (unlike the nav labels) because these are short
            // all-caps run-ins under a numeric value, and the wide tracking
            // is what makes them readable at this size.
            style: textTheme.labelSmall?.copyWith(
              fontSize: 10,
              letterSpacing: 0.6,
              color: isNeutral
                  ? colorScheme.onSurface.withValues(alpha: 0.55)
                  : accent.withValues(alpha: 0.9),
            ),
          ),
        ],
      ),
    );
  }
}
