import 'package:flutter/foundation.dart';

/// This service abstracts the Android Host Card Emulation (HCE) implementation.
/// In production, this maps directly to the `nfc_host_card_emulation` package.
class NfcService {
  // We default to true here so you can test the UI on an Android Emulator
  // without crashing (since emulators lack physical NFC chips).
  final bool _isMockMode = true;

  Future<void> startEmulation(String payload) async {
    try {
      if (_isMockMode) {
        debugPrint('NFC MOCK: Broadcasting APDU Payload -> $payload');
        await Future.delayed(const Duration(milliseconds: 500));
        return;
      }

      /* 
      // REAL IMPLEMENTATION (Requires nfc_host_card_emulation package):
      final nfcState = await NfcHce.checkDeviceNfcState();
      if (nfcState != NfcState.enabled) {
        throw Exception('NFC is disabled or unsupported.');
      }

      if (!_isInitialized) {
        await NfcHce.init(
          // This AID must match the aid_list.xml in your AndroidManifest
          aid: Uint8List.fromList([0xF0, 0x39, 0x41, 0x48, 0x14, 0x81, 0x00]),
          permanentApduResponses: true,
          listenOnlyConfiguredPorts: false,
        );
        _isInitialized = true;
      }

      // Encode the auth payload into bytes and attach it to APDU Port 0
      final bytes = utf8.encode(payload);
      await NfcHce.addApduResponse(0, bytes);
      */
    } catch (e) {
      throw Exception('Hardware failure: $e');
    }
  }

  Future<void> stopEmulation() async {
    try {
      if (_isMockMode) {
        debugPrint('NFC MOCK: HCE Service Terminated.');
        await Future.delayed(const Duration(milliseconds: 500));
        return;
      }

      /*
      // REAL IMPLEMENTATION:
      await NfcHce.removeApduResponse(0);
      */
    } catch (e) {
      throw Exception('Failed to stop HCE: $e');
    }
  }
}
