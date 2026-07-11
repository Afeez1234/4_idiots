import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  static const Color primaryAction = Color(0xFF000000);
  static const Color surfaceLight = Color(0xFFF4F4F5);
  static const Color surfaceDark = Color(0xFF0F0F0F);

  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: surfaceDark,
      primaryColor: Colors.white,
      textTheme: GoogleFonts.plusJakartaSansTextTheme(
        ThemeData(brightness: Brightness.dark).textTheme,
      ),
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
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
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
        labelStyle: const TextStyle(color: Color(0xFF666666)),
        hintStyle: const TextStyle(color: Color(0xFF444444)),
      ),
    );
  }

  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: surfaceLight,
      primaryColor: primaryAction,
      textTheme: GoogleFonts.plusJakartaSansTextTheme(
        ThemeData(brightness: Brightness.light).textTheme,
      ),
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
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
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
        labelStyle: const TextStyle(color: Color(0xFF888888)),
        hintStyle: const TextStyle(color: Color(0xFF888888)),
      ),
    );
  }
}
