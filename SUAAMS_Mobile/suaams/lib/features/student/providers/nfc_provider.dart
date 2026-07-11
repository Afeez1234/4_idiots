import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../data/nfc_service.dart';
import '../../auth/providers/auth_provider.dart';

enum NfcStatus { idle, broadcasting, success, error }

class NfcState {
  final NfcStatus status;
  final String? errorMessage;

  NfcState({this.status = NfcStatus.idle, this.errorMessage});

  NfcState copyWith({NfcStatus? status, String? errorMessage}) {
    return NfcState(
      status: status ?? this.status,
      errorMessage: errorMessage ?? this.errorMessage,
    );
  }
}

// Provide the hardware service
final nfcServiceProvider = Provider<NfcService>((ref) => NfcService());

// The state notifier that your Dashboard UI will listen to
final nfcProvider = NotifierProvider.autoDispose<NfcNotifier, NfcState>(
  NfcNotifier.new,
);

class NfcNotifier extends Notifier<NfcState> {
  bool _isTransmissionRunning = false;

  @override
  NfcState build() => NfcState();

  Future<void> startTransmission() async {
    if (_isTransmissionRunning) {
      return;
    }

    _isTransmissionRunning = true;
    final service = ref.read(nfcServiceProvider);

    // 1. Alert the UI to open the Radar Modal
    state = NfcState(status: NfcStatus.broadcasting);

    try {
      final user = ref.read(authProvider).user;
      if (user == null) {
        throw Exception("Session corrupted. Please log in again.");
      }

      // 2. Generate the secure APDU Payload (Student ID + Active Session Token)
      final payload = "${user.id}:${user.token}";

      await service.startEmulation(payload);

      // 3. Keep the HCE channel open. In a full production app, your ESP32
      // would scan this, hit your Flask backend, and the backend would push
      // a WebSocket event to the app to confirm.
      // For now, we simulate the 3-second physical tap window.
      await Future.delayed(const Duration(seconds: 3));

      if (!ref.mounted) {
        await service.stopEmulation();
        return;
      }

      // 4. Teardown the channel and trigger the Success UI
      await service.stopEmulation();
      if (!ref.mounted) {
        return;
      }

      state = NfcState(status: NfcStatus.success);

      // Hold the success screen for 2 seconds before automatically closing
      await Future.delayed(const Duration(seconds: 2));
      if (!ref.mounted) {
        return;
      }

      state = NfcState(status: NfcStatus.idle);
    } catch (e) {
      await service.stopEmulation();
      if (!ref.mounted) {
        return;
      }

      state = NfcState(
        status: NfcStatus.error,
        errorMessage: e.toString().replaceAll('Exception: ', ''),
      );

      // Hold the error screen for 3 seconds before closing
      await Future.delayed(const Duration(seconds: 3));
      if (!ref.mounted) {
        return;
      }

      state = NfcState(status: NfcStatus.idle);
    } finally {
      _isTransmissionRunning = false;
    }
  }

  // Allows the user to manually abort the scan from the UI
  Future<void> cancelTransmission() async {
    _isTransmissionRunning = false;
    final service = ref.read(nfcServiceProvider);
    await service.stopEmulation();

    if (!ref.mounted) {
      return;
    }

    state = NfcState(status: NfcStatus.idle);
  }
}
