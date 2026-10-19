import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'package:suaams/core/constants/api_constants.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/shared/widgets/suaams_logo.dart';

/// Where an admin, or an HOD without a Lecturer profile, lands in the app
/// (homeRouteFor in core/router/home_route.dart). Their work is on the web
/// portal: HOD and admin tools are web-only by design.
///
/// The route used to be a bare "Admin Dashboard" text with no way to sign
/// out, and an HOD without a Lecturer profile was sent to the lecturer
/// home, where every request failed "Lecturer profile not found".
/// (2026-10-19)
class WebPortalScreen extends ConsumerWidget {
  const WebPortalScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = terminalOf(context);
    final theme = Theme.of(context);
    final role = ref.watch(authProvider).user?.role;
    final who = role == 'admin' ? 'Admin' : 'HOD';
    // The site the API lives on: the base URL without its /api/v1 path.
    final site = ApiConstants.baseUrl.replaceFirst(RegExp(r'/api/v\d+/?$'), '');

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SuaamsLogo(size: 56),
                const SizedBox(height: 24),
                Text(
                  'Use the web portal',
                  style: theme.textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                Text(
                  '$who tools are on the SUAAMS web portal. '
                  'Sign in there with the same username and password.',
                  style: theme.textTheme.bodyMedium?.copyWith(color: t.textSecondary),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                SelectableText(
                  site,
                  style: theme.textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 32),
                OutlinedButton(
                  onPressed: () => ref.read(authProvider.notifier).logout(),
                  child: const Text('Sign out'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
