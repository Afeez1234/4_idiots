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
    // Animation driving the neon concentric radar waves. PERF FIX: no
    // longer calls ..repeat() here -- previously this ticked continuously
    // through the `authenticating` state (biometric prompt) too, even
    // though the radar UI isn't shown until `broadcasting` is reached in
    // _buildBroadcastingState. It's now started/stopped from the status
    // listener in build() below, in sync with when it's actually visible.
    _radarController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    );

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

    // Monitor status to trigger hardware-synchronized haptic notifications,
    // and (PERF FIX) to start/stop the radar animation so it only ticks
    // while the broadcasting UI is actually on screen.
    ref.listen<NfcCheckInState>(nfcCheckInProvider, (previous, next) {
      if (next.status == NfcCheckInStatus.broadcasting) {
        // Continuous light tick simulating active radio transmission
        HapticFeedback.selectionClick();
        if (!_radarController.isAnimating) {
          _radarController.repeat();
        }
      } else {
        // Any state other than "broadcasting" doesn't render the radar
        // widget, so stop the ticker rather than let it spin unseen.
        if (_radarController.isAnimating) {
          _radarController.stop();
        }
        if (next.status == NfcCheckInStatus.success) {
          // Successful check-in, server-confirmed via /checkin/status
          HapticFeedback.vibrate();
        } else if (next.status == NfcCheckInStatus.error) {
          // Security or transmission failure
          HapticFeedback.heavyImpact();
        } else if (next.status == NfcCheckInStatus.unconfirmed ||
            next.status == NfcCheckInStatus.noHardwareDetected) {
          // Deliberately distinct from error's heavyImpact -- both of
          // these are retry-friendly outcomes, not confirmed failures.
          HapticFeedback.mediumImpact();
        } else if (next.status == NfcCheckInStatus.notEnrolled) {
          // Definite, permanent failure -- same weight as a hard error,
          // even though the visual treatment below is deliberately
          // different (this isn't a security/hardware problem).
          HapticFeedback.heavyImpact();
        }
      }
    });

    return Container(
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainer,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(24)),
        border: Border.all(color: colorScheme.outline.withValues(alpha: 0.1)),
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
          ] else if (nfcState.status == NfcCheckInStatus.confirming) ...[
            _buildConfirmingState(colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.success) ...[
            _buildSuccessState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.unconfirmed) ...[
            _buildUnconfirmedState(colorScheme),
          ] else if (nfcState.status ==
              NfcCheckInStatus.noHardwareDetected) ...[
            _buildNoHardwareDetectedState(colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.notEnrolled) ...[
            _buildNotEnrolledState(nfcState, colorScheme),
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
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
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
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
        ),
      ],
    );
  }

  // 3. Broadcasting State (Concentric Pulse Radar + Countdown)
  // DEEP FIX 1: Restored parameter signature (NfcCheckInState state) to solve undefined compiler error
  Widget _buildBroadcastingState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
    return Column(
      children: [
        // Concentric animated radar waves
        SizedBox(
          width: 140,
          height: 140,
          // PERF FIX: RepaintBoundary isolates this 60fps radar animation
          // from the countdown text and Cancel button below it, which don't
          // need to repaint on every animation tick.
          child: RepaintBoundary(
            child: AnimatedBuilder(
              animation: _radarController,
              // PERF FIX: this center icon is static -- it never changes
              // while broadcasting -- so it's built once here and passed
              // through as `child` instead of being reconstructed inside
              // `builder` on every one of the ~60 ticks/sec this
              // AnimationController fires. AnimatedBuilder's `child` param
              // exists specifically so builder can reuse a static subtree
              // instead of rebuilding it every frame; it just wasn't being
              // used before.
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
              builder: (context, child) {
                return CustomPaint(
                  painter: _RadarWavePainter(
                    progress: _radarController.value,
                    color: colorScheme.primary,
                  ),
                  child: child,
                );
              },
            ),
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
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 4. Success Verified State (Green Check)
  // Only reached once /checkin/status has actually confirmed an Attendance
  // row exists -- see NfcCheckInNotifier's confirmation polling. Shows the
  // confirmed course code when the backend returned one.
  Widget _buildSuccessState(NfcCheckInState state, ColorScheme colorScheme) {
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
          state.courseCode != null
              ? 'Checked in for ${state.courseCode}.'
              : 'Your signature has been committed to database ledger.',
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 4b. Confirming State -- broadcast window closed, still polling
  // /checkin/status for server-side confirmation. No radar here: nothing
  // is being transmitted anymore, this is purely "waiting to hear back".
  Widget _buildConfirmingState(ColorScheme colorScheme) {
    return Column(
      children: [
        CircularProgressIndicator(color: colorScheme.primary, strokeWidth: 3),
        const SizedBox(height: 24),
        const Text(
          'CONFIRMING',
          style: TextStyle(fontWeight: FontWeight.bold, letterSpacing: 2),
        ),
        const SizedBox(height: 8),
        Text(
          'Waiting for the terminal to confirm your check-in...',
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 4c. Unconfirmed State (Amber) -- confirmation window ran out with no
  // answer. Deliberately NOT styled like the red error state below: this
  // means "unknown", not "failed" -- the tap may well have worked.
  Widget _buildUnconfirmedState(ColorScheme colorScheme) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: Color(0xFFF59E0B), // Amber
          ),
          child: const Icon(
            Icons.help_outline_rounded,
            color: Colors.white,
            size: 36,
          ),
        ),
        const SizedBox(height: 24),
        const Text(
          'COULD NOT CONFIRM',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: Color(0xFFF59E0B),
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            'Signal was sent, but we couldn\'t confirm it reached the terminal in time. Check your dashboard in a moment.',
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.5),
              fontSize: 12,
            ),
            textAlign: TextAlign.center,
          ),
        ),
      ],
    );
  }

  // 4d. No Hardware Detected State (Amber) -- broadcast window closed and
  // no reader ever engaged the HCE service at all (see
  // SuaamsHceService.wasTapDetected()). Same amber "retry-friendly" tier
  // as Unconfirmed above, but a distinct icon/message: this one is
  // certain, not ambiguous -- nothing was in range, not "we don't know".
  Widget _buildNoHardwareDetectedState(ColorScheme colorScheme) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: Color(0xFFF59E0B), // Amber
          ),
          child: const Icon(
            Icons.search_off_rounded,
            color: Colors.white,
            size: 36,
          ),
        ),
        const SizedBox(height: 24),
        const Text(
          'NO TERMINAL DETECTED',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: Color(0xFFF59E0B),
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            'No reader responded during the transmission window. Hold your phone closer to the terminal and try again.',
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.5),
              fontSize: 12,
            ),
            textAlign: TextAlign.center,
          ),
        ),
      ],
    );
  }

  // 4e. Not Enrolled State (Red) -- a reader DID read the token and Flask
  // DID answer, but with "you're not registered for this course". Styled
  // like the hard error state below (this is definite and permanent, not
  // ambiguous), but with its own icon/copy pointing at the real cause
  // instead of a generic security/hardware message.
  Widget _buildNotEnrolledState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: colorScheme.error,
          ),
          child: const Icon(
            Icons.person_off_rounded,
            color: Colors.white,
            size: 36,
          ),
        ),
        const SizedBox(height: 24),
        Text(
          'NOT REGISTERED',
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
            state.courseCode != null
                ? 'You\'re not registered for ${state.courseCode}. Contact your department if this looks wrong.'
                : 'You\'re not registered for this course. Contact your department if this looks wrong.',
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.5),
              fontSize: 12,
            ),
            textAlign: TextAlign.center,
          ),
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
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.5),
              fontSize: 12,
            ),
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
