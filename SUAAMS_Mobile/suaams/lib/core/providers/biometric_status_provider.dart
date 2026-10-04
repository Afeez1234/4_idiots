import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:local_auth/local_auth.dart';

/// Whether this device can actually satisfy the app's check-in requirement.
///
/// The Profile screen surfaces this because until now nothing in the app
/// reported it. `nfc_provider.dart` is the only place that checks, and when
/// the answer is no it throws "Hardware security mismatch: Biometrics are
/// disabled or unsupported." with no fallback -- so a student who had no
/// fingerprint enrolled discovered it by tapping the check-in card in a
/// lecture hall, and got a hard error with no indication of what to fix.
///
/// This does not weaken or replace that check. The check-in path still
/// calls the platform itself, because a status read at profile-open time
/// says nothing about whether the sensor still works when the student
/// actually taps. This exists only to tell them early.
enum BiometricStatus {
  /// Hardware present and at least one biometric enrolled -- tapping the
  /// check-in card will show a fingerprint/face prompt.
  enrolled,

  /// The device can authenticate, but nothing is enrolled. `authenticate()`
  /// falls back to the device passcode, so check-in still works -- but
  /// there will be no fingerprint prompt, which surprises people who expect
  /// one.
  passcodeOnly,

  /// No biometric hardware, or the platform reports it unsupported. Check-in
  /// WILL fail with "Hardware security mismatch" until this is resolved.
  unavailable,

  /// The platform call failed, or the check hasn't resolved yet.
  unknown,
}

final biometricStatusProvider = FutureProvider<BiometricStatus>((ref) async {
  // Same construction as nfc_provider.dart's field initializer -- the
  // class is LocalAuthentication, and it needs nothing from BuildContext.
  final auth = LocalAuthentication();

  try {
    final canCheck = await auth.canCheckBiometrics;
    final isSupported = await auth.isDeviceSupported();

    // These are the exact two conditions nfc_provider throws on, so
    // mirroring them means the status can never disagree with the behaviour.
    if (!canCheck || !isSupported) return BiometricStatus.unavailable;

    final enrolled = await auth.getAvailableBiometrics();
    return enrolled.isEmpty
        ? BiometricStatus.passcodeOnly
        : BiometricStatus.enrolled;
  } catch (_) {
    // A platform throw here must not take the profile screen down with it.
    // Reporting "unknown" renders as a neutral row rather than a false
    // alarm, and the real check still happens at check-in.
    return BiometricStatus.unknown;
  }
});