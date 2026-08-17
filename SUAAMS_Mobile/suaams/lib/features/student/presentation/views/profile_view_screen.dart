import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../../../../core/providers/theme_provider.dart';
import '../../../auth/providers/auth_provider.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';

class ProfileView extends ConsumerWidget {
  const ProfileView({super.key});

  void _showLogoutDialog(BuildContext context, WidgetRef ref) {
    final colorScheme = Theme.of(context).colorScheme;
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: colorScheme.surfaceContainer,
        title: const Text(
          'Sign Out',
          style: TextStyle(fontWeight: FontWeight.bold),
        ),
        content: const Text(
          'Are you sure you want to log out of your terminal session?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'CANCEL',
              style: TextStyle(color: colorScheme.onSurface),
            ),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: colorScheme.error,
              foregroundColor: colorScheme.onError,
            ),
            onPressed: () {
              Navigator.pop(context);
              ref.read(authProvider.notifier).logout();
            },
            child: const Text('SIGN OUT'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

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
          const Text(
            'STUDENT DOSSIER',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 2,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
          ),
          const SizedBox(height: 16),

          // 1. Personal info
          _buildPersonalInfoCard(profile, colorScheme),
          const SizedBox(height: 32),

          const Text(
            'SYSTEM PREFERENCES',
            style: TextStyle(
              fontSize: 10,
              letterSpacing: 2,
              color: Colors.grey,
              fontWeight: FontWeight.bold,
            ),
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
            onTap: () => ref.read(themeProvider.notifier).toggleTheme(),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.phonelink_lock_rounded,
            title: 'Linked Devices',
            subtitle: 'Manage device binding',
            colorScheme: colorScheme,
            onTap: () => context.push('/student/profile/devices'),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.notifications_rounded,
            title: 'Notification Settings',
            subtitle: 'Announcements & session alerts',
            colorScheme: colorScheme,
            onTap: () => context.push('/student/profile/notifications'),
          ),
          const SizedBox(height: 12),
          _buildPreferenceTile(
            icon: Icons.security_rounded,
            title: 'Account Security',
            subtitle: 'Update authorization code',
            colorScheme: colorScheme,
            // Reuses the existing ChangePasswordScreen (already fully
            // working -- it's also used for the forced first-login flow at
            // app_router.dart). Uses push (not go) deliberately: go replaces
            // the whole nav stack, which is right for the forced-login case
            // but would leave a voluntary visit here with no way back if the
            // student changes their mind. push keeps this screen underneath,
            // so the OS back gesture/button returns to Profile.
            onTap: () => context.push('/change-password'),
          ),

          const SizedBox(height: 48),

          // 3. Sign Out Button
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
                  'TERMINATE SESSION',
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
                  profile.fullName[0].toUpperCase(),
                  style: TextStyle(
                    fontWeight: FontWeight.w900,
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
          _buildInfoRow('MATRIC NO', profile.matricNumber, colorScheme),
          const SizedBox(height: 8),
          _buildInfoRow('DEPARTMENT', profile.department, colorScheme),
          const SizedBox(height: 8),
          _buildInfoRow('LEVEL', profile.level, colorScheme),
        ],
      ),
    );
  }

  Widget _buildInfoRow(String label, String value, ColorScheme colorScheme) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.bold,
            letterSpacing: 1.0,
            color: colorScheme.onSurface.withValues(alpha: 0.5),
          ),
        ),
        Text(
          value.toUpperCase(),
          style: const TextStyle(
            fontSize: 12,
            fontFamily: 'JetBrains Mono',
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }

  Widget _buildPreferenceTile({
    required IconData icon,
    required String title,
    required String subtitle,
    required ColorScheme colorScheme,
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
