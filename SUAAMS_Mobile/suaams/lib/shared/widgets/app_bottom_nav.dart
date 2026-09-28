import 'package:flutter/material.dart';

import 'package:suaams/shared/widgets/app_badge.dart';

// Shared bottom navigation for the student and lecturer shells.
//
// Generalized from the private _DashboardBottomNav/_BottomNavItem pair
// that used to live inside student_dashboard_screen.dart, so both 5-tab
// bars render identically.
//
// What this version fixes, all of it visible on every screen of the app:
//
//   * Labels read from Theme.of().textTheme instead of a hand-rolled
//     TextStyle. The old one set no fontFamily at all, so the strip
//     rendered in the platform typeface while everything behind it was in
//     the app font -- and it sat at 8sp, the smallest text in the app.
//   * Tiles are Expanded, so every tab has the same hit target. They used
//     to be sized by their own label, which gave ATTENDANCE a visibly
//     wider target than ID CARD.
//   * Press feedback. The old tile was a bare GestureDetector: nothing
//     changed on touch-down, so a tap gave no confirmation at all until
//     the screen behind it had already swapped.
//   * The active indicator animates and is actually visible. It was
//     primary @ 5% -- roughly #141414 on a #0F0F0F surface -- appearing
//     instantly, so the only active/inactive signal was text going from
//     45% opacity to full.
//   * Tabs are announced correctly to screen readers. Nothing previously
//     marked these as buttons or reported which one was selected.
class AppBottomNavItem {
  final IconData icon;
  final String label;

  /// Optional unread count, rendered as a numbered badge over the icon.
  /// Null or 0 hides it.
  final int? badgeCount;

  /// A plain dot, for "something is true here" rather than "there are N of
  /// these". Deliberately separate from [badgeCount]: a live-session dot is
  /// not an error, so it must not wear the error-red count pill, and
  /// passing 1 through the count path would render a misleading "1".
  final bool showDot;

  const AppBottomNavItem({
    required this.icon,
    required this.label,
    this.badgeCount,
    this.showDot = false,
  });
}

class AppBottomNav extends StatelessWidget {
  final List<AppBottomNavItem> items;
  final int currentIndex;
  final ValueChanged<int> onTap;

  const AppBottomNav({
    super.key,
    required this.items,
    required this.currentIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return DecoratedBox(
      decoration: BoxDecoration(
        // surfaceContainer rather than surface: the old bar used the same
        // colour as the scaffold behind it, so the only thing separating
        // the two was a 15%-alpha border.
        color: colorScheme.surfaceContainer,
        border: Border(
          top: BorderSide(color: colorScheme.outline.withValues(alpha: 0.4)),
        ),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
          child: Row(
            children: [
              for (var i = 0; i < items.length; i++)
                Expanded(
                  child: _AppBottomNavTile(
                    item: items[i],
                    active: i == currentIndex,
                    colorScheme: colorScheme,
                    onTap: () => onTap(i),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AppBottomNavTile extends StatelessWidget {
  final AppBottomNavItem item;
  final bool active;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _AppBottomNavTile({
    required this.item,
    required this.active,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final labelStyle = Theme.of(context).textTheme.labelSmall!.copyWith(
      // Active state is carried by colour and weight rather than by
      // going all-caps, which is what made the old labels a dark smear at
      // small sizes.
      color: active
          ? colorScheme.primary
          : colorScheme.onSurface.withValues(alpha: 0.55),
      fontWeight: active ? FontWeight.w700 : FontWeight.w600,
    );

    return Semantics(
      button: true,
      selected: active,
      label: item.label,
      child: AnimatedScale(
        // A small lift on the active tile, so switching tabs has some
        // sense of direction rather than one tab simply going dim.
        scale: active ? 1.0 : 0.96,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        // The boundary goes INSIDE the scale on purpose. AnimatedContainer
        // below animates colour and border, which are paint changes; with a
        // RepaintBoundary above it, that repaint is confined to this tile's
        // own layer instead of walking up to the nearest ancestor boundary
        // and dirtying the page body every time a tab is tapped. The scale
        // then acts on the finished layer, so it is a cheap re-composite
        // rather than another repaint. This is the same isolation the
        // backgrounds and text fields get elsewhere in the app.
        child: RepaintBoundary(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
            padding: const EdgeInsets.symmetric(vertical: 6),
            decoration: BoxDecoration(
              color: active
                  ? colorScheme.primary.withValues(alpha: 0.10)
                  : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: active
                    ? colorScheme.primary.withValues(alpha: 0.28)
                    : Colors.transparent,
              ),
            ),
            child: Material(
              // Transparent so the AnimatedContainer's pill shows through,
              // while still giving InkWell a Material to splash against.
              color: Colors.transparent,
              borderRadius: BorderRadius.circular(12),
              child: InkWell(
                onTap: onTap,
                borderRadius: BorderRadius.circular(12),
                splashColor: colorScheme.primary.withValues(alpha: 0.10),
                highlightColor: colorScheme.primary.withValues(alpha: 0.05),
                child: Padding(
                  // 6 + 22 + 3 + 15 + 6 ~= 52, clearing the 48dp minimum
                  // touch target vertically.
                  padding: const EdgeInsets.symmetric(
                    vertical: 6,
                    horizontal: 2,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _NavIcon(
                        icon: item.icon,
                        active: active,
                        badgeCount: item.badgeCount,
                        showDot: item.showDot,
                        colorScheme: colorScheme,
                      ),
                      const SizedBox(height: 3),
                      Text(
                        item.label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: labelStyle,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _NavIcon extends StatelessWidget {
  final IconData icon;
  final bool active;
  final int? badgeCount;
  final bool showDot;
  final ColorScheme colorScheme;

  const _NavIcon({
    required this.icon,
    required this.active,
    required this.badgeCount,
    required this.showDot,
    required this.colorScheme,
  });

  @override
  Widget build(BuildContext context) {
    final iconWidget = Icon(
      icon,
      size: 22,
      color: active
          ? colorScheme.primary
          : colorScheme.onSurface.withValues(alpha: 0.55),
    );

    final count = badgeCount;
    final hasCount = count != null && count > 0;
    if (!showDot && !hasCount) {
      return iconWidget;
    }

    // The marker itself is shared with the home header's announcements
    // button -- see shared/widgets/app_badge.dart. Only the offset differs,
    // because the nav's icon is 22px and centred in a wider tile while the
    // header's sits inside a 40dp IconButton.
    return Stack(
      clipBehavior: Clip.none,
      children: [
        iconWidget,
        Positioned(
          right: showDot ? -4 : -9,
          top: showDot ? -2 : -6,
          child: showDot
              ? AppBadge.dot(
                  background: colorScheme.primary,
                  borderColor: colorScheme.surfaceContainer,
                )
              : AppBadge.count(
                  // Error red is reserved for failure states; an unread
                  // count is neither good nor bad, so it uses the accent.
                  background: colorScheme.primary,
                  borderColor: colorScheme.surfaceContainer,
                  count: count,
                ),
        ),
      ],
    );
  }
}
