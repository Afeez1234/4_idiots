import 'package:flutter/material.dart';

// SUAAMS design system.
//
// Typography is the load-bearing part of this file. The app previously had
// no TextTheme of its own -- every screen hand-rolled a raw TextStyle --
// which produced 15 distinct font sizes across the codebase, most of them
// at or below 12sp, and an 8sp floor used for status badges and bottom-nav
// labels. Those are the hardest things on screen to read, and they were
// carrying real information.
//
// Two faces, one rule:
//   [uiFont]  Plex Sans  -- labels, buttons, body copy, stats, nav.
//   [accentFont] Plex Mono -- ONLY data that reads as machine output:
//             time ranges, session/course codes, terminal status strings.
//   Both are bundled via pubspec.yaml, not fetched by google_fonts. See the
//   comment on the `fonts:` block there for why that matters on a bad
//   wifi day in a lecture hall.
class AppTheme {
  static const Color primaryAction = Color(0xFF000000);
  static const Color surfaceLight = Color(0xFFF4F4F5);
  static const Color surfaceDark = Color(0xFF0F0F0F);

  static const String uiFont = 'IBMPlexSans';
  static const String accentFont = 'IBMPlexMono';

  // Smallest text the app is allowed to render. Anything below this is a
  // bug, not a style choice -- it is what made the 8sp nav labels and
  // PRESENT/ABSENT badges illegible.
  static const double minBodySize = 11;

  /// Accent-face text: times, codes, terminal strings. Monospace has no
  /// kerning to reclaim, so this is kept short and never used for labels.
  ///
  /// [size] is nullable and null is meaningful: it leaves fontSize unset so
  /// the style inherits from the ambient DefaultTextStyle, which is what a
  /// bare `TextStyle(fontFamily: ...)` did. Forcing a default here would
  /// silently resize every call site that previously inherited -- the mono
  /// runs sit inside already-sized Text widgets, so the size comes from
  /// there, not from here.
  static TextStyle accent({
    double? size,
    FontWeight weight = FontWeight.w400,
    Color? color,
    double letterSpacing = 0,
  }) {
    return TextStyle(
      fontFamily: accentFont,
      fontSize: size,
      fontWeight: weight,
      color: color,
      letterSpacing: letterSpacing,
    );
  }

  /// Section eyebrow -- the small all-caps run-in label above a block
  /// ("TODAY'S PROTOCOL"). The one place all-caps is safe, because it is
  /// paired with a real title rather than standing alone.
  static TextStyle eyebrow(Color color) {
    return TextStyle(
      fontSize: 11,
      letterSpacing: 1.5,
      fontWeight: FontWeight.w600,
      color: color,
    );
  }

  static TextTheme _scale(Brightness brightness) {
    final base = ThemeData(brightness: brightness).textTheme;
    return base
        .apply(fontFamily: uiFont)
        .copyWith(
          // Display/headline: the one or two words a screen is about.
          headlineSmall: base.headlineSmall?.copyWith(
            fontSize: 24,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.2,
          ),
          titleLarge: base.titleLarge?.copyWith(
            fontSize: 20,
            fontWeight: FontWeight.w700,
            letterSpacing: -0.2,
          ),
          titleMedium: base.titleMedium?.copyWith(
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
          titleSmall: base.titleSmall?.copyWith(
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
          // Body: never below 12. bodySmall is 12 rather than the M3 12
          // default only in weight, so the small sizes stay legible
          // without the colour having to compensate.
          bodyLarge: base.bodyLarge?.copyWith(fontSize: 16, height: 1.45),
          bodyMedium: base.bodyMedium?.copyWith(fontSize: 14, height: 1.45),
          bodySmall: base.bodySmall?.copyWith(fontSize: 12, height: 1.4),
          // Labels: the floor. 11sp is the smallest the app renders, and
          // bottom-nav labels sit here.
          labelLarge: base.labelLarge?.copyWith(
            fontSize: 14,
            fontWeight: FontWeight.w600,
          ),
          labelMedium: base.labelMedium?.copyWith(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.3,
          ),
          labelSmall: base.labelSmall?.copyWith(
            fontSize: 11,
            fontWeight: FontWeight.w600,
            letterSpacing: 0.4,
          ),
        );
  }

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: surfaceDark,
      primaryColor: Colors.white,
      fontFamily: uiFont,
      textTheme: _scale(Brightness.dark),
      cardTheme: const CardThemeData(color: Color(0xFF1C1C1C), elevation: 0),
      colorScheme: const ColorScheme.dark(
        primary: Colors.white,
        surface: surfaceDark,
        surfaceContainer: Color(0xFF1C1C1C),
        onPrimary: Colors.black,
        onSurface: Colors.white,
        outline: Color(0xFF2A2A2A),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF1C1C1C),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Colors.white, width: 1),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFFF5252), width: 1.5),
        ),
        labelStyle: const TextStyle(color: Color(0xFF8A8A8A)),
        hintStyle: const TextStyle(color: Color(0xFF6E6E6E)),
      ),
    );
  }

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: surfaceLight,
      primaryColor: primaryAction,
      fontFamily: uiFont,
      textTheme: _scale(Brightness.light),
      cardTheme: const CardThemeData(color: Colors.white, elevation: 0),
      colorScheme: const ColorScheme.light(
        primary: primaryAction,
        surface: surfaceLight,
        surfaceContainer: Colors.white,
        onPrimary: Colors.white,
        onSurface: Color(0xFF1A1A1A),
        outline: Color(0xFFDDDDDD),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF000000), width: 1),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFFF5252), width: 1.5),
        ),
        labelStyle: const TextStyle(color: Color(0xFF6E6E6E)),
        hintStyle: const TextStyle(color: Color(0xFF9A9A9A)),
      ),
    );
  }
}
