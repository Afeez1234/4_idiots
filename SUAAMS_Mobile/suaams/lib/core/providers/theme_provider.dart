import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Profile > System preferences > Interface theme: Automatic (follow the
/// phone), Dark or Light.
///
/// The value is read BEFORE the first frame (readThemeMode() in main.dart),
/// the same way card privacy and onboarding are. It used to load lazily,
/// starting dark, so anyone who'd chosen light saw a dark flash on every
/// launch -- and with Automatic, that flash would hit every phone in light
/// mode.
final themeProvider = NotifierProvider<ThemeNotifier, ThemeMode>(
  ThemeNotifier.new,
);

const _themeKey = 'theme_mode';

/// Used when the student has never chosen. DARK for now, deliberately:
/// most people asked preferred the dark theme and disliked the current
/// light one, and Automatic would show light to every phone in light mode.
/// Switch to ThemeMode.system once the light theme has been reworked --
/// existing explicit choices are unaffected either way.
const ThemeMode defaultThemeMode = ThemeMode.dark;

/// Reads the saved choice. Nothing saved (or unreadable) means
/// [defaultThemeMode].
Future<ThemeMode> readThemeMode() async {
  try {
    final saved = await const FlutterSecureStorage().read(key: _themeKey);
    return ThemeMode.values.firstWhere(
      (m) => m.name == saved,
      orElse: () => defaultThemeMode,
    );
  } catch (_) {
    return defaultThemeMode;
  }
}

class ThemeNotifier extends Notifier<ThemeMode> {
  ThemeNotifier() : _initial = defaultThemeMode;

  /// Seeded from storage in main.dart so the first frame is already right.
  ThemeNotifier.seeded(this._initial);

  final ThemeMode _initial;

  @override
  ThemeMode build() => _initial;

  void set(ThemeMode mode) {
    state = mode;
    // Stored by enum name: 'system' / 'dark' / 'light'. The old values were
    // 'dark' and 'light', so existing choices carry over unchanged.
    // Write-through without awaiting, like the other preferences.
    const FlutterSecureStorage().write(key: _themeKey, value: mode.name);
  }
}

/// Subtitle for the profile tiles. Keeps the existing mode names.
String themeModeLabel(ThemeMode mode) => switch (mode) {
  ThemeMode.system => 'Automatic (follows your phone)',
  ThemeMode.dark => 'Stealth Mode (Dark)',
  ThemeMode.light => 'Blueprint Mode (Light)',
};
