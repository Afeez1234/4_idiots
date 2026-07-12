//This file is the main router for the SUAAMS app. It uses GoRouter to define the navigation structure and implements a security guard to handle authentication-based redirects.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../features/auth/providers/auth_provider.dart';
import '../../features/auth/presentation/splash_screen.dart';
import '../../features/auth/presentation/login_screen.dart';
import '../../features/student/presentation/student_dashboard_screen.dart';
import '../../features/auth/presentation/change_password_screen.dart';

final appRouterProvider = Provider<GoRouter>((ref) {
  // 1. Create a simple ValueNotifier bridge for GoRouter
  final routerListener = ValueNotifier<bool>(false);

  // 2. Listen to the authProvider. Whenever it changes, trigger the routerListener!
  ref.listen(authProvider, (previous, next) {
    routerListener.value = !routerListener.value;
  });
  return GoRouter(
    initialLocation: '/splash',
    //3. Pass the bridge to GoRouter so it can listen for changes in the auth state
    refreshListenable:
        routerListener, // This allows the router to listen for changes in the auth state
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      final isLoggingIn = state.matchedLocation == '/login';
      final isSplash = state.matchedLocation == '/splash';
      final isChangingPassword = state.matchedLocation == '/change-password';
      final user = authState.user;

      if (isSplash) return null;

      if (user == null && !isLoggingIn) return '/login';

      if (user != null && user.requiresPasswordChange && !isChangingPassword) {
        return '/change-password';
      }

      if (user != null && (isLoggingIn || isSplash)) {
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
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
        path: '/admin',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Admin Dashboard'))),
      ),
      GoRoute(
        path: '/lecturer',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Lecturer Dashboard'))),
      ),
      GoRoute(
        path: '/student',
        builder: (context, state) => const StudentDashboardScreen(),
      ),
      GoRoute(
        path: '/change-password',
        builder: (context, state) => const ChangePasswordScreen(),
      ),
    ],
  );
});
