import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Which roles have already been shown the first-run walkthrough.
///
/// This is a SET, not a bool, and that is the second fix here. It began as a
/// single `seen_onboarding` boolean, which meant that on a phone shared
/// between a student and a lecturer account — a departmental handset, a
/// demo device — whoever signed in first marked onboarding seen and the
/// other role never got theirs. The two walkthroughs describe different
/// tabs, a different core loop and a different security model, so "seen"
/// has to be tracked per walkthrough, not per device.
///
/// A set rather than a map of bools because "seen" is monotonic: once a
/// role has walked through, it has, and there is no state in which a role
/// is explicitly un-seen.
class OnboardingNotifier extends Notifier<Set<String>> {
  /// Default for tests, and for any instance created without the startup
  /// seed (in which case onboarding will be shown).
  OnboardingNotifier() : _initialValue = const <String>{};

  /// The real constructor in production: `main()` reads the whole keyspace
  /// before `runApp` and installs this through `ProviderScope(overrides:)`,
  /// because NotifierProvider only accepts a zero-argument builder.
  OnboardingNotifier.seeded(this._initialValue);

  final Set<String> _initialValue;

  @override
  Set<String> build() => _initialValue;

  bool hasSeen(String role) => state.contains(role);

  Future<void> markSeen(String role) async {
    if (state.contains(role)) return;
    // Set state first so a fast double-tap on "Get started" can't route the
    // user back into onboarding before the write lands.
    state = {...state, role};
    await const FlutterSecureStorage()
        .write(key: onboardingKeyFor(role), value: 'true');
  }
}

const seenOnboardingPrefix = 'seen_onboarding';

/// Storage key for one role's walkthrough.
String onboardingKeyFor(String role) => '${seenOnboardingPrefix}_$role';

final onboardingProvider =
    NotifierProvider<OnboardingNotifier, Set<String>>(OnboardingNotifier.new);

/// Read every role's flag once, at startup. Kept as a free function so
/// `main()` can call it before a ProviderScope exists, and it enumerates the
/// keyspace rather than reading one role -- the signed-in role isn't known
/// this early, and the redirect that consumes this has to be synchronous.
Future<Set<String>> readSeenOnboardingRoles() async {
  try {
    final all = await const FlutterSecureStorage().readAll();
    return {
      for (final entry in all.entries)
        if (entry.value == 'true' &&
            entry.key.startsWith('${seenOnboardingPrefix}_'))
          entry.key.substring(seenOnboardingPrefix.length + 1),
    };
  } catch (_) {
    // A storage failure must not lock anyone out of the app. Showing
    // onboarding again is a much smaller problem than being unable to log
    // in, so default to "not seen" and let the flow be re-walked.
    return <String>{};
  }
}