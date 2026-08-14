import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../providers/auth_provider.dart';
import '../../../shared/utils/grid_overlay_painter.dart';
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
          // PERF FIX: background extracted into its own const-constructible
          // widget and wrapped in RepaintBoundary, same pattern already used
          // in login_screen.dart/_LoginBackground. Without this, the ticking
          // CircularProgressIndicator below shared this Stack's single paint
          // layer with the static gradient circles + CustomPaint grid, so
          // every animation frame repainted the whole background too --
          // this is the exact "blinking cursor forces the whole canvas to
          // redraw" pitfall from CLAUDE.md, just with a spinner instead of a
          // text cursor.
          const RepaintBoundary(
            child: _SplashBackground(),
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

// Extracted so it can be `const`-constructed and isolated behind a
// RepaintBoundary above -- it depends on Theme.of(context) internally
// instead of taking isDarkMode/colorScheme as params, so the const instance
// above is stable across rebuilds while still reading current theme values
// at paint time via its own BuildContext.
class _SplashBackground extends StatelessWidget {
  const _SplashBackground();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;

    return Stack(
      children: [
        Positioned.fill(child: Container(color: colorScheme.surface)),
        Positioned(
          top: -100,
          right: -50,
          child: Container(
            width: 250,
            height: 250,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF0A0A14).withValues(alpha: 0.6)
                  : const Color(0xFFE0E7FF).withValues(alpha: 0.75),
            ),
          ),
        ),
        Positioned(
          bottom: -80,
          left: -60,
          child: Container(
            width: 200,
            height: 200,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: isDarkMode
                  ? const Color(0xFF080810).withValues(alpha: 0.65)
                  : const Color(0xFFFEF3C7).withValues(alpha: 0.55),
            ),
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: CustomPaint(
              // PERF FIX: const painter instance per branch (see
              // grid_overlay_painter.dart) instead of allocating a new one.
              painter: isDarkMode
                  ? const GridOverlayPainter(color: Colors.white)
                  : const GridOverlayPainter(color: Colors.black),
            ),
          ),
        ),
      ],
    );
  }
}
