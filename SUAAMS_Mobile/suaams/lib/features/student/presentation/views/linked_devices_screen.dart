import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/device_info_provider.dart';

// Read-only by design -- see get_device_info's doc-comment in
// api/student.py. This screen explains the admin-reset flow rather than
// offering a self-service unbind/reset, since a student being able to
// unbind their own device from inside the app would defeat the whole
// point of device binding (CLAUDE.md's threat model requires a physical
// ID check at the Admin Web Dashboard instead).
class LinkedDevicesScreen extends ConsumerWidget {
  const LinkedDevicesScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(deviceInfoProvider);
    final colorScheme = Theme.of(context).colorScheme;

    if (state.isLoading && state.data == null) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }

    final data = state.data;
    if (data == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Linked Devices')),
        body: Center(child: Text(state.errorMessage ?? 'No data available')),
      );
    }

    final bound = data.deviceBound;
    final statusColor = bound
        ? const Color(0xFF10B981)
        : const Color(0xFFF59E0B);

    return Scaffold(
      backgroundColor: colorScheme.surface,
      appBar: AppBar(
        title: const Text('Linked Devices'),
        backgroundColor: colorScheme.surface,
        elevation: 0,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: statusColor.withValues(alpha: 0.3)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        bound
                            ? Icons.phonelink_lock_rounded
                            : Icons.phonelink_erase_rounded,
                        color: statusColor,
                        size: 22,
                      ),
                      const SizedBox(width: 10),
                      Text(
                        bound ? 'DEVICE LINKED' : 'NO DEVICE LINKED',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w900,
                          letterSpacing: 1.5,
                          color: statusColor,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    bound
                        ? 'Your account is locked to this phone. Attendance check-ins only work from this device -- logging in from a different phone is blocked automatically.'
                        : 'No device is currently linked. Your next login will bind this account to that phone.',
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.5,
                      color: colorScheme.onSurface.withValues(alpha: 0.8),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 24),
            const Text(
              'GETTING A NEW PHONE?',
              style: TextStyle(
                fontSize: 10,
                letterSpacing: 1.5,
                color: Colors.grey,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: colorScheme.surfaceContainer.withValues(alpha: 0.72),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: colorScheme.outline.withValues(alpha: 0.1),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Device resets can\'t be done from inside the app -- this is intentional, so a lost or stolen phone can\'t be used to move your account elsewhere.',
                    style: TextStyle(
                      fontSize: 12,
                      height: 1.5,
                      color: colorScheme.onSurface.withValues(alpha: 0.7),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Bring your physical school ID to an administrator to request a reset.',
                    style: TextStyle(
                      fontSize: 12,
                      height: 1.5,
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onSurface.withValues(alpha: 0.9),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
