import 'package:suaams/core/theme/app_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/core/providers/theme_provider.dart';
import 'package:suaams/shared/widgets/theme_mode_sheet.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/lecturer/providers/lecturer_provider.dart'
    show lecturerDashboardProvider;
import 'package:suaams/shared/widgets/app_label_value_row.dart';
import 'package:suaams/features/lecturer/models/lecturer_dashboard_model.dart';
import 'package:suaams/shared/widgets/confirm_dialog.dart';

// Profile tab -- new screen (the lecturer side previously only had logout
// tucked into the dashboard header's avatar tap). Mirrors the student
// ProfileView's structure/style: personal info, preferences, sign out.
class LecturerProfileScreen extends ConsumerWidget {
  const LecturerProfileScreen({super.key});

  Future<void> _showLogoutDialog(
    BuildContext context,
    WidgetRef ref,
    ColorScheme colorScheme,
  ) async {
    // One of four hand-rolled copies; see student_home_screen.dart.
    // colorScheme is still taken as a parameter for call-site compatibility
    // but is no longer used here -- showConfirmDialog reads the theme itself.
    final confirmed = await showConfirmDialog(
      context,
      title: 'Log Out',
      message: 'Are you sure you want to log out of your account?',
      confirmLabel: 'LOG OUT',
      destructive: true,
    );
    if (confirmed) {
      await ref.read(authProvider.notifier).logout();
    }
  }

  // Guards the voluntary "Update password" tap: a confirmation dialog (so
  // a mis-tap can be backed out of before anything happens) followed by a
  // biometric/device-credential check (so an unlocked phone left lying
  // around isn't enough to change the account owner's password out from
  // under them -- same threat model as the NFC check-in gate in
  // nfc_provider.dart). Only reached voluntarily; the forced first-login
  // reset (app_router.dart's redirect guard) skips this entirely.
  Future<void> _confirmAndOpenChangePassword(
    BuildContext context,
    ColorScheme colorScheme,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainer,
        title: const Text(
          'Change Password',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        content: const Text(
          "You're about to change your account password. Continue?",
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(
              'CANCEL',
              style: TextStyle(color: colorScheme.onSurface),
            ),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('CONTINUE'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    bool authenticated = false;
    try {
      authenticated = await LocalAuthentication().authenticate(
        localizedReason: 'Verify identity to change your password',
      );
    } catch (_) {
      authenticated = false;
    }
    if (!context.mounted) return;

    if (!authenticated) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Identity verification failed.')),
      );
      return;
    }

    context.push('/change-password', extra: false);
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(lecturerDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final profile = state.data?.profile;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Profile'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (profile != null) ...[
                Text(
                  'LECTURER DOSSIER',
                  style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
                ),
                const SizedBox(height: 16),
                _PersonalInfoCard(profile: profile, colorScheme: colorScheme),
                const SizedBox(height: 32),
              ],

              Text(
                'SYSTEM PREFERENCES',
                style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
              ),
              const SizedBox(height: 16),

              _PreferenceTile(
                icon: isDarkMode
                    ? Icons.light_mode_rounded
                    : Icons.dark_mode_rounded,
                title: 'Interface Theme',
                subtitle: themeModeLabel(ref.watch(themeProvider)),
                colorScheme: colorScheme,
                onTap: () => ThemeModeSheet.show(context),
              ),
              const SizedBox(height: 12),
              _PreferenceTile(
                icon: Icons.security_rounded,
                title: 'Account Security',
                subtitle: 'Update password',
                colorScheme: colorScheme,
                onTap: () =>
                    _confirmAndOpenChangePassword(context, colorScheme),
              ),

              const SizedBox(height: 48),

              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: colorScheme.errorContainer.withValues(
                    alpha: 0.2,
                  ),
                  foregroundColor: colorScheme.error,
                  minimumSize: const Size(double.infinity, 56),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: BorderSide(
                      color: colorScheme.error.withValues(alpha: 0.5),
                    ),
                  ),
                  elevation: 0,
                ),
                onPressed: () => _showLogoutDialog(context, ref, colorScheme),
                child: const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.power_settings_new_rounded, size: 20),
                    SizedBox(width: 12),
                    Text(
                      'LOG OUT',
                      style: TextStyle(
                        letterSpacing: 2,
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }
}

class _PersonalInfoCard extends StatelessWidget {
  final LecturerProfile profile;
  final ColorScheme colorScheme;

  const _PersonalInfoCard({required this.profile, required this.colorScheme});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.15)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              CircleAvatar(
                radius: 24,
                backgroundColor: colorScheme.primary.withValues(alpha: 0.1),
                child: Text(
                  profile.fullName.isNotEmpty
                      ? profile.fullName[0].toUpperCase()
                      : 'L',
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 20,
                    color: colorScheme.primary,
                  ),
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Text(
                  profile.fullName,
                  style: const TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 16,
                  ),
                ),
              ),
            ],
          ),
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Divider(height: 1, thickness: 1),
          ),
          AppLabelValueRow('STAFF ID', profile.staffId),
          if (profile.department != null) ...[
            const SizedBox(height: 8),
            AppLabelValueRow('DEPARTMENT', profile.department!),
          ],
        ],
      ),
    );
  }
}

class _PreferenceTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final ColorScheme colorScheme;
  final VoidCallback onTap;

  const _PreferenceTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.colorScheme,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: colorScheme.surfaceContainer.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
        ),
        child: Row(
          children: [
            Icon(icon, color: colorScheme.primary, size: 24),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    subtitle,
                    style: TextStyle(
                      fontSize: 10,
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                ],
              ),
            ),
            Icon(
              Icons.chevron_right_rounded,
              color: colorScheme.onSurface.withValues(alpha: 0.3),
            ),
          ],
        ),
      ),
    );
  }
}
