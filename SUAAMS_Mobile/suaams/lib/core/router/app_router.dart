//This file is the main router for the SUAAMS app. It uses GoRouter to define the navigation structure and implements a security guard to handle authentication-based redirects.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/providers/auth_provider.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/auth/presentation/login_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  // Removed ref.watch() from here so the router doesn't rebuild continuously.
  final authNotifier = ref.read(authProvider.notifier);
  return GoRouter(
    initialLocation: '/splash',
    refreshListenable: authNotifier, // This allows the router to listen for changes in the auth state
    redirect: (context, state) {
      // 1. We READ the state only when a navigation event actually happens
      final authState = ref.read(authProvider);
      
      final isLoggingIn = state.matchedLocation == '/login';
      final isSplash = state.matchedLocation == '/splash';
      final user = authState.user;

      if (isSplash) return null;

      if (user == null && !isLoggingIn) {
        return '/login';
      }

      if (user != null && isLoggingIn) {
        if (user.role == 'admin') return '/admin';
        if (user.role == 'lecturer') return '/lecturer';
        if (user.role == 'student') return '/student';
      }

      return null;
    },
    
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/admin',
        builder: (context, state) => const Scaffold(body: Center(child: Text('Admin Dashboard'))),
      ),
      GoRoute(
        path: '/lecturer',
        builder: (context, state) => const Scaffold(body: Center(child: Text('Lecturer Dashboard'))),
      ),
      GoRoute(
        path: '/student',
        builder: (context, state) => Scaffold(
          body: Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text('Student Dashboard'),
                const SizedBox(height: 20),
                Consumer(
                  builder: (context, ref, _) => ElevatedButton(
                    onPressed: () => ref.read(authProvider.notifier).logout(),
                    child: const Text('Logout'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ],
  );
});