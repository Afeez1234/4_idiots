import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../../../shared/widgets/dashboard_background.dart';
import '../../providers/student_provider.dart';
import '../../models/student_dashboard_model.dart';
import 'nfc_broadcast_sheet.dart';

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
                ? Center(
                    child: state.isLoading
                        ? const CircularProgressIndicator()
                        : Text(state.errorMessage ?? 'No data available'),
                  )
                : SingleChildScrollView(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'DIGITAL SMART ID',
                          style: TextStyle(
                            fontSize: 10,
                            letterSpacing: 2,
                            color: Colors.grey,
                            fontWeight: FontWeight.bold,
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
                                'TAP TO CHECK IN',
                                style: TextStyle(
                                  letterSpacing: 2,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
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
                    fontWeight: FontWeight.w900,
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
              fontWeight: FontWeight.w900,
              letterSpacing: 1.5,
            ),
          ),
          const SizedBox(height: 8),

          _IdRow('MATRIC NO', profile.matricNumber, colorScheme),
          const SizedBox(height: 8),
          _IdRow('DEPARTMENT', profile.department, colorScheme),
          const SizedBox(height: 8),
          _IdRow('LEVEL', profile.level, colorScheme),

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
                      fontSize: 8,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.5,
                      color: colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    profile.rfidUid ?? 'UNASSIGNED',
                    style: TextStyle(
                      fontSize: 12,
                      fontFamily: 'JetBrains Mono',
                      fontWeight: FontWeight.bold,
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

class _IdRow extends StatelessWidget {
  final String label;
  final String value;
  final ColorScheme colorScheme;

  const _IdRow(this.label, this.value, this.colorScheme);

  @override
  Widget build(BuildContext context) {
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
}
