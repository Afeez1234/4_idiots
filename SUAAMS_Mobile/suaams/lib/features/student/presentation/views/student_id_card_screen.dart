import 'package:suaams/shared/widgets/app_label_value_row.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/shared/widgets/app_state_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/shared/widgets/dashboard_background.dart';
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/models/student_dashboard_model.dart';
import 'package:suaams/features/student/presentation/views/nfc_broadcast_sheet.dart';

// ID Card tab -- "Full screen digital ID with NFC tap button". The card
// visuals are lifted as-is from ProfileView's old _buildDigitalIDCard (now
// removed from there) since they already worked well; this screen just
// gives that card its own full-screen home and adds the NFC tap action.
// The "NFC active screen (biometric gate -> 3 second broadcast)" node under
// this in the nav map is NfcBroadcastSheet -- already fully working as a
// modal sheet (biometric gate + countdown + radar animation), so it's
// reused unchanged rather than converted into a separate route.
class StudentIdCardScreen extends ConsumerWidget {
  const StudentIdCardScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(studentDashboardProvider);
    final isDarkMode = Theme.of(context).brightness == Brightness.dark;
    final colorScheme = Theme.of(context).colorScheme;

    final data = state.data;

    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: Stack(
        children: [
          RepaintBoundary(
            child: DashboardBackground(
              isDarkMode: isDarkMode,
              colorScheme: colorScheme,
            ),
          ),
          SafeArea(
            child: data == null
                ? (state.isLoading
                      ? const Center(child: CircularProgressIndicator())
                      : AppStateView(
                          kind: AppStateKind.error,
                          icon: Icons.badge_rounded,
                          title: "Couldn't load your ID card",
                          message: state.errorMessage ??
                              'Check your connection and try again.',
                          onRetry: () => ref
                              .read(studentDashboardProvider.notifier)
                              .loadDashboardData(),
                        ))
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'DIGITAL SMART ID',
                          style: AppTheme.eyebrow(colorScheme.onSurface.withValues(alpha: 0.6)),
                        ),
                        const SizedBox(height: 8),
                        // This tab previously had no explanation anywhere in
                        // the app: a card appeared with no indication of what
                        // it was for, and a button labelled "TAP TO CHECK IN"
                        // underneath it that looked like a mistake. The card
                        // IS the attendance credential -- it lives on the
                        // phone rather than in a wallet, which is the whole
                        // premise of the system -- so say so.
                        Text(
                          'Your ID lives on this phone rather than in a '
                          'wallet. Present it at any SUAAMS terminal to '
                          'record your attendance.',
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(
                                color: colorScheme.onSurface.withValues(
                                  alpha: 0.55,
                                ),
                                height: 1.45,
                              ),
                        ),
                        const SizedBox(height: 16),
                        _DigitalIdCard(
                          profile: data.profile,
                          colorScheme: colorScheme,
                          isDarkMode: isDarkMode,
                        ),
                        const SizedBox(height: 32),
                        ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: colorScheme.primary,
                            foregroundColor: colorScheme.surface,
                            minimumSize: const Size(double.infinity, 56),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                            ),
                            elevation: 0,
                          ),
                          onPressed: () => NfcBroadcastSheet.show(context),
                          child: const Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.contactless_rounded, size: 22),
                              SizedBox(width: 12),
                              Text(
                                'CHECK IN WITH THIS ID',
                                style: TextStyle(
                                  letterSpacing: 1.5,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        // Same reassurance the Home session card gives: the
                        // fingerprint prompt is mandatory, so naming it here
                        // means it never arrives as a surprise.
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            Icon(
                              Icons.fingerprint_rounded,
                              size: 14,
                              color: colorScheme.onSurface.withValues(
                                alpha: 0.45,
                              ),
                            ),
                            const SizedBox(width: 6),
                            Flexible(
                              child: Text(
                                "You'll confirm with your fingerprint, then "
                                'hold your phone to the terminal.',
                                textAlign: TextAlign.center,
                                style: Theme.of(context).textTheme.bodySmall
                                    ?.copyWith(
                                      color: colorScheme.onSurface.withValues(
                                        alpha: 0.45,
                                      ),
                                    ),
                              ),
                            ),
                          ],
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

class _DigitalIdCard extends StatelessWidget {
  final StudentProfile profile;
  final ColorScheme colorScheme;
  final bool isDarkMode;

  const _DigitalIdCard({
    required this.profile,
    required this.colorScheme,
    required this.isDarkMode,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: colorScheme.outline.withValues(alpha: 0.15),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: isDarkMode ? 0.4 : 0.05),
            blurRadius: 20,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 40,
                height: 30,
                decoration: BoxDecoration(
                  color: Colors.amber.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(
                    color: Colors.amber.withValues(alpha: 0.5),
                  ),
                ),
                child: const Center(
                  child: Icon(
                    Icons.memory_rounded,
                    size: 20,
                    color: Colors.amber,
                  ),
                ),
              ),
              CircleAvatar(
                radius: 32,
                backgroundColor: colorScheme.primary.withValues(alpha: 0.1),
                child: Text(
                  profile.fullName[0].toUpperCase(),
                  style: TextStyle(
                    fontWeight: FontWeight.w700,
                    fontSize: 28,
                    color: colorScheme.primary,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 24),

          Text(
            profile.fullName.toUpperCase(),
            style: const TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: 8),

          AppLabelValueRow(
            'MATRIC NO',
            profile.matricNumber,
            uppercaseValue: true,
          ),
          const SizedBox(height: 8),
          AppLabelValueRow(
            'DEPARTMENT',
            profile.department,
            uppercaseValue: true,
          ),
          const SizedBox(height: 8),
          AppLabelValueRow('LEVEL', profile.level, uppercaseValue: true),

          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Divider(height: 1, thickness: 1),
          ),

          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'HARDWARE UID',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.5,
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    profile.rfidUid ?? 'UNASSIGNED',
                    style: AppTheme.accent(
                      size: 12,
                      weight: FontWeight.w700,
                      color: profile.rfidUid == null
                          ? colorScheme.error
                          : colorScheme.primary,
                    ),
                  ),
                ],
              ),
              Icon(
                Icons.contactless_rounded,
                color: profile.rfidUid == null
                    ? colorScheme.error.withValues(alpha: 0.5)
                    : colorScheme.primary,
              ),
            ],
          ),
        ],
      ),
    );
  }
}
