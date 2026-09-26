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

  /// Hands the freshly-minted beacon to the native HCE service.
  ///
  /// [ttlSeconds] is the server's own `expires_in` from the mint response,
  /// not a locally-guessed value. The native side arms its own deadline
  /// from this, so the window it enforces is exactly the window Flask will
  /// accept. Passing a guess here is how the app-side countdown and the
  /// server-side expiry drift apart.
  ///
  /// The token is 32 ASCII characters (see beacon.py), so the native
  /// service answers a reader with a single APDU exchange -- no chunking.
  Future<void> startHceEmulation(String payload, {int? ttlSeconds}) async {
    try {
      await _channel.invokeMethod('setBeaconToken', {
        'token': payload,
        // Null-aware element: the key is omitted entirely when we have no
        // server-supplied TTL, so Kotlin's call.argument<Int> sees a
        // missing key rather than an explicit null.
        'ttlSeconds': ?ttlSeconds,
      });
    } on PlatformException catch (e) {
      throw Exception('Hardware failure: ${e.message ?? e.code}');
    }
  }

  /// Asks the native side to drop the token now, rather than waiting out
  /// its deadline.
  ///
  /// This is an optimisation, not the safety mechanism. The token's window
  /// is enforced natively via a monotonic `SystemClock.elapsedRealtime()`
  /// deadline plus a self-scheduling clear, so it closes correctly even if
  /// this call never arrives -- which it previously could fail to do, when
  /// the provider was disposed mid-flow and both this method and the state
  /// write threw on an unmounted ref.
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
