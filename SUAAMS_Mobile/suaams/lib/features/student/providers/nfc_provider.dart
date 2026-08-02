import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
// studentServiceProvider already exists here (used for the dashboard
// fetch) -- reusing it instead of creating a second StudentService
// instance/provider just for the beacon mint call.
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/features/student/data/student_service.dart' show CheckinStatusResult;
import 'package:suaams/core/network/auth_retry.dart';

enum NfcCheckInStatus {
  idle,
  authenticating,
  broadcasting,
  // Broadcasting has stopped (3s window closed) but confirmation polling
  // is still running -- distinct from `broadcasting` so the UI stops
  // showing the radar/countdown for a signal that's no longer being sent.
  confirming,
  success,
  // Confirmation polling ran out its window with no server-side
  // confirmation. Deliberately NOT the same as `error`: the check-in may
  // well have worked (slow POST still in flight, cold-starting backend,
  // etc.) -- this state means "unknown", not "failed".
  unconfirmed,
  // The broadcast window closed and no reader ever engaged the HCE
  // service at all (see SuaamsHceService.wasTapDetected()) -- distinct
  // from `unconfirmed`: there's nothing ambiguous here, we know for
  // certain nothing was in range, so there's no point waiting out the
  // full confirmation-poll window.
  noHardwareDetected,
  // A reader DID read the token and Flask DID answer, but the answer was
  // "you're not registered for this course" -- a definite, permanent
  // failure (won't resolve by waiting), so confirmation polling stops
  // immediately rather than running out its full window.
  notEnrolled,
  error,
}

class NfcCheckInState {
  final NfcCheckInStatus status;
  final int secondsRemaining; // Countdown for the 3-second broadcast window
  final String? errorMessage;
  final String? courseCode; // Set on a confirmed check-in or a notEnrolled result

  NfcCheckInState({
    this.status = NfcCheckInStatus.idle,
    this.secondsRemaining = 0,
    this.errorMessage,
    this.courseCode,
  });

  NfcCheckInState copyWith({
    NfcCheckInStatus? status,
    int? secondsRemaining,
    String? errorMessage,
    String? courseCode,
  }) {
    return NfcCheckInState(
      status: status ?? this.status,
      secondsRemaining: secondsRemaining ?? this.secondsRemaining,
      errorMessage: errorMessage ?? this.errorMessage,
      courseCode: courseCode ?? this.courseCode,
    );
  }
}

// OPTIMIZATION: Leveraged absolute type inference to prevent generic bound mismatch on Riverpod 3.x
final nfcCheckInProvider = NotifierProvider.autoDispose(
  NfcCheckInNotifier.new,
);

class NfcCheckInNotifier extends Notifier<NfcCheckInState> {
  late final LocalAuthentication _localAuth;
  Timer? _broadcastTimer;
  Timer? _confirmationTimer;

  // Confirmation polling runs on its own clock, independent of the 3s
  // broadcast window. It starts the same moment broadcasting does, but
  // keeps going for longer than the broadcast itself -- specifically to
  // absorb a slow/cold-starting Flask response (Render free-tier cold
  // starts can run several seconds) without mistaking that for a failed
  // check-in.
  static const int _confirmationWindowSeconds = 10;
  int _confirmationTicks = 0;

  @override
  NfcCheckInState build() {
    _localAuth = LocalAuthentication();

    // Captured here, NOT inside onDispose below -- calling ref.read() from
    // inside an onDispose callback trips Riverpod's reentrancy guard
    // ("Cannot use Ref or modify other providers inside life-cycles/
    // selectors", _debugCallbackStack == 0), since onDispose already runs
    // as part of Riverpod's own internal teardown sequence and doesn't
    // permit calling back into the container while that's in progress.
    // nfcServiceProvider is a plain Provider (always the same NfcService
    // instance for this container's lifetime), so capturing it once here
    // and closing over it below is both safe and sufficient.
    final nfcService = ref.read(nfcServiceProvider);

    // Register auto-cleanup to prevent memory leaks when sheet is closed
    ref.onDispose(() {
      _broadcastTimer?.cancel();
      _confirmationTimer?.cancel();
      nfcService.stopHceEmulation();
    });

    return NfcCheckInState();
  }

  // Enforces biometric check-in and starts 3-second transmission window
  Future<void> initiateCheckInProtocol() async {
    state = NfcCheckInState(status: NfcCheckInStatus.authenticating);

    try {
      // 1. Check OS hardware capability
      final canAuthenticateWithBiometrics = await _localAuth.canCheckBiometrics;
      final isDeviceSupported = await _localAuth.isDeviceSupported();

      if (!canAuthenticateWithBiometrics || !isDeviceSupported) {
        throw Exception('Hardware security mismatch: Biometrics are disabled or unsupported.');
      }

      // 2. Cross-Version Safe Biometric Call
      // This call is structurally supported on all versions of local_auth to prevent compile crashes
      final authenticated = await _localAuth.authenticate(
        localizedReason: 'Verify identity to activate attendance beacon',
      );

      if (!authenticated) {
        throw Exception('Identity verification failed.');
      }

      // 3. Mint a short-lived beacon token, then broadcast THAT over HCE --
      // not the long-lived session token. Broadcasting the session token
      // directly would mean anything that captured/relayed the NFC signal
      // could replay it as a valid API credential indefinitely; the beacon
      // token backend-mints with a 3s expiry (BEACON_TOKEN_TTL_SECONDS in
      // api/student.py), matching the strict 3-second anti-relay window
      // CLAUDE.md documents as canonical.
      //
      // Routed through withAuthRetry so a session token that happens to
      // expire right as the student taps "check in" gets silently
      // refreshed and retried, instead of failing this whole attempt and
      // forcing them to back out and try again manually.
      final beaconToken = await withAuthRetry(
        ref,
        (token) => ref.read(studentServiceProvider).mintCheckinBeacon(token),
      );

      state = NfcCheckInState(status: NfcCheckInStatus.broadcasting, secondsRemaining: 3);
      await ref.read(nfcServiceProvider).startHceEmulation(beaconToken);

      // Both timers start together. Broadcasting is capped at 3s
      // regardless of confirmation state -- that's the anti-relay security
      // window, not something to extend for confirmation's sake.
      // Confirmation polling runs longer, on its own schedule, and can
      // resolve the whole flow (success, notEnrolled) before the
      // broadcast window even closes if the ESP32/backend respond quickly.
      _startBroadcastCountdown();
      _startConfirmationPolling();

    } catch (e) {
      if (ref.mounted) {
        state = NfcCheckInState(
          status: NfcCheckInStatus.error,
          errorMessage: e.toString().replaceAll('Exception: ', ''),
        );
      }
      ref.read(nfcServiceProvider).stopHceEmulation();
    }
  }

  void _startBroadcastCountdown() {
    _broadcastTimer?.cancel();
    _broadcastTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      // If confirmation polling already resolved this attempt, it cancels
      // this timer directly -- this guard is cheap insurance against both
      // timers firing in the same event-loop tick before that
      // cancellation propagates.
      if (state.status != NfcCheckInStatus.broadcasting) {
        timer.cancel();
        return;
      }

      if (state.secondsRemaining <= 1) {
        timer.cancel();

        // HCE is purely passive -- this is the only way to know whether
        // any reader was ever actually in range during the broadcast.
        final tapped = await ref.read(nfcServiceProvider).wasTapDetected();
        await ref.read(nfcServiceProvider).stopHceEmulation();

        // Re-check after the awaits above: confirmation polling runs on
        // its own timer and may have already resolved this attempt while
        // we were waiting on those platform channel calls.
        if (!ref.mounted || state.status != NfcCheckInStatus.broadcasting) {
          return;
        }

        if (!tapped) {
          // Nothing for confirmation polling to ever find -- no point
          // waiting out its full window for something that could never
          // have succeeded.
          _confirmationTimer?.cancel();
          state = state.copyWith(status: NfcCheckInStatus.noHardwareDetected);
          _scheduleReturnToIdle();
          return;
        }

        state = state.copyWith(status: NfcCheckInStatus.confirming);
      } else {
        if (ref.mounted) {
          state = state.copyWith(secondsRemaining: state.secondsRemaining - 1);
        }
      }
    });
  }

  void _startConfirmationPolling() {
    _confirmationTimer?.cancel();
    _confirmationTicks = 0;

    _confirmationTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      _confirmationTicks++;

      CheckinStatusResult? result;
      try {
        result = await withAuthRetry(
          ref,
          (token) => ref.read(studentServiceProvider).checkCheckinStatus(token),
        );
      } catch (_) {
        // A single failed poll (network blip, etc.) doesn't abort the
        // whole confirmation attempt -- the actual check-in already
        // happened over NFC; this loop is purely for UI feedback. Treat
        // it the same as "not confirmed yet" and try again next tick.
        // (withAuthRetry itself still gets its normal chance to silently
        // refresh/logout on a genuine auth failure -- this catch just
        // stops that from also killing the polling loop.)
        result = null;
      }

      if (result != null && result.checkedIn) {
        timer.cancel();
        _broadcastTimer?.cancel();
        await ref.read(nfcServiceProvider).stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(status: NfcCheckInStatus.success, courseCode: result.courseCode);
          _scheduleReturnToIdle();
        }
        return;
      }

      // not_enrolled is definite and permanent -- waiting longer never
      // fixes it, so stop immediately rather than running out the full
      // confirmation window for a result that's already known.
      if (result != null && result.reason == 'not_enrolled') {
        timer.cancel();
        _broadcastTimer?.cancel();
        await ref.read(nfcServiceProvider).stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(status: NfcCheckInStatus.notEnrolled, courseCode: result.courseCode);
          _scheduleReturnToIdle();
        }
        return;
      }

      if (_confirmationTicks >= _confirmationWindowSeconds) {
        timer.cancel();
        _broadcastTimer?.cancel();
        await ref.read(nfcServiceProvider).stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(status: NfcCheckInStatus.unconfirmed);
          _scheduleReturnToIdle();
        }
      }
    });
  }

  void _scheduleReturnToIdle() {
    Future.delayed(const Duration(seconds: 3), () {
      if (ref.mounted) {
        state = NfcCheckInState(status: NfcCheckInStatus.idle);
      }
    });
  }
}
