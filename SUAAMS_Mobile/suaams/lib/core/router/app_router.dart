//This file is the main router for the SUAAMS app. It uses GoRouter to define the navigation structure and implements a security guard to handle authentication-based redirects.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/auth/presentation/login_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  // 1. Watch the REAL auth state from Riverpod
  final authState = ref.watch(authProvider);

  return GoRouter(
    initialLocation: '/splash',
    
    // 2. The Security Guard (Redirect Logic)
    redirect: (context, state) {
      final isLoggingIn = state.matchedLocation == '/login';
      final isSplash = state.matchedLocation == '/splash';
      final user = authState.user;

      // Let the Splash Screen do its 2-second animation and vault check unbothered
      if (isSplash) return null;

      // If the user is NOT logged in and trying to access a protected route (like /student) -> kick to Login
      if (user == null && !isLoggingIn) {
        return '/login';
      }

      // If the user IS logged in and tries to go to the Login screen -> kick to their specific Dashboard
      if (user != null && isLoggingIn) {
        if (user.role == 'admin') return '/admin';
        if (user.role == 'lecturer') return '/lecturer';
        if (user.role == 'student') return '/student';
      }

      // If no rules are broken, let them proceed normally
      return null;
    },
    
    // 3. Define the actual routes
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      
      // --- Admin Routes (Placeholders until Phase 6) ---
      GoRoute(
        path: '/admin',
        builder: (context, state) => const Scaffold(body: Center(child: Text('Admin Dashboard'))),
      ),

      // --- Lecturer Routes (Placeholders until Phase 6) ---
      GoRoute(
        path: '/lecturer',
        builder: (context, state) => const Scaffold(body: Center(child: Text('Lecturer Dashboard'))),
      ),

      // --- Student Routes (Placeholders until Phase 6) ---
      GoRoute(
        path: '/student',
        builder: (context, state) => const Scaffold(body: Center(child: Text('Student Dashboard'))),
      ),
    ],
  );
});