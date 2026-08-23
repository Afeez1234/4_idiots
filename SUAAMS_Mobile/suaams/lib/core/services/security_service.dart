// Runtime Application Self-Protection (RASP) via freeRASP/Talsec -- closes
// the gap CLAUDE.md's threat model calls out explicitly: "Rooted/jailbroken
// devices: on startup, run integrity-checking... and refuse to generate
// transaction payloads if the OS is compromised -- closes the
// runtime-injection bypass of the biometric check." local_auth's biometric
// gate is an OS-level API call; on a rooted device with a hooking framework
// attached (Frida/Xposed), that call can be intercepted and forced to report
// success regardless of the actual fingerprint/face result. RASP is what
// verifies the device itself hasn't been tampered with to fake that
// verification -- it's a separate, lower-level check than local_auth's own.
//
// API verified directly against the installed package source (freerasp
// 5.0.4's lib/src/*.dart) rather than its published docs/examples, which
// describe a materially different (newer, 8.x-line) API surface --
// killOnBypass and several ThreatCallback fields referenced there
// (onMalware, onSystemVPN, onDevMode, onADBEnabled, etc.) don't exist in
// 5.0.4 at all. Pinned to ^5.0.4 in pubspec.yaml; a much newer major (8.x)
// is available on pub.dev with a richer callback set, if this ever gets
// revisited.
//
// Kept as a plain singleton (not a Riverpod provider), same reasoning as
// NotificationService: NfcCheckInNotifier just needs a synchronous yes/no
// check at the top of initiateCheckInProtocol(), not a reactive rebuild.
import 'package:flutter/foundation.dart';
import 'package:freerasp/freerasp.dart';

class SecurityService {
  SecurityService._();
  static final SecurityService instance = SecurityService._();

  bool _isCompromised = false;
  String? _threatDescription;

  /// True once a blocking threat has fired. Checked by
  /// NfcCheckInNotifier.initiateCheckInProtocol() before doing anything else
  /// -- biometric auth included, since a compromised OS is exactly what
  /// could fake that auth's result.
  bool get isCompromised => _isCompromised;

  /// Human-readable reason, surfaced in the check-in screen's error state
  /// when isCompromised is true.
  String? get threatDescription => _threatDescription;

  Future<void> initialize() async {
    final config = TalsecConfig(
      // Talsec's backend emails a security report here when a threat
      // fires -- fill in an address you actually monitor before shipping a
      // release build. Deliberately not defaulted to a real address here:
      // this is the one field that leaves the device (Talsec's service
      // receives it), so it shouldn't be filled in silently.
      watcherMail: 'REPLACE_WITH_AN_EMAIL_YOU_MONITOR@example.com',

      // isProd gates enforcement below (see _handleThreat) -- debug/local
      // runs always log detected threats but never lock you out, since a
      // debug-signed build will never match the release cert hash below.
      isProd: kReleaseMode,

      androidConfig: AndroidConfig(
        // Matches android/app/build.gradle.kts's applicationId.
        packageName: 'com.suaams.mobile',
        // REPLACE before a release build ships -- this needs your REAL
        // release keystore's certificate hash, not this placeholder. Get
        // it with:
        //   keytool -list -v -keystore <your-release>.jks -alias <your-alias>
        // then base64-encode the SHA-256 hex digest it prints (Talsec's
        // docs show the exact conversion). Left as a placeholder because
        // only you hold that keystore -- with it in place, onAppIntegrity
        // fires on every real release build until corrected, but that only
        // matters once isProd is actually true (kReleaseMode).
        //
        // IMPORTANT: this MUST decode as valid base64 to exactly 32 bytes --
        // AndroidConfig's constructor calls ConfigVerifier.verifyAndroid()
        // unconditionally (not gated by isProd), which throws
        // ConfigurationException on anything else, crashing the app on
        // every launch. 32 zero-bytes, base64-encoded, satisfies the format
        // check while still being obviously non-functional as a real hash.
        signingCertHashes: ['AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='],
      ),
      iosConfig: IOSConfig(
        bundleIds: ['com.suaams.mobile'],
        // No Apple Developer Team ID configured in this project yet
        // (ios/Runner.xcodeproj has no DEVELOPMENT_TEAM set) -- fill in
        // once/if this ships to a real iOS device or TestFlight.
        teamId: 'REPLACE_WITH_YOUR_APPLE_TEAM_ID',
      ),
    );

    // Only the fields this package version (5.0.4) actually defines --
    // see ThreatCallback in lib/src/threat_callback.dart.
    final callback = ThreatCallback(
      // ── Blocking: these directly match CLAUDE.md's stated threat ──────
      onPrivilegedAccess: () => _handleThreat(
        'Device is rooted/jailbroken',
        blocking: true,
      ),
      onHooks: () => _handleThreat(
        'Hooking framework detected (Frida/Xposed-style runtime injection)',
        blocking: true,
      ),
      onAppIntegrity: () => _handleThreat(
        'App signature does not match -- binary has been repackaged/tampered with',
        blocking: true,
      ),
      onDebug: () => _handleThreat(
        'Debugger attached to a running process',
        blocking: true,
      ),

      // ── Logged only: real signals, but not the biometric-bypass vector,
      // and onUnofficialStore especially must NOT block -- a side-loaded
      // capstone demo APK is, by definition, from an "unofficial store".
      // Blocking on that would break the demo itself.
      onSimulator: () => _handleThreat('Running on an emulator/simulator'),
      onUnofficialStore: () =>
          _handleThreat('App was not installed from the configured store'),
      onOverlay: () =>
          _handleThreat('Screen overlay detected (Android only)'),
      onPasscode: () => _handleThreat('No device passcode/screen lock set'),
      onDeviceID: () => _handleThreat('App was reinstalled (iOS only)'),
      onDeviceBinding: () => _handleThreat('Device binding check failed'),
      onSecureHardwareNotAvailable: () =>
          _handleThreat('Secure hardware-backed keystore unavailable'),
    );

    Talsec.instance.attachListener(callback);
    await Talsec.instance.start(config);
  }

  void _handleThreat(String description, {bool blocking = false}) {
    debugPrint('[SecurityService] Threat detected: $description');

    // Only enforce in release builds -- see isProd's comment above. Debug
    // runs (including on an emulator, or a debug-signed APK that will
    // never match the placeholder release cert hash) log every threat but
    // never flip isCompromised, so local development isn't blocked by
    // config that can only be finalized right before a real release build.
    if (blocking && kReleaseMode) {
      _isCompromised = true;
      _threatDescription = description;
    }
  }
}
