/* STREAMING_CHUNK: Importing core dependencies... */
// This file handles the interactive, haptic-enabled NFC broadcast sheet.
// It integrates native biometrics, runs a secure transmission countdown,
// and displays a high-fidelity pulsing radar animation.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/features/student/data/nfc_service.dart'
    show NfcAvailability;
import 'package:suaams/features/student/providers/nfc_provider.dart';
import 'package:suaams/features/student/data/ble_scan_service.dart'
    show BleReadiness;
import 'package:suaams/features/student/providers/checkin_method_provider.dart'
    show CheckInChannel, checkinMethodsProvider;
import 'package:suaams/shared/utils/attendance_status.dart';

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

  /// The one-line hint under each check-in entry point (home session card,
  /// ID card button), worded to match what the sheet will show. Kept here so
  /// the two entry points and the sheet can't drift apart.
  static (IconData, String) entryHint(
    NfcAvailability availability, {
    CheckInChannel channel = CheckInChannel.nfc,
  }) {
    if (channel == CheckInChannel.ble) {
      return (
        Icons.bluetooth_searching_rounded,
        "You'll confirm with your fingerprint, then stay close to the "
            'terminal.',
      );
    }
    return switch (availability) {
      NfcAvailability.iphone => (
        Icons.info_outline_rounded,
        "iPhones can't tap in yet. Tell your lecturer before the class ends.",
      ),
      NfcAvailability.unsupported => (
        Icons.info_outline_rounded,
        "This phone doesn't have NFC. Tell your lecturer before the class "
            'ends.',
      ),
      NfcAvailability.off => (
        Icons.nfc_rounded,
        "NFC is off. You'll be asked to turn it on when you tap.",
      ),
      NfcAvailability.ready => (
        Icons.fingerprint_rounded,
        "You'll confirm with your fingerprint, then hold your phone to the "
            'terminal.',
      ),
    };
  }

  @override
  ConsumerState<NfcBroadcastSheet> createState() => _NfcBroadcastSheetState();
}

class _NfcBroadcastSheetState extends ConsumerState<NfcBroadcastSheet>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
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

    // Watches for the student returning from the NFC settings screen.
    WidgetsBinding.instance.addObserver(this);

    // Automatically trigger biometrics and transmission on mount
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _startSecureBroadcast();
    });
  }

  /// True once the check-in flow has reached a state it will not move on
  /// from without the user acting again. "Cancel" is the wrong verb here --
  /// there is nothing in flight to cancel, and on the success state it
  /// implies dismissing the sheet might undo a committed attendance record.
  static bool _isTerminalState(NfcCheckInStatus status) {
    switch (status) {
      case NfcCheckInStatus.success:
      case NfcCheckInStatus.unconfirmed:
      case NfcCheckInStatus.noHardwareDetected:
      case NfcCheckInStatus.notEnrolled:
      case NfcCheckInStatus.nfcUnavailable:
      case NfcCheckInStatus.bleUnavailable:
      case NfcCheckInStatus.error:
        return true;
      default:
        return false;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _radarController.dispose();
    super.dispose();
  }

  // Back from the NFC settings screen: run the check-in again. If NFC is now
  // on, this goes straight to the fingerprint prompt; if it's still off, the
  // same "NFC is off" state comes back. Only for the fixable case -- a phone
  // without NFC won't grow it while the student is in settings.
  @override
  void didChangeAppLifecycleState(AppLifecycleState lifecycle) {
    if (lifecycle != AppLifecycleState.resumed) return;
    final current = ref.read(nfcCheckInProvider);
    if (current.status == NfcCheckInStatus.nfcUnavailable &&
        current.availability == NfcAvailability.off) {
      _startSecureBroadcast();
    }
    // Back from Bluetooth / Location / app settings. needsPermission is
    // left out: its button asks in-app, and that dialog itself pauses and
    // resumes the app, which would otherwise start a second attempt.
    if (current.status == NfcCheckInStatus.bleUnavailable &&
        (current.bleReadiness == BleReadiness.off ||
            current.bleReadiness == BleReadiness.locationOff ||
            current.bleReadiness == BleReadiness.permissionBlocked)) {
      ref
          .read(nfcCheckInProvider.notifier)
          .initiateCheckInProtocol(channel: CheckInChannel.ble);
    }
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
      if (next.status == NfcCheckInStatus.broadcasting ||
          next.status == NfcCheckInStatus.scanning) {
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
            next.status == NfcCheckInStatus.noHardwareDetected ||
            next.status == NfcCheckInStatus.nfcUnavailable ||
            next.status == NfcCheckInStatus.bleUnavailable) {
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
          ] else if (nfcState.status == NfcCheckInStatus.scanning) ...[
            _buildScanningState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.confirming) ...[
            _buildConfirmingState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.success) ...[
            _buildSuccessState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.unconfirmed) ...[
            _buildUnconfirmedState(colorScheme),
          ] else if (nfcState.status ==
              NfcCheckInStatus.noHardwareDetected) ...[
            _buildNoHardwareDetectedState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.notEnrolled) ...[
            _buildNotEnrolledState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.nfcUnavailable) ...[
            _buildNfcUnavailableState(nfcState, colorScheme),
          ] else if (nfcState.status == NfcCheckInStatus.bleUnavailable) ...[
            _buildBleUnavailableState(nfcState, colorScheme),
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
              // Wording follows the state. "CANCEL PROTOCOL" on a screen
              // showing ATTENDANCE VERIFIED asks the user to cancel
              // something that has already finished, which reads as though
              // dismissing the sheet might undo it. Once the flow reaches a
              // terminal state the action is just "leave".
              _isTerminalState(nfcState.status)
                  ? 'CLOSE'
                  : 'CANCEL PROTOCOL',
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
        // Not const: reads onSurface from the theme. Colors.grey was a
        // #9E9E9E glyph on a near-white sheet in light mode -- visible, but
        // faint enough to look like a rendering fault rather than a design.
        Icon(
          Icons.contactless_rounded,
          size: 64,
          color: colorScheme.onSurface.withValues(alpha: 0.35),
        ),
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
          style: AppTheme.accent(weight: FontWeight.w700, letterSpacing: 2),
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
            color: AppStatus.success, // Solid Emerald Green
          ),
          child: const Icon(Icons.check_rounded, color: Colors.white, size: 36),
        ),
        const SizedBox(height: 24),
        const Text(
          'ATTENDANCE VERIFIED',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: AppStatus.success,
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
  Widget _buildConfirmingState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
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
          state.channel == CheckInChannel.ble
              // Bluetooth: the phone itself is asking the server.
              ? 'Checking the terminal\'s code with the server...'
              : 'Waiting for the terminal to confirm your check-in...',
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
            color: AppStatus.warning, // Amber
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
            color: AppStatus.warning,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            // The old copy said only "Check your dashboard in a moment",
            // which is a dead end: it left the student standing at a terminal
            // with no idea whether to tap again (which could double-record)
            // or walk away (which might cost them the session). The point of
            // the amber state is that this is genuinely UNKNOWN, so say that
            // plainly and tell them the one thing that resolves it.
            'Your attendance was probably recorded, but the terminal didn\'t '
            'confirm it back in time. Do not tap again — close this and check '
            'your Records tab; it updates within a minute.',
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.6),
              fontSize: 12,
              height: 1.45,
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
  Widget _buildNoHardwareDetectedState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
    final ble = state.channel == CheckInChannel.ble;
    // Offered on a failed NFC attempt when the server has Bluetooth on:
    // the "my NFC is flaky" escape hatch.
    final offerBle =
        !ble && (ref.watch(checkinMethodsProvider).value?.ble ?? false);
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: AppStatus.warning, // Amber
          ),
          child: const Icon(
            Icons.search_off_rounded,
            color: Colors.white,
            size: 36,
          ),
        ),
        const SizedBox(height: 24),
        Text(
          ble ? "COULDN'T HEAR THE TERMINAL" : 'NO TERMINAL DETECTED',
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: AppStatus.warning,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            ble
                ? 'No SUAAMS terminal was heard nearby. Move closer to it and '
                      'try again.'
                : 'No reader responded during the transmission window. Hold your phone closer to the terminal and try again.',
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.5),
              fontSize: 12,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        const SizedBox(height: 24),
        _actionButton(
          label: 'TRY AGAIN',
          icon: Icons.refresh_rounded,
          onPressed: () => ref
              .read(nfcCheckInProvider.notifier)
              .initiateCheckInProtocol(channel: state.channel),
        ),
        if (offerBle) ...[
          const SizedBox(height: 12),
          _actionButton(
            label: 'TRY BLUETOOTH INSTEAD',
            icon: Icons.bluetooth_rounded,
            primary: false,
            onPressed: () => ref
                .read(nfcCheckInProvider.notifier)
                .initiateCheckInProtocol(channel: CheckInChannel.ble),
          ),
        ],
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

  // 4f. NFC Unavailable -- this phone can't tap in right now, found before
  // the fingerprint prompt. Not red: nothing failed and the student did
  // nothing wrong. NFC-off is amber with a way to fix it; a phone that can
  // never tap in is neutral, with the one thing the student can do instead.
  Widget _buildNfcUnavailableState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
    final availability = state.availability ?? NfcAvailability.unsupported;
    final fixable = availability == NfcAvailability.off;

    final (
      IconData icon,
      String title,
      String message,
    ) = switch (availability) {
      NfcAvailability.off => (
        Icons.nfc_rounded,
        'NFC IS OFF',
        'Turn on NFC to tap in. Come back to this screen afterwards and '
            'check-in will continue.',
      ),
      NfcAvailability.iphone => (
        Icons.phonelink_off_rounded,
        "IPHONES CAN'T TAP IN YET",
        "Apple doesn't allow apps to use NFC this way. Tell your lecturer "
            'before the class ends.',
      ),
      _ => (
        Icons.phonelink_off_rounded,
        "THIS PHONE CAN'T TAP IN",
        "It doesn't have the NFC needed to check in at the terminal. Tell "
            'your lecturer before the class ends.',
      ),
    };
    final tone = fixable
        ? AppStatus.warning
        : colorScheme.onSurface.withValues(alpha: 0.55);

    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(shape: BoxShape.circle, color: tone),
          child: Icon(icon, color: Colors.white, size: 36),
        ),
        const SizedBox(height: 24),
        Text(
          title,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: fixable ? AppStatus.warning : null,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            message,
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.6),
              fontSize: 12,
              height: 1.45,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        if (fixable) ...[
          const SizedBox(height: 24),
          ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              minimumSize: const Size(double.infinity, 52),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              elevation: 0,
            ),
            onPressed: () =>
                ref.read(nfcCheckInProvider.notifier).openNfcSettings(),
            icon: const Icon(Icons.settings_rounded, size: 18),
            label: const Text(
              'OPEN NFC SETTINGS',
              style: TextStyle(letterSpacing: 1.5, fontWeight: FontWeight.bold),
            ),
          ),
        ],
        // Reached when NFC was chosen (setting = NFC, or Automatic on a
        // phone whose NFC is merely off) but the server has Bluetooth on.
        if (ref.watch(checkinMethodsProvider).value?.ble ?? false) ...[
          const SizedBox(height: 12),
          _actionButton(
            label: 'USE BLUETOOTH INSTEAD',
            icon: Icons.bluetooth_rounded,
            primary: false,
            onPressed: () => ref
                .read(nfcCheckInProvider.notifier)
                .initiateCheckInProtocol(channel: CheckInChannel.ble),
          ),
        ],
      ],
    );
  }

  // 4g. Scanning -- Bluetooth's counterpart to broadcasting: the same radar,
  // but the phone is listening for the terminal rather than being read.
  Widget _buildScanningState(NfcCheckInState state, ColorScheme colorScheme) {
    return Column(
      children: [
        SizedBox(
          width: 140,
          height: 140,
          // Same isolation as the broadcasting radar: only the waves repaint.
          child: RepaintBoundary(
            child: AnimatedBuilder(
              animation: _radarController,
              child: Center(
                child: Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: colorScheme.primary,
                  ),
                  child: const Icon(
                    Icons.bluetooth_searching_rounded,
                    color: Colors.white,
                    size: 28,
                  ),
                ),
              ),
              builder: (context, child) => CustomPaint(
                painter: _RadarWavePainter(
                  progress: _radarController.value,
                  color: colorScheme.primary,
                ),
                child: child,
              ),
            ),
          ),
        ),
        const SizedBox(height: 32),
        Text(
          state.weakSignal ? 'SIGNAL WEAK' : 'LISTENING FOR TERMINAL',
          style: AppTheme.accent(weight: FontWeight.w700, letterSpacing: 2),
        ),
        const SizedBox(height: 8),
        Text(
          state.weakSignal
              ? 'The terminal is faint. Move closer to it...'
              : 'Stay close to the SUAAMS terminal...',
          style: TextStyle(
            color: colorScheme.onSurface.withValues(alpha: 0.5),
            fontSize: 12,
          ),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }

  // 4h. Bluetooth Unavailable -- found before the fingerprint prompt, like
  // NFC Unavailable. Amber with a fix where one exists; neutral otherwise.
  Widget _buildBleUnavailableState(
    NfcCheckInState state,
    ColorScheme colorScheme,
  ) {
    final notifier = ref.read(nfcCheckInProvider.notifier);
    final readiness = state.bleReadiness ?? BleReadiness.unsupported;
    final fixable = readiness != BleReadiness.unsupported;
    final isIos = Theme.of(context).platform == TargetPlatform.iOS;

    final (String title, String message) = switch (readiness) {
      BleReadiness.off => (
        'BLUETOOTH IS OFF',
        isIos
            ? 'Turn on Bluetooth in Control Centre, then come back here.'
            : 'Turn on Bluetooth to check in near the terminal.',
      ),
      BleReadiness.needsPermission => (
        'ALLOW NEARBY DEVICES',
        'SUAAMS needs permission to listen for the terminal. It does not '
            'use your location.',
      ),
      BleReadiness.permissionBlocked => (
        'BLUETOOTH PERMISSION OFF',
        'Bluetooth permission was turned off for SUAAMS. Turn it on in '
            'Settings, then come back here.',
      ),
      BleReadiness.locationOff => (
        'LOCATION IS OFF',
        'On this Android version, listening for Bluetooth devices needs '
            'Location switched on. SUAAMS does not use your location.',
      ),
      _ => (
        "THIS PHONE CAN'T CHECK IN",
        "It doesn't support the Bluetooth needed to check in. Tell your "
            'lecturer before the class ends.',
      ),
    };

    final (String? actionLabel, IconData? actionIcon, VoidCallback? action) =
        switch (readiness) {
          BleReadiness.off when !isIos => (
            'TURN ON BLUETOOTH',
            Icons.bluetooth_rounded,
            notifier.turnOnBluetooth,
          ),
          BleReadiness.needsPermission => (
            'ALLOW',
            Icons.check_rounded,
            notifier.requestBlePermission,
          ),
          BleReadiness.permissionBlocked => (
            'OPEN SETTINGS',
            Icons.settings_rounded,
            notifier.openBleSettings,
          ),
          _ => (null, null, null),
        };

    final tone = fixable
        ? AppStatus.warning
        : colorScheme.onSurface.withValues(alpha: 0.55);

    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(shape: BoxShape.circle, color: tone),
          child: const Icon(
            Icons.bluetooth_disabled_rounded,
            color: Colors.white,
            size: 36,
          ),
        ),
        const SizedBox(height: 24),
        Text(
          title,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            letterSpacing: 2,
            color: fixable ? AppStatus.warning : null,
          ),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16.0),
          child: Text(
            message,
            style: TextStyle(
              color: colorScheme.onSurface.withValues(alpha: 0.6),
              fontSize: 12,
              height: 1.45,
            ),
            textAlign: TextAlign.center,
          ),
        ),
        if (action != null) ...[
          const SizedBox(height: 24),
          _actionButton(
            label: actionLabel!,
            icon: actionIcon!,
            onPressed: action,
          ),
        ],
      ],
    );
  }

  /// Full-width button used by the retry / fix-it states. `primary` is the
  /// one thing to do; secondary is an alternative.
  Widget _actionButton({
    required String label,
    required IconData icon,
    required VoidCallback onPressed,
    bool primary = true,
  }) {
    const minimumSize = Size(double.infinity, 52);
    final shape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(12),
    );
    final text = Text(
      label,
      style: const TextStyle(letterSpacing: 1.5, fontWeight: FontWeight.bold),
    );
    return primary
        ? ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              minimumSize: minimumSize,
              shape: shape,
              elevation: 0,
            ),
            onPressed: onPressed,
            icon: Icon(icon, size: 18),
            label: text,
          )
        : OutlinedButton.icon(
            style: OutlinedButton.styleFrom(
              minimumSize: minimumSize,
              shape: shape,
            ),
            onPressed: onPressed,
            icon: Icon(icon, size: 18),
            label: text,
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
