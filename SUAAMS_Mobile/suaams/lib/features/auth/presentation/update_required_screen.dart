import 'package:flutter/material.dart';

import 'package:suaams/core/network/api_client.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/shared/widgets/suaams_logo.dart';

/// Shown in place of every route once the server answers 426 "UPDATE
/// REQUIRED": this build is older than MIN_APP_BUILD (SUAAMS/app_version.py).
/// The router sends everything here (app_router.dart) and nothing leads
/// away -- the app can't talk to the server until it's updated, so any other
/// screen would only fail.
///
/// Where to get the update comes from the server (APP_UPDATE_MESSAGE),
/// because this screen ships in builds made before anyone knows where the
/// next one will be hosted. SelectableText so a download link can be copied.
class UpdateRequiredScreen extends StatelessWidget {
  const UpdateRequiredScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final t = terminalOf(context);
    final theme = Theme.of(context);

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
                  'Update SUAAMS',
                  style: theme.textTheme.headlineSmall,
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 12),
                Text(
                  'This version of the app no longer works with the server. '
                  'Install the latest version to sign in and check in.',
                  style: theme.textTheme.bodyMedium?.copyWith(color: t.textSecondary),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                SelectableText(
                  updateMessage ??
                      'Get it from the same place you installed SUAAMS, '
                          'or ask IT Administration.',
                  style: theme.textTheme.titleMedium,
                  textAlign: TextAlign.center,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
