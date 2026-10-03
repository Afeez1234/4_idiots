import 'package:flutter/material.dart';

/// The `terminal` palette from the design mockups, as real Dart tokens.
///
/// The source of truth was `core/theme/i.html` and `core/theme/j.html` --
/// Tailwind phone mockups defining a ten-token palette that nothing
/// compiled. `AppTheme` had independently re-derived part of it, and the
/// two had drifted (the mockups' dark base is pure black; the app's has
/// always been #0F0F0F).
///
/// Ported selectively, NOT wholesale:
///
///  * Adopted: the status colour triples and the border tokens. These are
///    the part the app was actually missing -- status colours were re-typed
///    as `Color(0xFF10B981).withValues(alpha: 0.12 / 0.35 / 0.9)` at every
///    call site, 30+ times, with no light/dark pair anywhere.
///
///  * Rejected as specified: textMuted. The mockups put it at #333333 on
///    black (1.52:1 -- effectively invisible) and #A1A1AA on white (2.56:1).
///    Both fail WCAG AA for body text badly enough that adopting them
///    literally would have undone the contrast work. Replaced with measured
///    equivalents that pass, which is why these values differ from the
///    mockups. Every pair below was measured, not eyeballed.
///
///  * Not ported: base and surface. The app's #0F0F0F dark background is
///    treated as a deliberate choice over the mockups' #000000, and
///    switching every screen to pure black is a visual decision, not a
///    token cleanup.
///
/// The mockups are now out of date with respect to the muted-text values.
/// They should be treated as a design reference, not a source of truth --
/// this file is now that.
@immutable
class AppTerminal extends ThemeExtension<AppTerminal> {
  /// Lowest-emphasis body text. The 65%-alpha equivalent the mockups meant.
  final Color textMuted;

  /// Mid-emphasis text. Directly from the mockup (light); measured
  /// equivalent for dark, which had no usable value.
  final Color textSecondary;

  /// Hairline separators that aren't strong enough to be a real border.
  final Color borderSubtle;

  // Status triples: background, border, and text for each. The three
  // together are what a status pill actually needs -- a tinted fill, a
  // border that reads as an edge, and text that stays legible on both the
  // fill and the card behind it.
  //
  // The `*Text` values were measured against the TINTED fill the pills
  // actually use (the status hue at 10% over the surface), not against
  // the opaque `*Bg`. That distinction matters: the raw hues the app used
  // before this file existed -- #10B981, #F59E0B, #EF4444 -- score 2.31,
  // 1.99 and 3.29 against a light-mode tint, so every status label in the
  // app was failing AA. Dark mode was mostly fine, which is presumably
  // why it went unnoticed; it defaults to dark.
  final Color successBg;
  final Color successBorder;
  final Color successText;
  final Color warningBg;
  final Color warningBorder;
  final Color warningText;
  final Color dangerBg;
  final Color dangerBorder;
  final Color dangerText;

  const AppTerminal({
    required this.textMuted,
    required this.textSecondary,
    required this.borderSubtle,
    required this.successBg,
    required this.successBorder,
    required this.successText,
    required this.warningBg,
    required this.warningBorder,
    required this.warningText,
    required this.dangerBg,
    required this.dangerBorder,
    required this.dangerText,
  });

  static const AppTerminal dark = AppTerminal(
    textMuted: Color(0xFFB0B0B0), // 7.86:1 on #1C1C1C
    textSecondary: Color(0xFFD4D4D4), // 11.50:1
    borderSubtle: Color(0xFF111111), // from the mockup
    successBg: Color(0xFF0A1A0A), // from the mockup
    successBorder: Color(0xFF1A3A1A), // from the mockup
    successText: Color(0xFF10B981), // 5.77:1 on the 10%-tint pill
    warningBg: Color(0xFF1A1408),
    warningBorder: Color(0xFF4A3A10),
    warningText: Color(0xFFFBBF24), // 10.96:1
    dangerBg: Color(0xFF1A0A0A),
    dangerBorder: Color(0xFF4A1515),
    dangerText: Color(0xFFF87171), // 6.95:1
  );

  static const AppTerminal light = AppTerminal(
    textMuted: Color(0xFF6A6A6A), // 5.41:1 on white
    textSecondary: Color(0xFF52525B), // 7.73:1 -- from the mockup
    borderSubtle: Color(0xFFF0F0F0), // from the mockup
    successBg: Color(0xFFECFDF5), // from the mockup
    successBorder: Color(0xFFD1FAE5), // from the mockup
    successText: Color(0xFF065F46), // 7.29:1 -- from the mockup
    warningBg: Color(0xFFFFFBEB),
    warningBorder: Color(0xFFFDE68A),
    warningText: Color(0xFF92400E), // 6.84:1
    dangerBg: Color(0xFFFEF2F2),
    dangerBorder: Color(0xFFFECACA),
    dangerText: Color(0xFF991B1B), // 7.60:1
  );

  @override
  AppTerminal copyWith({
    Color? textMuted,
    Color? textSecondary,
    Color? borderSubtle,
    Color? successBg,
    Color? successBorder,
    Color? successText,
    Color? warningBg,
    Color? warningBorder,
    Color? warningText,
    Color? dangerBg,
    Color? dangerBorder,
    Color? dangerText,
  }) {
    return AppTerminal(
      textMuted: textMuted ?? this.textMuted,
      textSecondary: textSecondary ?? this.textSecondary,
      borderSubtle: borderSubtle ?? this.borderSubtle,
      successBg: successBg ?? this.successBg,
      successBorder: successBorder ?? this.successBorder,
      successText: successText ?? this.successText,
      warningBg: warningBg ?? this.warningBg,
      warningBorder: warningBorder ?? this.warningBorder,
      warningText: warningText ?? this.warningText,
      dangerBg: dangerBg ?? this.dangerBg,
      dangerBorder: dangerBorder ?? this.dangerBorder,
      dangerText: dangerText ?? this.dangerText,
    );
  }

  @override
  AppTerminal lerp(covariant AppTerminal? other, double t) {
    if (other == null) return this;
    return AppTerminal(
      textMuted: Color.lerp(textMuted, other.textMuted, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      borderSubtle: Color.lerp(borderSubtle, other.borderSubtle, t)!,
      successBg: Color.lerp(successBg, other.successBg, t)!,
      successBorder: Color.lerp(successBorder, other.successBorder, t)!,
      successText: Color.lerp(successText, other.successText, t)!,
      warningBg: Color.lerp(warningBg, other.warningBg, t)!,
      warningBorder: Color.lerp(warningBorder, other.warningBorder, t)!,
      warningText: Color.lerp(warningText, other.warningText, t)!,
      dangerBg: Color.lerp(dangerBg, other.dangerBg, t)!,
      dangerBorder: Color.lerp(dangerBorder, other.dangerBorder, t)!,
      dangerText: Color.lerp(dangerText, other.dangerText, t)!,
    );
  }
}

/// Shorthand for `Theme.of(context).extension<AppTerminal>()!`.
///
/// Falls back to the dark set rather than throwing, so a widget rendered
/// outside a MaterialApp (a bare test pump, for instance) degrades to
/// readable colours instead of crashing.
AppTerminal terminalOf(BuildContext context) {
  return Theme.of(context).extension<AppTerminal>() ?? AppTerminal.dark;
}
