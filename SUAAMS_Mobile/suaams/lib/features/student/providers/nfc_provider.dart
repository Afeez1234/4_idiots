import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';

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

      // 3. Begin NFC Emulation Channel
      final token = ref.read(authProvider).user?.token;
      if (token == null) throw Exception('Auth Session lost. Re-login.');

      state = NfcCheckInState(status: NfcCheckInStatus.broadcasting, secondsRemaining: 3);
      await ref.read(nfcServiceProvider).startHceEmulation(token);

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