//This file alraedy says it from the name :)

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // We only define a dark theme since the app is explicitly dark-mode first
  static ThemeData get darkTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      
      // The Scaffold background is the absolute bottom layer of the app
      scaffoldBackgroundColor: const Color(0xFF121212), 
      
      // ColorScheme dictates the primary accents across all Material widgets
      colorScheme: const ColorScheme.dark(
        primary: Color(0xFF5B7BFF), // The specific SUAAMS blue accent
        onPrimary: Colors.white,
        surface: Color(0xFF1E1E1E), // Slightly lighter gray for cards/elevated elements
        onSurface: Colors.white,
        error: Color(0xFFFF5252),
      ),

      // Global Typography: Applies the Inter font to all text in the app
      textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme).copyWith(
        headlineLarge: const TextStyle(
          fontWeight: FontWeight.bold, 
          color: Colors.white,
        ),
        bodyMedium: const TextStyle(
          color: Colors.white70,
        ),
      ),

      // Global Input Styling: This makes all your TextFields look exactly 
      // like your Figma design without styling them individually on every screen.
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF1E1E1E), // Dark grey text box background
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        
        // Default unselected state (no border)
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        
        // Active selected state (blue border)
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF5B7BFF), width: 1.5),
        ),
        
        // Error state (red border, like when a password is too short)
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFFF5252), width: 1.5),
        ),
        
        labelStyle: const TextStyle(color: Colors.grey),
        hintStyle: const TextStyle(color: Colors.grey),
      ),
    );
  }
}