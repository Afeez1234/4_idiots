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
        context.go('/login');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          // Background matching login screen
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
                painter: GridOverlayPainter(
                  color: isDarkMode ? Colors.white : Colors.black,
                ),
              ),
            ),
          ),

          // Content
          Center(
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
        ],
      ),
    );
  }
}
