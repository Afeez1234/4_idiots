package com.example.suaams

import io.flutter.embedding.android.FlutterFragmentActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

// FlutterFragmentActivity, not FlutterActivity -- local_auth's Android
// implementation shows its BiometricPrompt UI via a DialogFragment, which
// requires the hosting Activity to be a FragmentActivity.
// FlutterFragmentActivity is Flutter's own FragmentActivity-based
// alternative to plain FlutterActivity, provided specifically for plugins
// with this requirement (camera, google_sign_in, local_auth, etc.) -- not
// a local_auth-specific class, and not a change that needs a new pubspec
// dependency.
class MainActivity : FlutterFragmentActivity() {
    // Bridges NfcService (Dart) to SuaamsHceService (native) -- Dart
    // fetches the beacon token over the normal authenticated HTTP call
    // (mint_checkin_beacon) and hands it across this channel right before
    // broadcasting; the native HCE service has no HTTP/auth logic of its
    // own, it only ever holds whatever token it was last given.
    private val hceChannelName = "suaams/hce"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, hceChannelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "setBeaconToken" -> {
                        val token = call.argument<String>("token")
                        if (token.isNullOrEmpty()) {
                            result.error("INVALID_ARGUMENT", "token is required", null)
                        } else {
                            SuaamsHceService.setBeaconToken(token)
                            result.success(null)
                        }
                    }
                    "clearBeaconToken" -> {
                        SuaamsHceService.clearBeaconToken()
                        result.success(null)
                    }
                    "wasTapDetected" -> {
                        result.success(SuaamsHceService.wasTapDetected())
                    }
                    else -> result.notImplemented()
                }
            }
    }
}
