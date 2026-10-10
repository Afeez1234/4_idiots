import 'package:flutter/material.dart';

/// Loading placeholders shaped like the content they stand in for.
///
/// A spinner says "something is happening"; a skeleton also says what is
/// about to appear and where, so the screen doesn't jump when data lands.
/// Use it for a screen's FIRST load only. Once real data has been shown, a
/// refresh should keep that data on screen rather than swap back to a
/// skeleton -- see loadDashboardData in student_provider.dart.
///
/// Keep spinners where a spinner is the honest signal: inside buttons, the
/// splash/login flow, and the check-in sheet.

/// Pulses its child's opacity while content loads.
///
/// A fade rather than a moving shimmer gradient: FadeTransition only
/// changes the opacity of an already-painted layer, so each frame is a
/// cheap compositing step instead of a repaint with a shader. The
/// RepaintBoundary keeps even that from touching the parent -- without it
/// the pulse would repaint the DashboardBackground grid and glows behind
/// it every frame, the same problem CLAUDE.md describes for a blinking
/// TextField cursor.
///
/// Honours the system "remove animations" setting: with it on, the
/// placeholders are drawn once at mid opacity and never animate.
class SkeletonPulse extends StatefulWidget {
  final Widget child;

  const SkeletonPulse({super.key, required this.child});

  @override
  State<SkeletonPulse> createState() => _SkeletonPulseState();
}

class _SkeletonPulseState extends State<SkeletonPulse>
    with SingleTickerProviderStateMixin {
  // Field initialiser, not late-in-initState, so the controller exists for
  // the whole State lifetime and dispose() can never see it unset.
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  );

  late final Animation<double> _opacity = Tween<double>(
    begin: 0.45,
    end: 1,
  ).animate(CurvedAnimation(parent: _controller, curve: Curves.easeInOut));

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // Read here rather than in initState: MediaQuery is an inherited
    // dependency, and the user can toggle reduced motion while the
    // skeleton is on screen.
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller
        ..stop()
        ..value = 0.5;
    } else if (!_controller.isAnimating) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepaintBoundary(
      // Screen readers would otherwise find a run of empty boxes. One
      // label for the whole placeholder tells them what's going on.
      child: Semantics(
        label: 'Loading',
        excludeSemantics: true,
        child: FadeTransition(opacity: _opacity, child: widget.child),
      ),
    );
  }
}

/// One grey block: a line of text, an avatar, a badge.
///
/// Static on its own -- wrap a whole group of these in a single
/// [SkeletonPulse] so they fade together with one animation controller,
/// rather than giving every block its own.
class SkeletonBox extends StatelessWidget {
  final double? width;
  final double height;
  final double radius;

  const SkeletonBox({
    super.key,
    this.width,
    required this.height,
    this.radius = 6,
  });

  /// A circle, for avatars and icon buttons.
  const SkeletonBox.circle({super.key, required double size})
    : width = size,
      height = size,
      radius = size / 2;

  @override
  Widget build(BuildContext context) {
    // onSurface at low alpha rather than a fixed grey, so the same
    // placeholder reads as a soft block on both the midnight-black and the
    // light theme.
    final color = Theme.of(
      context,
    ).colorScheme.onSurface.withValues(alpha: 0.08);
    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}

/// What sits at the right-hand end of a [SkeletonListCard], matching the
/// real row it stands in for.
enum SkeletonTrailing {
  /// A status pill or time badge (today's protocol, records).
  pill,

  /// A navigation chevron (timetable day tiles).
  chevron,

  /// A short line of text (a class's time range).
  text,
}

/// A list-row placeholder matching the app's standard card: rounded
/// container, a title line and a short subtitle line, and something on the
/// right. Used for "today's protocol", records, the timetable and similar
/// lists.
class SkeletonListCard extends StatelessWidget {
  final SkeletonTrailing trailing;

  /// A small circle before the text, for rows that start with a status dot
  /// (the attendance records list).
  final bool leadingDot;

  const SkeletonListCard({
    super.key,
    this.trailing = SkeletonTrailing.pill,
    this.leadingDot = false,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
      ),
      child: Row(
        children: [
          if (leadingDot) ...[
            const SkeletonBox.circle(size: 12),
            const SizedBox(width: 16),
          ],
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Fractional widths so the lines look like text of
                // varying length instead of a uniform stripe.
                FractionallySizedBox(
                  widthFactor: 0.6,
                  child: SkeletonBox(height: 14),
                ),
                SizedBox(height: 8),
                FractionallySizedBox(
                  widthFactor: 0.35,
                  child: SkeletonBox(height: 10),
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          switch (trailing) {
            SkeletonTrailing.pill => const SkeletonBox(width: 64, height: 26),
            SkeletonTrailing.chevron => const SkeletonBox(
              width: 14,
              height: 14,
              radius: 3,
            ),
            SkeletonTrailing.text => const SkeletonBox(width: 84, height: 12),
          },
        ],
      ),
    );
  }
}

/// [count] list cards under one pulse.
class SkeletonList extends StatelessWidget {
  final int count;
  final SkeletonTrailing trailing;
  final bool leadingDot;

  const SkeletonList({
    super.key,
    this.count = 3,
    this.trailing = SkeletonTrailing.pill,
    this.leadingDot = false,
  });

  @override
  Widget build(BuildContext context) {
    return SkeletonPulse(
      child: Column(
        children: [
          for (var i = 0; i < count; i++)
            SkeletonListCard(trailing: trailing, leadingDot: leadingDot),
        ],
      ),
    );
  }
}
