import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/features/student/providers/checkin_method_provider.dart';

/// Short label for the profile tile's subtitle.
String checkInMethodLabel(CheckInMethodPref pref) => switch (pref) {
  CheckInMethodPref.automatic => 'Automatic',
  CheckInMethodPref.nfc => 'NFC (tap)',
  CheckInMethodPref.bluetooth => 'Bluetooth',
};

/// Profile > System preferences > Check-in method.
///
/// Automatic is right for almost everyone; the other two exist for a phone
/// whose NFC is unreliable, and for testing one channel on purpose. When
/// the server has Bluetooth switched off, that option is shown but
/// disabled, so the student can see why it isn't available.
class CheckInMethodSheet extends ConsumerWidget {
  const CheckInMethodSheet({super.key});

  static void show(BuildContext context) {
    showModalBottomSheet(
      context: context,
      showDragHandle: true,
      builder: (_) => const CheckInMethodSheet(),
    );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final current = ref.watch(checkInMethodPrefProvider);
    final bleOn = ref.watch(checkinMethodsProvider).value?.ble ?? false;
    final muted = Theme.of(
      context,
    ).colorScheme.onSurface.withValues(alpha: 0.6);

    Widget option(
      CheckInMethodPref pref,
      String title,
      String subtitle, {
      bool enabled = true,
    }) {
      return RadioListTile<CheckInMethodPref>(
        value: pref,
        enabled: enabled,
        title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(subtitle, style: TextStyle(fontSize: 12, color: muted)),
      );
    }

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.only(bottom: 16),
        child: RadioGroup<CheckInMethodPref>(
          groupValue: current,
          onChanged: (value) {
            if (value == null) return;
            ref.read(checkInMethodPrefProvider.notifier).set(value);
            Navigator.pop(context);
          },
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(24, 0, 24, 8),
                child: Text(
                  'CHECK-IN METHOD',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    letterSpacing: 2,
                  ),
                ),
              ),
              option(
                CheckInMethodPref.automatic,
                'Automatic (recommended)',
                "NFC when this phone can tap, Bluetooth when it can't.",
              ),
              option(
                CheckInMethodPref.nfc,
                'NFC (tap)',
                'Always hold your phone to the terminal.',
              ),
              option(
                CheckInMethodPref.bluetooth,
                'Bluetooth',
                bleOn
                    ? 'Always check in by staying near the terminal. Use this '
                          'if tapping keeps failing on your phone.'
                    : 'Not switched on for your institution yet.',
                enabled: bleOn,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
