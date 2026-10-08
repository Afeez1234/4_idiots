package com.suaams.mobile

import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.nfc.NfcAdapter
import android.provider.Settings
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
                            // Dart passes the server's own expires_in (in
                            // seconds) so the native deadline matches the
                            // window Flask will actually accept, rather than
                            // a locally-guessed one that could disagree.
                            val ttlSeconds = call.argument<Int>("ttlSeconds")
                            val ttlMillis = (ttlSeconds?.toLong()
                                ?: (SuaamsHceService.DEFAULT_TTL_MILLIS / 1000L)) * 1000L
                            SuaamsHceService.setBeaconToken(token, ttlMillis)
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
                    // Can this phone tap in at all, right now? Checked before
                    // the fingerprint prompt so a phone that can't broadcast
                    // never gets as far as minting a beacon. The manifest
                    // declares NFC as optional, so the app installs on phones
                    // without it -- this is where that gets caught.
                    "getNfcStatus" -> {
                        result.success(nfcStatus())
                    }
                    // Opens the system NFC toggle. Not every OEM build has
                    // the dedicated screen, so fall back to the general
                    // wireless settings rather than doing nothing.
                    "openNfcSettings" -> {
                        try {
                            startActivity(Intent(Settings.ACTION_NFC_SETTINGS))
                        } catch (e: ActivityNotFoundException) {
                            startActivity(Intent(Settings.ACTION_WIRELESS_SETTINGS))
                        }
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    // One of "unsupported" (no NFC chip), "noHce" (NFC, but can't act as a
    // card -- some phones ship like this), "disabled" (switched off) or
    // "ready". Order matters: a phone without HCE can't tap in even with
    // NFC switched on, so "turn on NFC" would be the wrong advice.
    private fun nfcStatus(): String {
        val adapter = NfcAdapter.getDefaultAdapter(this) ?: return "unsupported"
        if (!packageManager.hasSystemFeature(PackageManager.FEATURE_NFC_HOST_CARD_EMULATION)) {
            return "noHce"
        }
        return if (adapter.isEnabled) "ready" else "disabled"
    }
}
