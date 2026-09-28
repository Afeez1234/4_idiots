import 'package:suaams/shared/widgets/dashboard_background.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';
import '../../../shared/widgets/suaams_logo.dart';

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
    await Future.delayed(const Duration(seconds: 2));
    if (!mounted) return;
    await ref.read(authProvider.notifier).checkExistingAuth();
    if (mounted) {
      final user = ref.read(authProvider).user;
      if (user != null) {
        // Token exists! Route them based on password status and role
        if (user.requiresPasswordChange) {
          context.go('/change-password');
        } else if (user.role == 'student') {
          context.go('/student/home');
        } else if (user.role == 'lecturer') {
          context.go('/lecturer/home');
        } else if (user.role == 'admin') {
          context.go('/admin');
        } else {
          context.go('/login');
        }
      } else {
        context.go('/login');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          // PERF FIX: background isolated in its own RepaintBoundary.
          // Without this, the ticking CircularProgressIndicator below shared
          // this Stack's single paint layer with the static gradient circles
          // + CustomPaint grid, so every animation frame repainted the whole
          // background too -- this is the exact "blinking cursor forces the
          // whole canvas to redraw" pitfall from CLAUDE.md, just with a
          // spinner instead of a text cursor.
          //
          // This is no longer `const`: the private _SplashBackground it
          // replaced had no parameters and could be constructed at compile
          // time, whereas the shared DashboardBackground reads isDarkMode
          // and colorScheme. The RepaintBoundary is what actually buys the
          // isolated paint layer; const was a secondary saving, and losing
          // it costs one widget allocation on a screen that renders once.
          RepaintBoundary(
            child: DashboardBackground(
              isDarkMode: Theme.of(context).brightness == Brightness.dark,
              colorScheme: colorScheme,
              variant: AppBackgroundVariant.auth,
            ),
          ),

          // Content -- also isolated in its own RepaintBoundary so the
          // spinner's 60fps ticks stay confined to just this subtree.
          Center(
            child: RepaintBoundary(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SuaamsLogoFull(size: 64, color: colorScheme.primary),
                  const SizedBox(height: 60),
                  CircularProgressIndicator(
                    color: colorScheme.primary,
                    strokeWidth: 2,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
