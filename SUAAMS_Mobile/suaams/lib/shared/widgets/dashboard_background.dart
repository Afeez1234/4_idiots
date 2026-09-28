import 'package:flutter/material.dart';

import 'package:suaams/shared/utils/grid_overlay_painter.dart';

/// Which size/tint of the decorative glow pair to draw.
enum AppBackgroundVariant {
  /// Compact glows, sized for a dense screen with real content on it
  /// (the home dashboards). This is what the first two dashboards used.
  dashboard,

  /// Larger glows for a mostly-empty screen where the background is a
  /// large share of the composition -- login, splash.
  auth,

  /// Same as [auth], but the top-right glow is red rather than indigo.
  /// Used by change-password, where the screen is a security interstitial
  /// and the red reads as "be careful" without saying anything.
  authAlert,
}

/// Shared background: base surface + two decorative circles + grid overlay.
///
/// This was three more private classes before it was consolidated --
/// `_LoginBackground`, `_SplashBackground` and `_ChangePasswordBackground`
/// were each a near-verbatim copy of this with different circle sizes,
/// while two earlier dashboard copies had already been pulled out. The
/// differences were only size and one colour, both of which are now the
/// [variant] parameter, so a change to the treatment lands everywhere at
/// once.
class DashboardBackground extends StatelessWidget {
  final bool isDarkMode;
  final ColorScheme colorScheme;
  final AppBackgroundVariant variant;

  const DashboardBackground({
    super.key,
    required this.isDarkMode,
    required this.colorScheme,
    this.variant = AppBackgroundVariant.dashboard,
  });

  @override
  Widget build(BuildContext context) {
    final isAuth = variant != AppBackgroundVariant.dashboard;
    final isAlert = variant == AppBackgroundVariant.authAlert;

    // Compact on dashboards, oversized on the auth screens.
    const primarySize = 170.0;
    const secondarySize = 130.0;
    final scale = isAuth ? 250 / primarySize : 1.0;

    final primaryDark = isAlert
        ? const Color(0xFF140A0A)
        : const Color(0xFF0A0A14);
    final primaryLight = isAlert
        ? const Color(0xFFFFE0E0)
        : const Color(0xFFE0E7FF);
    final secondaryDark = isAlert
        ? const Color(0xFF100808)
        : const Color(0xFF080810);

    return Stack(
      children: [
        Positioned.fill(
          child: Container(
            decoration: BoxDecoration(color: colorScheme.surface),
          ),
        ),
        Positioned(
          top: -55 * scale,
          right: -45 * scale,
          child: Container(
            width: primarySize * scale,
            height: primarySize * scale,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? primaryDark.withValues(alpha: 0.6)
                  : primaryLight.withValues(alpha: 0.75),
            ),
          ),
        ),
        Positioned(
          bottom: -35 * scale,
          left: -25 * scale,
          child: Container(
            width: secondarySize * scale,
            height: secondarySize * scale,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? secondaryDark.withValues(alpha: 0.65)
                  : const Color(0xFFFEF3C7).withValues(alpha: 0.55),
            ),
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              // const painter instance per branch -- see
              // grid_overlay_painter.dart on why this is safe.
              painter: isDarkMode
                  ? const GridOverlayPainter(color: Colors.white)
                  : const GridOverlayPainter(color: Colors.black),
            ),
          ),
        ),
      ],
    );
  }
}
