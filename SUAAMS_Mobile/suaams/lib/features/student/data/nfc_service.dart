import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

final nfcServiceProvider = Provider<NfcService>((ref) => NfcService());

/// Bridges to SuaamsHceService, the custom native HostApduService
/// (android/app/src/main/kotlin/com/example/suaams/SuaamsHceService.kt)
/// that actually broadcasts the beacon token over NFC HCE. No third-party
/// HCE package involved -- nfc_host_card_emulation was evaluated and ruled
/// out (its AndroidHceService.kt only supports one fixed response per AID
/// match, no 61xx/GET RESPONSE chaining, and the beacon JWT needs
/// multi-exchange chunking to transmit).
class NfcService {
  static const MethodChannel _channel = MethodChannel('suaams/hce');

  /// Hands the freshly-minted beacon token to the native HCE service.
  /// Called right after mint_checkin_beacon succeeds (see
  /// nfc_provider.dart) -- native code holds this in memory only, it never
  /// fetches or refreshes a token itself.
  Future<void> startHceEmulation(String payload) async {
    try {
      await _channel.invokeMethod('setBeaconToken', {'token': payload});
    } on PlatformException catch (e) {
      throw Exception('Hardware failure: ${e.message ?? e.code}');
    }
  }

  /// Clears the token held natively. Called when the 3-second broadcast
  /// window closes (or on any error before it starts) -- defense in depth
  /// on top of the token's own short expiry, so a tap arriving after this
  /// point gets a clean "no token" response instead of a stale one.
  Future<void> stopHceEmulation() async {
    try {
      await _channel.invokeMethod('clearBeaconToken');
    } on PlatformException catch (e) {
      throw Exception('Failed to stop HCE: ${e.message ?? e.code}');
    }
  }

  /// Whether any reader actually engaged the HCE service since the last
  /// startHceEmulation() call. HCE is purely passive/reactive -- this is
  /// the only way the app can tell "nothing was ever nearby" apart from
  /// "something read it, but the backend never confirmed", which
  /// otherwise look identical from here. Fails safe to false (rather than
  /// throwing) on a platform-channel error, since a channel failure here
  /// shouldn't be read as "a reader definitely engaged".
  Future<bool> wasTapDetected() async {
    try {
      final result = await _channel.invokeMethod<bool>('wasTapDetected');
      return result ?? false;
    } on PlatformException catch (_) {
      return false;
    }
  }
}
