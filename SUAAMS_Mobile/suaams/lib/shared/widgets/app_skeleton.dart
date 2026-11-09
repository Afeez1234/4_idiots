import 'dart:async';

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

/// The line a long first load shows, so a wait reads as "the server is
/// slow" rather than "the app has hung".
///
/// Added 2026-11-01. A cold Render start kept lecturer Home on a bare
/// spinner for about a minute with no words, long enough that a lecturer in
/// front of a hall would kill the app and restart the wait. The app can't
/// tell a cold server from slow Wi-Fi, so the copy says "may".
///
/// Invisible for [delay], then fades in (instantly with reduced motion).
/// Hidden from screen readers until it shows, then announced once as a
/// polite live region.
class SlowLoadHint extends StatefulWidget {
  final Duration delay;

  const SlowLoadHint({super.key, this.delay = const Duration(seconds: 5)});

  static const message =
      'Still loading. The server may be waking up; this can take up to a '
      'minute.';

  @override
  State<SlowLoadHint> createState() => _SlowLoadHintState();
}

class _SlowLoadHintState extends State<SlowLoadHint> {
  Timer? _timer;
  bool _shown = false;

  @override
  void initState() {
    super.initState();
    _timer = Timer(widget.delay, () {
      if (mounted) setState(() => _shown = true);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final reduceMotion = MediaQuery.disableAnimationsOf(context);
    return ExcludeSemantics(
      excluding: !_shown,
      child: Semantics(
        liveRegion: true,
        child: AnimatedOpacity(
          opacity: _shown ? 1 : 0,
          duration: reduceMotion
              ? Duration.zero
              : const Duration(milliseconds: 280),
          curve: Curves.easeOutCubic,
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: colorScheme.surfaceContainer,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: colorScheme.outline.withValues(alpha: 0.1),
              ),
            ),
            child: Row(
              children: [
                Icon(
                  Icons.cloud_sync_rounded,
                  size: 18,
                  color: colorScheme.onSurface.withValues(alpha: 0.7),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    SlowLoadHint.message,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurface.withValues(alpha: 0.7),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Places a [SlowLoadHint] at the bottom of a skeleton, above it in the
/// stack so the skeleton keeps its exact loaded-screen layout.
class WithSlowLoadHint extends StatelessWidget {
  final Widget child;

  const WithSlowLoadHint({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        child,
        const Positioned(
          left: 24,
          right: 24,
          bottom: 24,
          child: SlowLoadHint(),
        ),
      ],
    );
  }
}

/// A whole screen's first load: list-card placeholders and the slow-load
/// hint. Replaced the bare `CircularProgressIndicator` that 18 screens
/// returned on first load (2026-11-01).
///
/// With [scaffold] (the default) it brings its own app bar, so a pushed
/// screen has its back button while it loads, which the bare spinner
/// Scaffold didn't. Pass the loaded screen's [title] when it is fixed
/// ("Timetable"); leave it null when it comes from the data. Use
/// `scaffold: false` inside a screen that already has its Scaffold.
class AppLoadingView extends StatelessWidget {
  final String? title;
  final bool scaffold;
  final int rows;
  final SkeletonTrailing trailing;

  const AppLoadingView({
    super.key,
    this.title,
    this.scaffold = true,
    this.rows = 4,
    this.trailing = SkeletonTrailing.chevron,
  });

  @override
  Widget build(BuildContext context) {
    final body = WithSlowLoadHint(
      child: SingleChildScrollView(
        physics: const NeverScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        child: SkeletonList(count: rows, trailing: trailing),
      ),
    );
    if (!scaffold) return body;
    final colorScheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: title == null ? null : Text(title!),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: body,
    );
  }
}
