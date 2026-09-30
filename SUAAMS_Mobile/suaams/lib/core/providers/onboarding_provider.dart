import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Whether this install has already been through the first-run walkthrough.
///
/// Seeded from disk in `main()` BEFORE `runApp`, and passed in as a
/// constructor argument, because the router's `redirect` is synchronous --
/// it cannot await a storage read. Loading it lazily inside the provider
/// would mean the redirect sees a default of "not seen" on every launch and
/// bounces a returning user back into onboarding every time the app starts.
class OnboardingNotifier extends Notifier<bool> {
  /// Default for tests and for any provider instance created without the
  /// startup seed (in which case onboarding will be shown).
  OnboardingNotifier() : _initialValue = false;

  /// The real constructor in production: `main()` awaits the storage read
  /// and installs this through `ProviderScope(overrides: [...])`, because
  /// NotifierProvider itself only accepts a zero-argument builder.
  OnboardingNotifier.seeded(this._initialValue);

  final bool _initialValue;

  @override
  bool build() => _initialValue;

  Future<void> markSeen() async {
    // Set state first so a fast double-tap on "Get started" can't route the
    // user back to onboarding before the write lands.
    state = true;
    const FlutterSecureStorage().write(key: seenOnboardingKey, value: 'true');
  }
}

const seenOnboardingKey = 'seen_onboarding';

final onboardingProvider =
    NotifierProvider<OnboardingNotifier, bool>(OnboardingNotifier.new);

/// Read the flag once, at startup. Kept as a free function so `main()` can
/// call it before a ProviderScope exists.
Future<bool> readOnboardingFlag() async {
  try {
    final value = await const FlutterSecureStorage().read(key: seenOnboardingKey);
    return value == 'true';
  } catch (_) {
    // A storage failure must not lock anyone out of the app. Showing
    // onboarding again is a much smaller problem than being unable to log
    // in, so default to "not seen" and let the flow be re-walked.
    return false;
  }
}
