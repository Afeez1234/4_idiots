/* STREAMING_CHUNK: Importing core dependencies... */
// This file handles the interactive, haptic-enabled NFC broadcast sheet.
// It integrates native biometrics, runs a secure 3-second transmission countdown,
// and displays a high-fidelity pulsing radar animation.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../providers/nfc_provider.dart';

class NfcBroadcastSheet extends ConsumerStatefulWidget {
  const NfcBroadcastSheet({super.key});

  // Static helper to cleanly summon the sheet from the dashboard screen
  static void show(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      barrierColor: Colors.black.withValues(alpha: 0.8),
      builder: (context) => const NfcBroadcastSheet(),
    );
  }

  @override
  ConsumerState<NfcBroadcastSheet> createState() => _NfcBroadcastSheetState();
}

class _NfcBroadcastSheetState extends ConsumerState<NfcBroadcastSheet>
    with SingleTickerProviderStateMixin {
  late AnimationController _radarController;

  @override
  void initState() {
    super.initState();
    /* STREAMING_CHUNK: Initializing radar animation controller... */
    // Infinite loop animation driving the neon concentric radar waves
    _radarController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();

    // Automatically trigger biometrics and transmission on mount
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _startSecureBroadcast();
    });
  }

  @override
  void dispose() {
    _radarController.dispose();
    super.dispose();
  }

  /* STREAMING_CHUNK: Executing biometric check and hardware HCE channel... */
  Future<void> _startSecureBroadcast() async {
    // 1. Fire a light tactile trigger indicating biometric prompt appearance
    HapticFeedback.lightImpact();

    // 2. Start the Riverpod state machine (Triggers biometric verification & HCE)
    await ref.read(nfcCheckInProvider.notifier).initiateCheckInProtocol();
  }

  @override
  Widget build(BuildContext context) {
    /* STREAMING_CHUNK: Reading active state slices... */
    final nfcState = ref.watch(nfcCheckInProvider);
    final colorScheme = Theme.of(context).colorScheme;

    // Monitor status to trigger hardware-synchronized haptic notifications
    ref.listen<NfcCheckInState>(nfcCheckInProvider, (previous, next) {
      if (next.status == NfcCheckInStatus.broadcasting) {
        // Continuous light tick simulating active radio transmission
        HapticFeedback.selectionClick();
      } else if (next.status == NfcCheckInStatus.success) {
        // Successful check-in verified by ESP32 handshake
        HapticFeedback.vibrate();
      } else if (next.status == NfcCheckInStatus.error) {
        // Security or transmission failure
        HapticFeedback.heavyImpact();
      }
    });

    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        border: Border.all(
          color: colorScheme.outline.withValues(alpha: 0.1),
        ),
      ),
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          /* STREAMING_CHUNK: Building structural sheet handle... */
          // Draggable indicator
          Container(
            width: 40,
            height: 4,
            decoration: BoxDecoration(
              color: colorScheme.onSurface.withValues(alpha: 0.2),
              borderRadius: BorderRadius.circular(2),
            ),
          ),
          const SizedBox(height: 32),

          /* STREAMING_CHUNK: Branching UI states based on nfcCheckInProvider... */
          if (nfcState.status == NfcCheckInStatus.authenticating) ...[
            _buildAuthenticatingState(colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.broadcasting) ...[
            _buildBroadcastingState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.success) ...[
            _buildSuccessState(colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.error) ...[
            _buildErrorState(nfcState, colorScheme),
          ] else ...[
            _buildIdleState(colorScheme),
          ],

          const SizedBox(height: 32),

          /* STREAMING_CHUNK: Generating cancel override button... */
          TextButton(
            style: TextButton.styleFrom(
              minimumSize: const Size(double.infinity, 56),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            onPressed: () {
              ref.invalidate(nfcCheckInProvider);
              Navigator.pop(context);
            },
            child: Text(
              'CANCEL PROTOCOL',
              style: TextStyle(
                color: colorScheme.onSurface.withValues(alpha: 0.5),
                letterSpacing: 2,
                fontWeight: FontWeight.bold,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /* STREAMING_CHUNK: Constructing state-specific layout widgets... */
  // 1. Idle Initial State
  Widget _buildIdleState(ColorScheme colorScheme) {
    return Column(
      children: [
        const Icon(Icons.contactless_rounded, size: 64, color: Colors.grey),
        const SizedBox(height: 24),
        const Text(
          'PROTOCOL IDLE',
          style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 2),
        ),
        const SizedBox(height: 8),
        Text(
          'Awaiting initialization signal...',
          style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 12),
        ),
      ],
    );
  }

  // 2. Authenticating State (Biometric Lock)
  Widget _buildAuthenticatingState(ColorScheme colorScheme) {
    return Column(
      children: [
        CircularProgressIndicator(color: colorScheme.primary, strokeWidth: 3),
        const SizedBox(height: 24),
        const Text(
          'VERIFYING IDENTITY',
          style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 2),
        ),
        const SizedBox(height: 8),
        Text(
          'Please verify biometric key on your terminal...',
          style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 12),
        ),
      ],
    );
  }

  // 3. Broadcasting State (Concentric Pulse Radar + Countdown)
  // DEEP FIX 1: Restored parameter signature (NfcCheckInState state) to solve undefined compiler error
  Widget _buildBroadcastingState(NfcCheckInState state, ColorScheme colorScheme) {
    return Column(
      children: [
        // Concentric animated radar waves
        SizedBox(
          width: 140,
          height: 140,
          child: AnimatedBuilder(
            animation: _radarController,
            builder: (context, child) {
              return CustomPaint(
                painter: _RadarWavePainter(
                  progress: _radarController.value,
                  color: colorScheme.primary,
                ),
                child: Center(
                  child: Container(
                    width: 56,
                    height: 56,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: colorScheme.primary,
                    ),
                    child: const Icon(
                      Icons.contactless_rounded,
                      color: Colors.white,
                      size: 28,
                    ),
                  ),
                ),
              );
            },
          ),
        ),
        const SizedBox(height: 32),
        Text(
          'BEAMING ATTENDANCE SIGNAL: ${state.secondsRemaining}s',
          style: const TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            fontFamily: 'JetBrains Mono',
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Hold your terminal close to the door sensor...',
          style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 12),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 4. Success Verified State (Green Check)
  Widget _buildSuccessState(ColorScheme colorScheme) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: Color(0xFF10B981), // Solid Emerald Green
          ),
          child: const Icon(Icons.check_rounded, color: Colors.white, size: 36),
        ),
        const SizedBox(height: 24),
        const Text(
          'ATTENDANCE VERIFIED',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: Color(0xFF10B981),
          ),
        ),
        const SizedBox(height: 8),
        Text(
          'Your signature has been committed to database ledger.',
          style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 12),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 5. Error Failure State (Red Warning)
  // DEEP FIX 2: Restored parameter signature (NfcCheckInState state) to solve undefined compiler error
  Widget _buildErrorState(NfcCheckInState state, ColorScheme colorScheme) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: colorScheme.error,
          ),
          child: const Icon(Icons.close_rounded, color: Colors.white, size: 36),
        ),
        const SizedBox(height: 24),
        Text(
          'CHECK-IN ABORTED',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: colorScheme.error,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            state.errorMessage ?? 'Unknown security error.',
            style: TextStyle(color: colorScheme.onSurface.withValues(alpha: 0.5), fontSize: 12),
            textAlign: TextAlign.center,
          ),
        ),
      ],
    );
  }
}

/* STREAMING_CHUNK: Writing custom painters for concentric waves... */
class _RadarWavePainter extends CustomPainter {
  final double progress;
  final Color color;

  _RadarWavePainter({required this.progress, required this.color});

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final maxRadius = size.width / 2;

    // We paint 3 concentric waves offset in phases
    for (int i = 0; i < 3; i++) {
      final currentProgress = (progress + (i / 3)) % 1.0;
      final radius = maxRadius * currentProgress;
      final opacity = (1.0 - currentProgress).clamp(0.0, 1.0);

      final paint = Paint()
        ..color = color.withValues(alpha: opacity * 0.4)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0;

      canvas.drawCircle(center, radius, paint);
    }
  }

  @override
  bool shouldRepaint(covariant _RadarWavePainter oldDelegate) {
    return oldDelegate.progress != progress || oldDelegate.color != color;
  }
}