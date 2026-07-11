import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final themeProvider = NotifierProvider<ThemeNotifier, ThemeMode>(
  ThemeNotifier.new,
);

class ThemeNotifier extends Notifier<ThemeMode> {
  final _storage = const FlutterSecureStorage();

  @override
  ThemeMode build() {
    // Load saved theme on app start
    _loadTheme();
    return ThemeMode.dark; // default while loading
  }

  Future<void> _loadTheme() async {
    final saved = await _storage.read(key: 'theme_mode');
    if (saved == 'light') {
      state = ThemeMode.light;
    } else {
      state = ThemeMode.dark;
    }
  }

  Future<void> toggleTheme() async {
    final newTheme = state == ThemeMode.light ? ThemeMode.dark : ThemeMode.light;
    state = newTheme;
    await _storage.write(
      key: 'theme_mode',
      value: newTheme == ThemeMode.light ? 'light' : 'dark',
    );
  }
}