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
// 8.2.2's lib/src/*.dart) rather than its published docs/examples.
//
// Was pinned to ^5.0.4, then moved to ^8.2.2. The config surface
// (TalsecConfig / AndroidConfig / IOSConfig, including the unconditional
// ConfigVerifier.verifyAndroid() base64 check on signingCertHashes) is
// unchanged between the two. ThreatCallback is not: 8.x drops onOverlay
// outright -- Talsec removed overlay detection from the threat set rather
// than renaming it, so there is no like-for-like replacement. 8.x adds
// onAutomation, onMultiInstance, onTimeSpoofing, onLocationSpoofing,
// onBootloader, onDevMode, onADBEnabled, onSystemVPN, onMalware,
// onScreenshot, onScreenRecording, onUnsecureWiFi, onObfuscationIssues,
// and killOnBypass.
//
// The threat-to-tier mapping below is a judgement call about this app's
// threat model, not something the package dictates -- if you upgrade again,
// re-read it rather than assuming the tiers carry over.
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

  /// Whether Talsec actually started and is listening for threats.
  ///
  /// Without this, there were only two states -- "a threat fired" and "no
  /// threat fired" -- and a FreeRASP integration that failed silently was
  /// indistinguishable from a clean device. That fails OPEN: no Play
  /// Services, a missing native lib, or a thrown PlatformException during
  /// start() all left _isCompromised false, and check-in proceeded as
  /// though integrity had been verified. Check-in now fails closed unless
  /// we can positively confirm the checker is running.
  bool _isArmed = false;

  /// True when the integrity checker is running and reported no blocking
  /// threat. Only meaningful once [isArmed] is true.
  bool get isArmed => _isArmed;

  /// True once a blocking threat has fired, OR when integrity checking
  /// never successfully armed. Checked by
  /// NfcCheckInNotifier.initiateCheckInProtocol() before doing anything else
  /// -- biometric auth included, since a compromised OS is exactly what
  /// could fake that auth's result.
  ///
  /// Fails closed by design: an unarmed checker is treated as
  /// untrustworthy rather than as a pass.
  bool get isCompromised =>
      _isCompromised || (_initialized && !_isArmed);

  /// Set as soon as initialize() is entered, so a checker that throws part
  /// way through still leaves us in the "tried but didn't arm" state
  /// rather than the indistinguishable "never ran" one.
  bool _initialized = false;

  /// Whether Talsec reported that its checks actually RAN to completion,
  /// as opposed to merely having a live process after start() returned.
  ///
  /// Deliberately NOT part of the isCompromised verdict. start() returning
  /// without throwing proves the native side is up; it does not prove the
  /// checks executed and reported. Gating _isArmed on this instead would
  /// be the more principled design, but the failure mode is unacceptable:
  /// if the execution-state event never arrives (Play Services absent, a
  /// native-side fault that leaves the channel silent), check-in would be
  /// permanently blocked in release builds with no way to tell "threat
  /// detected" apart from "checker never reported back" -- the exact
  /// ambiguity _isArmed was introduced to eliminate, reintroduced one
  /// level up.
  ///
  /// So it is strictly additive: better diagnostics when it fires, and no
  /// change to the verdict when it doesn't. Read it in logs to tell a
  /// genuinely clean device from a checker that never reported.
  bool _checksCompleted = false;

  /// Exposed for the same diagnostic reason as _checksCompleted. Getters
  /// can't be meaningfully widened to UI right now -- nothing consumes
  /// them, and adding surface invites someone to wire it into isCompromised.
  bool get checksCompleted => _checksCompleted;

  /// Human-readable reason, surfaced in the check-in screen's error state
  /// when isCompromised is true.
  String? get threatDescription => _threatDescription;

  Future<void> initialize() async {
    final config = TalsecConfig(
      // TODO(release): set a real watcherMail before shipping a release
      // build. Talsec's backend emails a security report here when a
      // threat fires. Deliberately not defaulted to a real address:
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
        // TODO(release): set the real release signing cert hash before
        // shipping -- this needs your REAL release keystore's certificate
        // hash, not this placeholder. Get it with:
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
        // TODO(release): set the real Apple Team ID once/if this ships to
        // a real iOS device or TestFlight -- no Team ID is configured in
        // this project yet (ios/Runner.xcodeproj has no DEVELOPMENT_TEAM
        // set).
        teamId: 'REPLACE_WITH_YOUR_APPLE_TEAM_ID',
      ),
    );

    // Only the fields this package version (8.2.2) actually defines --
    // see ThreatCallback in lib/src/callbacks/threat_callback.dart.
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
      // Took the blocking slot that onOverlay held before the 8.x upgrade.
      // Talsec dropped overlay detection from the threat set entirely, so
      // there is no rename to chase -- this is a substitution, and the
      // reasoning is that it covers a superset of what overlay threatened.
      // An overlay needed a human to be induced into tapping the check-in
      // sheet at an attacker's chosen moment; automation supplies that tap
      // directly, with no human in the loop at all. Both are tapjacking-
      // class attacks against a broadcast attendance credential, and the
      // emulator / unofficial-store checks above remain rightly
      // non-blocking while this has no innocent explanation on a device
      // about to mint one.
      onAutomation: () => _handleThreat(
        'UI automation detected (scripted input, e.g. Appium/UIAutomator)',
        blocking: true,
      ),
      // An unlocked/compromised bootloader is the same class of problem as
      // onPrivilegedAccess above: the OS's integrity is gone, so anything
      // the OS tells us -- including local_auth's own answer -- is
      // untrustworthy. Android-only in the SDK. Blocking is safe here in a
      // way it wouldn't be for onDevMode/onADBEnabled below: a bootloader
      // unlock is not part of a legitimate NFC/PN532 tap test, whereas ADB
      // and dev mode genuinely are while bench-testing that flow.
      onBootloader: () => _handleThreat(
        'Bootloader is unlocked or compromised',
        blocking: true,
      ),

      // ── Logged only: real signals, but not the biometric-bypass vector,
      // and onUnofficialStore especially must NOT block -- a side-loaded
      // capstone demo APK is, by definition, from an "unofficial store".
      // Blocking on that would break the demo itself.
      onSimulator: () => _handleThreat('Running on an emulator/simulator'),
      onUnofficialStore: () =>
          _handleThreat('App was not installed from the configured store'),
      onPasscode: () => _handleThreat('No device passcode/screen lock set'),
      onDeviceID: () => _handleThreat('App was reinstalled (iOS only)'),
      onDeviceBinding: () => _handleThreat('Device binding check failed'),
      // Ties to the relay-attack defence in CLAUDE.md, where the 3-second
      // acceptance window is load-bearing. Logged rather than blocking, and
      // the distinction matters: the server validates exp_unix against its
      // OWN clock, so a device with a manipulated clock still cannot forge
      // a live token. What it CAN do is make this app's local expiry UI lie
      // about how long the broadcast window is open -- which is a confusing
      // failure mode to debug, not an authentication bypass.
      onTimeSpoofing: () =>
          _handleThreat('Device clock appears to have been manipulated'),
      onSecureHardwareNotAvailable: () =>
          _handleThreat('Secure hardware-backed keystore unavailable'),
    );

    Talsec.instance.attachListener(callback);

    // Separate from the threat listener: this reports that the checks RAN
    // to completion, as opposed to a threat firing. See _checksCompleted --
    // it deliberately does not feed the isCompromised verdict, only the
    // diagnostics. Attached before start() so an event that lands during
    // startup isn't dropped.
    Talsec.instance.attachExecutionStateListener(
      RaspExecutionStateCallback(
        onAllChecksFinished: () {
          _checksCompleted = true;
          debugPrint(
            '[SecurityService] All integrity checks finished '
            '(armed=$_isArmed, compromised=$_isCompromised)',
          );
        },
      ),
    );

    // Set before start(), not after: if start() throws, we still want
    // initialize() to have marked us as "tried" so isCompromised reports
    // the failure-closed state rather than looking un-started.
    _initialized = true;
    await Talsec.instance.start(config);
    // Only now, with the checker actually running, is "no threat yet" a
    // meaningful pass rather than an absence of evidence.
    _isArmed = true;
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
