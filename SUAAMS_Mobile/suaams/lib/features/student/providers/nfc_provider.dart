import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
// studentServiceProvider already exists here (used for the dashboard
// fetch) -- reusing it instead of creating a second StudentService
// instance/provider just for the beacon mint call.
import 'package:suaams/features/student/providers/student_provider.dart';
import 'package:suaams/core/network/auth_retry.dart';

enum NfcCheckInStatus { idle, authenticating, broadcasting, success, error }

class NfcCheckInState {
  final NfcCheckInStatus status;
  final int secondsRemaining; // Countdown for the 3-second security envelope
  final String? errorMessage;

  NfcCheckInState({
    this.status = NfcCheckInStatus.idle,
    this.secondsRemaining = 0,
    this.errorMessage,
  });

  NfcCheckInState copyWith({
    NfcCheckInStatus? status,
    int? secondsRemaining,
    String? errorMessage,
  }) {
    return NfcCheckInState(
      status: status ?? this.status,
      secondsRemaining: secondsRemaining ?? this.secondsRemaining,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }
}

// OPTIMIZATION: Leveraged absolute type inference to prevent generic bound mismatch on Riverpod 3.x
final nfcCheckInProvider = NotifierProvider.autoDispose(
  NfcCheckInNotifier.new,
);

class NfcCheckInNotifier extends Notifier<NfcCheckInState> {
  late final LocalAuthentication _localAuth;
  Timer? _countdownTimer;

  @override
  NfcCheckInState build() {
    _localAuth = LocalAuthentication();

    // Register auto-cleanup to prevent memory leaks when sheet is closed
    ref.onDispose(() {
      _countdownTimer?.cancel();
      ref.read(nfcServiceProvider).stopHceEmulation();
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

      // 4. Enforce Strict 3-Second Transmit Envelope
      _startSecureCountdown();

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

  void _startSecureCountdown() {
    _countdownTimer?.cancel();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (timer) async {
      if (state.secondsRemaining <= 1) {
        // Window expired. Self-destruct emulation payload!
        _countdownTimer?.cancel();
        await ref.read(nfcServiceProvider).stopHceEmulation();
        
        if (ref.mounted) {
          state = NfcCheckInState(status: NfcCheckInStatus.success);
        }
        
        // Auto-close check-in card UI after brief delay
        Future.delayed(const Duration(seconds: 2), () {
          if (ref.mounted) {
            state = NfcCheckInState(status: NfcCheckInStatus.idle);
          }
        });
      } else {
        if (ref.mounted) {
          state = state.copyWith(secondsRemaining: state.secondsRemaining - 1);
        }
      }
    });
  }
}