//This file is the splash screen for the SUAAMS app. It checks for an existing JWT in secure storage and routes the user to the appropriate screen based on their authentication state and role.
// i think it is from here where it determines if it will take you to the login screen or the dashboard based on your role. It also has a 2-second delay to show the branding before routing.
//reminder to work on the branding logo

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';

class SplashScreen extends ConsumerStatefulWidget {
  const SplashScreen({super.key});

  @override
  ConsumerState<SplashScreen> createState() => _SplashScreenState();
}

class _SplashScreenState extends ConsumerState<SplashScreen> {
  @override
  void initState() {
    super.initState();
    _checkAuthenticationState();
  }

  Future<void> _checkAuthenticationState() async {
    // 1. Give the UI a moment to render the branding (min 2 seconds)
    await Future.delayed(const Duration(seconds: 2));

    // 2. Call our Riverpod provider to check the hardware vault for a JWT
    await ref.read(authProvider.notifier).checkExistingAuth();

    // 3. Route the user based on the result
    if (mounted) {
      final user = ref.read(authProvider).user;
      
      if (user != null) {
        // Token exists! Route them to their specific dashboard based on their role
        if (user.role == 'student') {
          context.go('/student');
        } else if (user.role == 'lecturer') {
          context.go('/lecturer');
        } else if (user.role == 'admin') {
          context.go('/admin');
        } else {
          context.go('/login');
        }
      } else {
        // Vault is empty, force them to log in
        context.go('/login');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(
              'SUAAMS',
              style: Theme.of(context).textTheme.headlineLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: Theme.of(context).colorScheme.primary,
                    letterSpacing: 3.0,
                    fontSize: 42,
                  ),
            ),
            const SizedBox(height: 12),
            Text(
              'Smart University Attendance\nand Academic Management System',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.grey[400],
                    height: 1.5,
                    letterSpacing: 1.1,
                  ),
            ),
            const SizedBox(height: 60),
            CircularProgressIndicator(
              color: Theme.of(context).colorScheme.primary,
              strokeWidth: 3,
            ),
          ],
        ),
      ),
    );
  }
}