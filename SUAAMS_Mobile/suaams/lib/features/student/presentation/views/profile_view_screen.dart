import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/core/theme/app_terminal.dart';
import 'package:suaams/core/providers/theme_provider.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/shared/widgets/confirm_dialog.dart';
import 'package:suaams/shared/utils/initials.dart';

class ProfileView extends ConsumerWidget {
  const ProfileView({super.key});

  Future<void> _showLogoutDialog(BuildContext context, WidgetRef ref) async {
    // All four logout dialogs now go through showConfirmDialog, so they no
    // longer drift -- this one used to ask about logging out of your
    // "terminal session" where the others said "session".
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
    final state = ref.watch(studentDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;
    // The muted text tokens are used for every low-emphasis label here.
    // These were `onSurface.withValues(alpha: 0.5)` at 10sp, which measured
    // 3.34:1 on white -- failing WCAG AA. Dark mode came in at 5.17:1, which
    // is presumably why it survived: the app defaults to dark. textMuted is
    // 5.41:1 light / 7.86:1 dark, so it passes in both.
    final terminal = terminalOf(context);

    // We can safely assume data exists here because the parent dashboard checks it,
    // but we use null coalescing just to be safe.
    final data = state.data;
    if (data == null) return const SizedBox.shrink();

    final profile = data.profile;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('STUDENT DOSSIER', style: AppTheme.eyebrow(terminal.textMuted)),
          const SizedBox(height: 16),

          // 1. Personal info
          _buildPersonalInfoCard(profile, colorScheme, terminal),
          const SizedBox(height: 32),

          Text(
            'SYSTEM PREFERENCES',
            style: AppTheme.eyebrow(terminal.textMuted),
          ),
          const SizedBox(height: 16),

          // 2. Preferences List
          _buildPreferenceTile(
            icon: isDarkMode
                ? Icons.light_mode_rounded
                : Icons.dark_mode_rounded,
            title: 'Interface Theme',
            subtitle: isDarkMode
                ? 'Stealth Mode (Dark)'
                : 'Blueprint Mode (Light)',
            colorScheme: colorScheme,
            terminal: terminal,
            onTap: () => ref.read(themeProvider.notifier).toggleTheme(),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.phonelink_lock_rounded,
            title: 'Linked Devices',
            subtitle: 'Manage device binding',
            colorScheme: colorScheme,
            terminal: terminal,
            onTap: () => context.push('/student/profile/devices'),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.notifications_rounded,
            title: 'Notification Settings',
            subtitle: 'Announcements & session alerts',
            colorScheme: colorScheme,
            terminal: terminal,
            onTap: () => context.push('/student/profile/notifications'),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.security_rounded,
            title: 'Account Security',
            subtitle: 'Update password',
            colorScheme: colorScheme,
            terminal: terminal,
            // Reuses the existing ChangePasswordScreen (already fully
            // working -- it's also used for the forced first-login flow at
            // app_router.dart). _confirmAndOpenChangePassword() confirms
            // intent, verifies identity, then pushes with extra: false so
            // ChangePasswordScreen shows a visible back button -- push alone
            // wasn't enough; the screen had no back-button UI of its own.
            onTap: () => _confirmAndOpenChangePassword(context, colorScheme),
          ),

          const SizedBox(height: 48),

          // 3. Log Out Button
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
            onPressed: () => _showLogoutDialog(context, ref),
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
          const SizedBox(height: 120), // Padding for bottom nav
        ],
      ),
    );
  }

  // The digital ID card visuals (NFC chip mark, hardware UID row) that used
  // to live here moved to StudentIdCardScreen -- they're the "Full screen
  // digital ID" tab now. This is a plain personal-info summary instead.
  Widget _buildPersonalInfoCard(
    StudentProfile profile,
    ColorScheme colorScheme,
    AppTerminal terminal,
  ) {
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
                  initialOf(profile.fullName, fallback: 'S'),
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
          _buildInfoRow('MATRIC NO', profile.matricNumber, terminal),
          const SizedBox(height: 8),
          _buildInfoRow('DEPARTMENT', profile.department, terminal),
          const SizedBox(height: 8),
          _buildInfoRow('LEVEL', profile.level, terminal),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value, AppTerminal terminal) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: AppTheme.minBodySize,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.0,
            color: terminal.textMuted,
          ),
        ),
        Text(
          value.toUpperCase(),
          style: AppTheme.accent(size: 12, weight: FontWeight.w700),
        ),
      ],
    );
  }

  Widget _buildPreferenceTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required ColorScheme colorScheme,
    required AppTerminal terminal,
    required VoidCallback onTap,
  }) {
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
                      fontSize: AppTheme.minBodySize,
                      color: terminal.textMuted,
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
