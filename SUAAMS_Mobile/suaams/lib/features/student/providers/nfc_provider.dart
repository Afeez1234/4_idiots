import 'dart:async';
import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
// studentServiceProvider already exists here (used for the dashboard
// fetch) -- reusing it instead of creating a second StudentService
// instance/provider just for the beacon mint call. studentDashboardProvider
// is imported for the same reason: a confirmed check-in has to invalidate
// it or the attendance tab keeps showing pre-check-in data.
import 'package:suaams/features/student/providers/student_provider.dart';
// The home screen's "TODAY'S PROTOCOL" list and the per-course attendance
// history view. Both show attendance and both are cached, so both need
// invalidating when a check-in lands.
import 'package:suaams/features/student/providers/today_schedule_provider.dart';
import 'package:suaams/features/student/providers/course_attendance_history_provider.dart';
import 'package:suaams/features/student/data/student_service.dart'
    show CheckinStatusResult;
// Bluetooth fallback: the scanner, and the one rule for choosing a channel.
import 'package:suaams/features/student/data/ble_scan_service.dart';
import 'package:suaams/features/student/providers/checkin_method_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/core/services/security_service.dart';
import 'package:suaams/core/network/user_facing_error.dart';

enum NfcCheckInStatus {
  idle,
  authenticating,
  broadcasting,
  // Bluetooth: listening for the terminal's rotating code. The BLE
  // counterpart of `broadcasting` -- the phone receives instead of sends.
  scanning,
  // Broadcasting has stopped (window closed) but confirmation polling
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
  // This phone can't tap in right now: NFC is off, missing, or it's an
  // iPhone (see NfcCheckInState.availability). Checked before the
  // fingerprint prompt, so nothing was minted or broadcast. Deliberately
  // not `error`: the student did nothing wrong, and NFC-off is fixable.
  nfcUnavailable,
  // Bluetooth can't scan right now: off, permission missing, Location off
  // (Android 11 and older), or no BLE. See NfcCheckInState.bleReadiness.
  // Checked before the fingerprint prompt, like nfcUnavailable.
  bleUnavailable,
  error,
}

class NfcCheckInState {
  final NfcCheckInStatus status;
  final int secondsRemaining; // Countdown for the broadcast window
  final String? errorMessage;
  final String?
  courseCode; // Set on a confirmed check-in or a notEnrolled result
  // Why the phone can't tap in. Set only with status nfcUnavailable.
  final NfcAvailability? availability;
  // Which channel this attempt is using, so shared states (confirming,
  // noHardwareDetected, success) can word themselves correctly.
  final CheckInChannel channel;
  // Why Bluetooth can't scan. Set only with status bleUnavailable.
  final BleReadiness? bleReadiness;
  // Bluetooth: the terminal has been heard, but faintly ("move closer").
  final bool weakSignal;

  NfcCheckInState({
    this.status = NfcCheckInStatus.idle,
    this.secondsRemaining = 0,
    this.errorMessage,
    this.courseCode,
    this.availability,
    this.channel = CheckInChannel.nfc,
    this.bleReadiness,
    this.weakSignal = false,
  });

  NfcCheckInState copyWith({
    NfcCheckInStatus? status,
    int? secondsRemaining,
    String? errorMessage,
    String? courseCode,
    NfcAvailability? availability,
    CheckInChannel? channel,
    BleReadiness? bleReadiness,
    bool? weakSignal,
  }) {
    return NfcCheckInState(
      status: status ?? this.status,
      secondsRemaining: secondsRemaining ?? this.secondsRemaining,
      errorMessage: errorMessage ?? this.errorMessage,
      courseCode: courseCode ?? this.courseCode,
      availability: availability ?? this.availability,
      channel: channel ?? this.channel,
      bleReadiness: bleReadiness ?? this.bleReadiness,
      weakSignal: weakSignal ?? this.weakSignal,
    );
  }
}

/// Whether this phone can tap in, for the entry points (home session card,
/// ID card button) to grey themselves out BEFORE the sheet opens. The sheet
/// itself re-checks on every attempt rather than trusting this cached value,
/// since NFC can be switched off between the two. Invalidate it on app
/// resume: the student may have just toggled NFC in system settings.
final nfcAvailabilityProvider = FutureProvider.autoDispose<NfcAvailability>(
  (ref) => ref.read(nfcServiceProvider).getAvailability(),
);

// OPTIMIZATION: Leveraged absolute type inference to prevent generic bound mismatch on Riverpod 3.x
final nfcCheckInProvider = NotifierProvider.autoDispose(NfcCheckInNotifier.new);

class NfcCheckInNotifier extends Notifier<NfcCheckInState> {
  // BUG FIX: was `late final LocalAuthentication _localAuth;` assigned
  // inside build() (`_localAuth = LocalAuthentication();`). late final
  // permits exactly one assignment per INSTANCE, but build() isn't
  // guaranteed to run only once per instance -- Riverpod can re-invoke it
  // on the same Notifier object (e.g. on hot reload during active
  // development, which re-runs build() without necessarily reconstructing
  // a fresh instance first). The second call hit the second assignment and
  // threw LateInitializationError. A field initializer runs exactly once,
  // at object construction -- a genuinely different, earlier event than
  // build() -- which sidesteps the whole problem. No `late` needed either:
  // LocalAuthentication() doesn't depend on anything only available inside
  // build() (no `ref`, no per-build state).
  final LocalAuthentication _localAuth = LocalAuthentication();

  // Hoisted so the cleanup path never has to touch `ref`.
  //
  // This is the fix for the dispose race that used to leave a live beacon
  // readable from native memory. Cleanup used to be written as
  // `ref.read(nfcServiceProvider).stopHceEmulation()`, which throws
  // UnmountedRefException once the provider is disposed -- and the two
  // places that needed it (the catch block and the countdown timer) were
  // both reachable AFTER disposal, precisely when it mattered. A plain
  // object reference keeps working past disposal, so the wipe can no longer
  // fail because of Riverpod's lifecycle.
  //
  // Deliberately not `final`: build() can re-run on the same instance, and
  // a second final assignment would throw the same LateInitializationError
  // described above.
  NfcService? _nfcService;
  // Hoisted for the same reason as _nfcService.
  BleScanService? _bleScanner;

  Timer? _broadcastTimer;
  Timer? _confirmationTimer;
  Timer? _idleTimer;

  // Confirmation polling runs on its own clock, independent of the 3s
  // broadcast window. It starts the same moment broadcasting does, but
  // keeps going for longer than the broadcast itself.
  //
  // This has to outlast the TERMINAL's own round-trip, not just the phone's
  // broadcast. By the time a tap is confirmed, the data path is
  // phone -> ESP32 -> Flask -> MySQL -> Flask -> phone, and the ESP32's
  // POST is the slow leg: measured at 5.0-5.3s against a Render free-tier
  // dyno, which is on its own longer than the whole window this used to
  // allow. The app therefore reported "could not confirm" for taps that had
  // in fact been recorded. 25s leaves comfortable headroom over a slow
  // terminal without leaving the sheet hanging for long.
  static const int _confirmationWindowSeconds = 25;

  // Guards against overlapping polls. The timer fires every second, but each
  // poll is an async HTTP call that can outlive its tick -- against a slow
  // backend it can take seconds. Without this, ticks pile up and issue
  // several concurrent requests for what should be one question, which
  // makes the backend slower still and the tick count meaningless.
  bool _pollInFlight = false;

  // The anti-relay security window (matches BEACON_TOKEN_TTL_SECONDS in
  // api/student.py) -- NOT the same clock as _confirmationWindowSeconds
  // above. Broadcasting must stop at this many seconds regardless of
  // confirmation state.
  //
  // Raised 3 -> 10 on 2026-09-27 after a hardware bench run. At 3s the
  // entire usable budget went to the student walking up to the terminal:
  // a warm-server check-in costs ~0.5s end to end, so only ~2.5s of slack
  // remained for the human part, which failed deterministically for anyone
  // not already standing at the reader. See BEACON_TOKEN_TTL_SECONDS in
  // beacon.py for the full relay-attack reasoning behind the new number.
  //
  // This is now only the UI countdown. The window that actually secures
  // the credential is enforced natively, from the server's own expires_in,
  // via a monotonic deadline in SuaamsHceService. This constant no longer
  // has to be exactly right for safety -- only for the displayed number.
  static const int _broadcastWindowSeconds = 10;
  int _confirmationTicks = 0;

  @override
  NfcCheckInState build() {
    // _localAuth assignment removed from here -- it's a field initializer
    // now (see the field declaration above for why).

    // Captured here, NOT inside onDispose below -- calling ref.read() from
    // inside an onDispose callback trips Riverpod's reentrancy guard
    // ("Cannot use Ref or modify other providers inside life-cycles/
    // selectors", _debugCallbackStack == 0), since onDispose already runs
    // as part of Riverpod's own internal teardown sequence and doesn't
    // permit calling back into the container while that's in progress.
    // nfcServiceProvider is a plain (non-autoDispose) Provider, so the same
    // NfcService instance lives for this container's lifetime and caching
    // the reference here is safe as well as necessary.
    _nfcService = ref.read(nfcServiceProvider);
    _bleScanner = ref.read(bleScanServiceProvider);

    // Register auto-cleanup to prevent memory leaks when sheet is closed
    ref.onDispose(() {
      _broadcastTimer?.cancel();
      _confirmationTimer?.cancel();
      _idleTimer?.cancel();
      // Note the field access rather than a local/ref.read -- this has to
      // keep working after the provider is gone, which is exactly when
      // dispose races land.
      _nfcService?.stopHceEmulation();
    });

    return NfcCheckInState();
  }

  // Enforces biometric check-in and starts the transmission window.
  //
  // [channel] forces NFC or Bluetooth (the sheet's "Try Bluetooth instead"
  // and retry buttons). Left null, the channel comes from the student's
  // preference, this phone's NFC and the server -- see
  // resolveCheckInChannel, which the entry points use too.
  Future<void> initiateCheckInProtocol({CheckInChannel? channel}) async {
    // Re-entrancy latch. There are two independent UI entry points
    // (student_home_screen's check-in button and the ID-card screen's),
    // each of which can open the sheet, and the sheet starts the protocol
    // from a post-frame callback. Two of those landing together used to run
    // the whole flow twice concurrently against one notifier: two
    // authenticate() calls, two mints, two setBeaconToken calls -- where
    // the second silently overwrote the first in native memory and the
    // second's timer was the only one that survived. The first beacon was
    // then orphaned with no wipe scheduled, the same leak as the dispose
    // race. Refuse to start a second run rather than half-doing both.
    if (state.status != NfcCheckInStatus.idle &&
        state.status != NfcCheckInStatus.error &&
        // Retried automatically when the student comes back from the NFC
        // or Bluetooth settings (see NfcBroadcastSheet's resume handler).
        state.status != NfcCheckInStatus.nfcUnavailable &&
        state.status != NfcCheckInStatus.bleUnavailable &&
        // "Try again" / "Try Bluetooth instead" start from here.
        state.status != NfcCheckInStatus.noHardwareDetected) {
      debugPrint('[NFC] ignoring check-in start: already ${state.status}');
      return;
    }

    // Cancel any pending return-to-idle from a previous attempt, so a stale
    // timer can't reset the state of the attempt we're about to begin.
    _idleTimer?.cancel();
    _idleTimer = null;

    state = NfcCheckInState(status: NfcCheckInStatus.authenticating);

    try {
      // 0. RASP gate -- runs before biometric auth, not after. A rooted
      // device with a hooking framework attached (Frida/Xposed) can force
      // local_auth's own authenticate() call below to report success
      // regardless of the real fingerprint/face result, so checking
      // biometrics FIRST would let a compromised device pass this whole
      // flow. SecurityService.isCompromised is populated by
      // main()'s startup RASP check (see security_service.dart);
      // no-op (always false) on a debug build, since enforcement there is
      // gated to release builds only.
      if (SecurityService.instance.isCompromised) {
        throw Exception(
          'Security check failed: ${SecurityService.instance.threatDescription}. '
          'Attendance check-in is disabled on this device.',
        );
      }

      // 0a. NFC or Bluetooth? Decided before anything else, because each
      // has its own "can this phone do it?" check below.
      final chosen = channel ?? await _resolveChannel();
      if (!ref.mounted) return;
      if (chosen == CheckInChannel.ble) {
        await _runBleCheckIn();
        return;
      }

      // 0b. Can this phone tap in at all? Before the fingerprint prompt, so
      // a student whose phone can't broadcast isn't asked to authenticate
      // for nothing, and no beacon is minted that could never be read.
      final availability =
          await _nfcService?.getAvailability() ?? NfcAvailability.ready;
      if (!ref.mounted) return;
      if (availability != NfcAvailability.ready) {
        state = NfcCheckInState(
          status: NfcCheckInStatus.nfcUnavailable,
          availability: availability,
        );
        return;
      }

      // 1-2. Fingerprint / face / device PIN. Shared with the Bluetooth path.
      if (!await _verifyIdentity()) return;

      // 3. Mint a short-lived beacon, then broadcast THAT over HCE -- not
      // the long-lived session token. Broadcasting the session token
      // directly would mean anything that captured/relayed the NFC signal
      // could replay it as a valid API credential indefinitely; the beacon
      // is minted with a 10s expiry (BEACON_TOKEN_TTL_SECONDS in
      // beacon.py), the anti-relay window -- 3s until 2026-09-27, raised
      // once a bench run showed the whole usable budget was going to the
      // student's walk-up. See that constant for the reasoning.
      //
      // Routed through withAuthRetry so a session token that happens to
      // expire right as the student taps "check in" gets silently
      // refreshed and retried, instead of failing this whole attempt and
      // forcing them to back out and try again manually.
      final mint = await withAuthRetry(
        ref,
        (token) => ref.read(studentServiceProvider).mintCheckinBeacon(token),
      );

      if (!ref.mounted) return;

      // BUG FIX: `state = ...broadcasting...` used to be set BEFORE this
      // await, not after. That line triggers an immediate UI rebuild (the
      // radar animation + "tap now" cue) the instant it executes -- before
      // the MethodChannel call below even started, let alone completed. A
      // tap landing in that window hit SuaamsHceService with beaconToken
      // still null, returning SW_NO_TOKEN (6A 88) -- deterministically, on
      // every attempt, since the UI invited a tap before the native side
      // was ready for one. Moving the state change to AFTER this await
      // guarantees the token is live natively before the user is ever
      // visually told to tap.
      debugPrint(
        '[NFC ${DateTime.now().millisecondsSinceEpoch}] Calling setBeaconToken...',
      );

      // Hand the server's own expires_in down so the native deadline
      // matches the window Flask will actually accept. It used to be
      // discarded on the Dart side, which is how the app's countdown and
      // the server's real expiry could drift apart by the length of the
      // mint round-trip.
      await _nfcService?.startHceEmulation(
        mint.beaconToken,
        ttlSeconds: mint.expiresIn,
      );
      debugPrint(
        '[NFC ${DateTime.now().millisecondsSinceEpoch}] setBeaconToken call completed.',
      );

      if (!ref.mounted) return;

      state = NfcCheckInState(
        status: NfcCheckInStatus.broadcasting,
        secondsRemaining: _broadcastWindowSeconds,
      );

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
          errorMessage: userFacingError(e),
        );
      }
      // Uses the hoisted field, not ref.read -- this line used to be the
      // one that threw when the provider was already disposed, taking the
      // wipe down with it. (And the native deadline is a further backstop
      // that doesn't depend on this call at all.)
      await _nfcService?.stopHceEmulation();
    }
  }

  /// The fingerprint / face / device-PIN gate, run before anything is
  /// minted, broadcast or submitted -- on both channels. Returns false if
  /// the sheet was dismissed meanwhile; throws if verification failed.
  Future<bool> _verifyIdentity() async {
    // 1. Check OS hardware capability
    final canAuthenticateWithBiometrics = await _localAuth.canCheckBiometrics;
    final isDeviceSupported = await _localAuth.isDeviceSupported();

    // The sheet can be dismissed (drag, back gesture, CANCEL) while any
    // of these platform calls are in flight, which disposes this
    // provider. Everything below -- including the catch block -- touches
    // `ref`, so without this guard a perfectly ordinary cancel turns
    // into UnmountedRefException.
    if (!ref.mounted) return false;

    if (!canAuthenticateWithBiometrics || !isDeviceSupported) {
      throw Exception(
        'Hardware security mismatch: Biometrics are disabled or unsupported.',
      );
    }

    // 2. Cross-Version Safe Biometric Call
    // This call is structurally supported on all versions of local_auth to prevent compile crashes
    final authenticated = await _localAuth.authenticate(
      localizedReason: 'Verify identity to activate attendance beacon',
    );

    // THE critical guard. This await is the widest window in the whole
    // flow: the student is looking at a system biometric prompt and may
    // reasonably swipe the sheet away. Previously nothing checked for
    // disposal here, so execution continued to push a beacon into native
    // memory on a disposed provider, and then both the state write below
    // and the catch block's cleanup threw -- leaving the token live and
    // readable with no wipe ever scheduled.
    if (!ref.mounted) return false;

    if (!authenticated) {
      throw Exception('Identity verification failed.');
    }
    return true;
  }

  /// Chooses NFC or Bluetooth when the caller didn't force one. Only asks
  /// the server when the answer could actually be Bluetooth, so a normal
  /// NFC check-in costs no extra request.
  Future<CheckInChannel> _resolveChannel() async {
    final pref = ref.read(checkInMethodPrefProvider);
    final nfc = await _nfcService?.getAvailability() ?? NfcAvailability.ready;
    final mightUseBle =
        pref == CheckInMethodPref.bluetooth ||
        (pref == CheckInMethodPref.automatic && nfc.cannotTapIn);
    var serverBle = false;
    if (mightUseBle && ref.mounted) {
      try {
        final methods = await withAuthRetry(
          ref,
          (token) => ref.read(studentServiceProvider).fetchCheckinMethods(token),
        );
        serverBle = methods.ble;
      } catch (e) {
        debugPrint('[BLE] methods unavailable, using NFC: $e');
      }
    }
    return resolveCheckInChannel(pref: pref, nfc: nfc, serverBle: serverBle);
  }

  /// Bluetooth check-in: readiness, fingerprint, scan, submit.
  ///
  /// The server answers in one request, so there's no confirmation polling.
  /// A stale code ("invalid_code") nearly always means the terminal rotated
  /// between hearing and submitting, so that gets one automatic rescan.
  Future<void> _runBleCheckIn() async {
    final scanner = _bleScanner;
    if (scanner == null) return;

    final readiness = await scanner.readiness();
    if (!ref.mounted) return;
    if (readiness != BleReadiness.ready) {
      state = NfcCheckInState(
        status: NfcCheckInStatus.bleUnavailable,
        channel: CheckInChannel.ble,
        bleReadiness: readiness,
      );
      return;
    }

    if (!await _verifyIdentity()) return;

    for (var attempt = 0; attempt < 2; attempt++) {
      state = NfcCheckInState(
        status: NfcCheckInStatus.scanning,
        channel: CheckInChannel.ble,
      );
      final heard = await scanner.scanForTerminal(
        onWeakSignal: () {
          if (ref.mounted &&
              state.status == NfcCheckInStatus.scanning &&
              !state.weakSignal) {
            state = state.copyWith(weakSignal: true);
          }
        },
      );
      if (!ref.mounted) return;

      if (heard == null) {
        state = NfcCheckInState(
          status: NfcCheckInStatus.noHardwareDetected,
          channel: CheckInChannel.ble,
        );
        return;
      }

      state = NfcCheckInState(
        status: NfcCheckInStatus.confirming,
        channel: CheckInChannel.ble,
      );
      final result = await withAuthRetry(
        ref,
        (token) => ref
            .read(studentServiceProvider)
            .submitBleCheckin(
              token,
              payloadHex: heard.payloadHex,
              rssi: heard.rssi,
            ),
      );
      if (!ref.mounted) return;

      if (result.recorded) {
        state = NfcCheckInState(
          status: NfcCheckInStatus.success,
          channel: CheckInChannel.ble,
          courseCode: result.courseCode,
        );
        _scheduleReturnToIdle();
        _invalidateAttendanceViews();
        return;
      }
      if (result.reason == 'no_active_session') {
        throw Exception('No active session for you right now.');
      }
      // invalid_code: rescan once and resubmit a fresh code.
      debugPrint('[BLE] code rejected (attempt ${attempt + 1}), rescanning');
    }
    throw Exception(
      "The terminal's code couldn't be verified. Make sure you're near the "
      'SUAAMS terminal and try again.',
    );
  }

  /// Asks for the Bluetooth scan permission, then retries if it's now ready.
  Future<void> requestBlePermission() async {
    final readiness = await _bleScanner?.requestPermission();
    if (!ref.mounted) return;
    if (readiness == BleReadiness.ready) {
      await initiateCheckInProtocol(channel: CheckInChannel.ble);
    } else if (readiness != null) {
      state = state.copyWith(bleReadiness: readiness);
    }
  }

  /// Android's own "turn on Bluetooth?" prompt, then a retry.
  Future<void> turnOnBluetooth() async {
    await _bleScanner?.turnOn();
    if (!ref.mounted) return;
    await initiateCheckInProtocol(channel: CheckInChannel.ble);
  }

  /// For a permanently denied permission. The sheet retries on resume.
  Future<void> openBleSettings() async {
    await _bleScanner?.openSettings();
  }

  /// Opens the system NFC toggle. The sheet re-runs the check when the app
  /// resumes, so the student doesn't have to reopen it after switching on.
  Future<void> openNfcSettings() async {
    await _nfcService?.openNfcSettings();
  }

  void _startBroadcastCountdown() {
    _broadcastTimer?.cancel();
    _broadcastTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      // If confirmation polling already resolved this attempt, it cancels
      // this timer directly -- this guard is cheap insurance against both
      // timers firing in the same event-loop tick before that
      // cancellation propagates. Checking `mounted` first matters: reading
      // `state` on a disposed notifier throws.
      if (!ref.mounted) {
        timer.cancel();
        return;
      }

      if (state.status != NfcCheckInStatus.broadcasting) {
        timer.cancel();
        return;
      }

      if (state.secondsRemaining <= 1) {
        timer.cancel();

        // HCE is purely passive -- this is the only way to know whether
        // any reader was ever actually in range during the broadcast.
        final tapped = await _nfcService?.wasTapDetected() ?? false;
        await _nfcService?.stopHceEmulation();

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
          // No return-to-idle here: this screen carries "Try again" and
          // "Try Bluetooth instead" buttons, and the latch above accepts a
          // new start from this state directly.
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

    _confirmationTimer = Timer.periodic(const Duration(seconds: 1), (
      timer,
    ) async {
      // Guard BEFORE the first await, not after. A callback that throws
      // from a timer becomes an unhandled async error, and this callback
      // previously dereferenced `ref` first thing -- so a sheet dismissed
      // mid-poll turned into a crash rather than a clean teardown.
      if (!ref.mounted) {
        timer.cancel();
        return;
      }

      // A previous poll is still outstanding -- don't stack another request
      // behind it. Skipping this tick is free; the outstanding one will
      // still resolve the attempt.
      if (_pollInFlight) {
        return;
      }

      _confirmationTicks++;
      _pollInFlight = true;

      CheckinStatusResult? result;
      try {
        result = await withAuthRetry(
          ref,
          (token) => ref.read(studentServiceProvider).checkCheckinStatus(token),
        );
      } catch (_) {
        // A single failed poll (network blip, a timeout, etc.) doesn't abort
        // the whole confirmation attempt -- the actual check-in already
        // happened over NFC; this loop is purely for UI feedback. Treat it
        // the same as "not confirmed yet" and try again next tick.
        // (withAuthRetry itself still gets its normal chance to silently
        // refresh on a genuine auth failure.)
        result = null;
      } finally {
        _pollInFlight = false;
      }

      // The await above means the provider may have been disposed (or the
      // attempt resolved on another timer) while the request was in
      // flight. Everything below touches ref/state, so re-check.
      if (!ref.mounted) {
        timer.cancel();
        return;
      }

      if (result != null && result.checkedIn) {
        timer.cancel();
        _broadcastTimer?.cancel();
        await _nfcService?.stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(
            status: NfcCheckInStatus.success,
            courseCode: result.courseCode,
          );
          _scheduleReturnToIdle();
          // Refresh everything that displays attendance.
          //
          // Without this, the check-in succeeds but the UI doesn't change:
          // records_view watches studentDashboardProvider, and the home
          // screen's "TODAY'S PROTOCOL" list watches todayScheduleProvider.
          // Both are cached Riverpod providers that only refetch when
          // something invalidates them, so attendance recorded by the
          // terminal would stay invisible until the student pulled to
          // refresh or restarted the app.
          _invalidateAttendanceViews();
        }
        return;
      }

      // not_enrolled is definite and permanent -- waiting longer never
      // fixes it, so stop immediately rather than running out the full
      // confirmation window for a result that's already known.
      if (result != null && result.reason == 'not_enrolled') {
        timer.cancel();
        _broadcastTimer?.cancel();
        await _nfcService?.stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(
            status: NfcCheckInStatus.notEnrolled,
            courseCode: result.courseCode,
          );
          _scheduleReturnToIdle();
        }
        return;
      }

      if (_confirmationTicks >= _confirmationWindowSeconds) {
        timer.cancel();
        _broadcastTimer?.cancel();
        await _nfcService?.stopHceEmulation();
        if (ref.mounted) {
          state = state.copyWith(status: NfcCheckInStatus.unconfirmed);
          _scheduleReturnToIdle();
        }
      }
    });
  }

  /// Drop the cached state of every view that shows attendance, so they
  /// refetch on next read.
  ///
  /// Called after the server confirms a check-in. These are autoDispose
  /// providers, so invalidating one that's already been disposed is a
  /// no-op rather than an error -- safe to call unconditionally.
  void _invalidateAttendanceViews() {
    ref.invalidate(studentDashboardProvider);
    ref.invalidate(todayScheduleProvider);
    ref.invalidate(courseAttendanceHistoryProvider);
  }

  void _scheduleReturnToIdle() {
    // Was an untracked Future.delayed. Two overlapping attempts left two
    // of these pending, and whichever survived would reset state out from
    // under the newer attempt -- e.g. knocking a fresh success back to idle
    // a moment after it landed. Store it so it can be cancelled.
    _idleTimer?.cancel();
    _idleTimer = Timer(const Duration(seconds: 3), () {
      if (ref.mounted) {
        state = NfcCheckInState(status: NfcCheckInStatus.idle);
      }
    });
  }
}
