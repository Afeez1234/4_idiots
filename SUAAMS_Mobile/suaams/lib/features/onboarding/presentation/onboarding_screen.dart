import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:suaams/core/providers/onboarding_provider.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/dashboard_background.dart';
import 'package:suaams/shared/widgets/suaams_logo.dart';

/// First-run walkthrough, shown once per install.
///
/// This exists because the app had no orientation layer at all. A student
/// arriving at the dashboard had no way to learn what the app was for, what
/// would happen when they tapped the check-in card, or that their account is
/// tied to this specific phone -- the last of which they would otherwise
/// discover by being locked out and having to visit IT.
///
/// Deliberately not skippable. Every page is something a first-timer needs
/// before they can use the app without help, and a "Skip" on a three-page
/// flow mostly just produces support questions later.
class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;

  static const _pages = <_OnboardingPageData>[
    _OnboardingPageData(
      icon: Icons.fact_check_rounded,
      title: 'Your attendance,\nfrom your phone',
      body:
          'SUAAMS records your attendance by tapping your phone against a '
          'terminal in the lecture hall. No queue, no paper sheet, and no '
          'book to sign.',
      points: [
        ('Home', 'Your live session, stats, and today\'s timetable'),
        ('Timetable', 'What you have scheduled this week'),
        ('Records', 'Every session you have attended'),
        ('ID Card', 'Your digital student ID and linked devices'),
      ],
    ),
    _OnboardingPageData(
      icon: Icons.contactless_rounded,
      title: 'Checking in takes\nabout a second',
      body:
          'When a lecturer starts a session, the card on your Home tab turns '
          'live. Tap it and follow the three steps.',
      points: [
        ('1', 'Tap the session card on your Home tab'),
        ('2', 'Confirm with your fingerprint — this is required, not optional'),
        ('3', 'Hold the back of your phone near the terminal'),
      ],
    ),
    _OnboardingPageData(
      icon: Icons.phonelink_lock_rounded,
      title: 'Your account is\ntied to this phone',
      body:
          'The first time you sign in, this device is recorded against your '
          'account. Signing in from another phone is blocked, and nobody — '
          'including IT — can move your attendance to a new device without '
          'you presenting your ID in person.',
      points: [
        ('Why', 'So nobody can mark attendance on your behalf'),
        ('Lost phone', 'Visit IT Administration to have the binding reset'),
        ('Security', 'Failed fingerprint checks are refused, not bypassed'),
      ],
    ),
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  /// Advance one page, wrapping to the first if the user is mid-swipe and
  /// overshoots. Guarded so a double-tap can't queue two jumps.
  void _goNext() {
    if (!_controller.hasClients) return;
    final next = _page + 1;
    _controller.animateToPage(
      next >= _pages.length ? 0 : next,
      duration: const Duration(milliseconds: 280),
      curve: Curves.easeOutCubic,
    );
  }

  Future<void> _finish() async {
    await ref.read(onboardingProvider.notifier).markSeen();
    if (!mounted) return;
    // Straight to the role's home. Routing back through /splash would work
    // (the redirect would then send them onward) but costs a second
    // two-second splash in the middle of a flow the user just finished.
    final user = ref.read(authProvider).user;
    if (user == null) {
      context.go('/login');
    } else if (user.requiresPasswordChange) {
      context.go('/change-password');
    } else if (user.role == 'student') {
      context.go('/student/home');
    } else if (user.role == 'lecturer' || user.role == 'hod') {
      context.go('/lecturer/home');
    } else if (user.role == 'admin') {
      context.go('/admin');
    } else {
      context.go('/login');
    }
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final isLast = _page == _pages.length - 1;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          RepaintBoundary(
            child: DashboardBackground(
              isDarkMode: isDark,
              colorScheme: colorScheme,
              variant: AppBackgroundVariant.auth,
            ),
          ),
          SafeArea(
            child: Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 24, 24, 0),
                  child: Row(
                    children: [
                      const SuaamsLogo(size: 28),
                      const SizedBox(width: 10),
                      Text(
                        'SUAAMS',
                        style: Theme.of(context).textTheme.titleSmall?.copyWith(
                          letterSpacing: 3,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                ),
                Expanded(
                  child: PageView.builder(
                    controller: _controller,
                    itemCount: _pages.length,
                    onPageChanged: (i) => setState(() => _page = i),
                    itemBuilder: (context, i) =>
                        _OnboardingPage(data: _pages[i]),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 8, 24, 24),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          for (var i = 0; i < _pages.length; i++)
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              margin: const EdgeInsets.symmetric(horizontal: 3),
                              width: i == _page ? 20 : 7,
                              height: 7,
                              decoration: BoxDecoration(
                                color: i == _page
                                    ? colorScheme.primary
                                    : colorScheme.onSurface.withValues(alpha: 0.2),
                                borderRadius: BorderRadius.circular(4),
                              ),
                            ),
                        ],
                      ),
                      const SizedBox(height: 20),
                      SizedBox(
                        width: double.infinity,
                        child: FilledButton(
                          // Advances the PageView until the last page, then
                          // finishes. Previously this was wired straight to
                          // _finish, so the very first NEXT tap dropped the
                          // user onto the dashboard and skipped pages two
                          // and three entirely -- including the page
                          // explaining the device binding.
                          onPressed: isLast ? _finish : _goNext,
                          style: FilledButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.onPrimary,
                            padding: const EdgeInsets.symmetric(vertical: 16),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                          ),
                          child: Text(
                            isLast ? 'GET STARTED' : 'NEXT',
                            style: const TextStyle(
                              fontWeight: FontWeight.w700,
                              letterSpacing: 1.5,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _OnboardingPageData {
  final IconData icon;
  final String title;
  final String body;
  final List<(String, String)> points;

  const _OnboardingPageData({
    required this.icon,
    required this.title,
    required this.body,
    required this.points,
  });
}

class _OnboardingPage extends StatelessWidget {
  final _OnboardingPageData data;

  const _OnboardingPage({required this.data});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(24, 32, 24, 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 64,
            height: 64,
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(
              data.icon,
              size: 30,
              color: colorScheme.primary,
            ),
          ),
          const SizedBox(height: 24),
          Text(
            data.title,
            style: textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
              height: 1.25,
            ),
          ),
          const SizedBox(height: 12),
          Text(
            data.body,
            style: textTheme.bodyMedium?.copyWith(
              color: colorScheme.onSurface.withValues(alpha: 0.65),
            ),
          ),
          const SizedBox(height: 24),
          for (final (lead, text) in data.points) ...[
            _PointRow(lead: lead, text: text),
            const SizedBox(height: 10),
          ],
        ],
      ),
    );
  }
}

class _PointRow extends StatelessWidget {
  final String lead;
  final String text;

  const _PointRow({required this.lead, required this.text});

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer.withValues(alpha: 0.7),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: colorScheme.outline.withValues(alpha: 0.14),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            constraints: const BoxConstraints(minWidth: 26),
            alignment: Alignment.center,
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: colorScheme.primary.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Text(
              lead,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontFamily: AppTheme.accentFont,
                fontSize: 11,
                fontWeight: FontWeight.w700,
                color: colorScheme.primary,
              ),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: colorScheme.onSurface.withValues(alpha: 0.75),
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
