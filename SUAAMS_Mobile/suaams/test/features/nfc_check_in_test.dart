// Tests for the NFC check-in flow (NfcCheckInNotifier.initiateCheckInProtocol).
//
// Two bugs in this flow were fixed by hand and had nothing to catch them
// coming back:
//
//  1. Closing the sheet while the fingerprint prompt was up disposed the
//     provider, but the flow carried on: it minted a beacon and pushed it
//     into the native HCE service with no wipe scheduled, leaving it
//     readable. Two things stop it today: the `ref.mounted` check after
//     authenticate(), and the next step (the mint, via withAuthRetry)
//     needing `ref`, which throws once the provider is gone. This test pins
//     the outcome -- nothing broadcast -- not either one of them, so it
//     still catches a refactor that removes both (e.g. hoisting the mint
//     off `ref` the way _nfcService was hoisted). Checked: removing only
//     the mounted check leaves it passing.
//  2. Two entry points (home card, ID card) could start the flow together,
//     running two prompts and two mints; the second overwrote the first in
//     native memory and orphaned it. The re-entrancy latch stops that.
//
// What's real vs faked: the notifier is the real code. The NFC service and
// the OS fingerprint prompt are faked, so a test controls exactly when the
// prompt answers. SecurityService is the real singleton; it hasn't been
// initialised in a test, so it reports the phone as not compromised.

import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:local_auth/local_auth.dart';
import 'package:suaams/features/student/data/ble_scan_service.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
import 'package:suaams/features/student/providers/checkin_method_provider.dart';
import 'package:suaams/features/student/providers/nfc_provider.dart';

/// Records what reached the native HCE service. Extends Fake, so any call a
/// test didn't plan for throws instead of passing silently.
class _FakeNfcService extends Fake implements NfcService {
  final List<String> broadcast = [];
  int stops = 0;

  @override
  Future<NfcAvailability> getAvailability() async => NfcAvailability.ready;

  @override
  Future<void> startHceEmulation(String payload, {int? ttlSeconds}) async {
    broadcast.add(payload);
  }

  @override
  Future<void> stopHceEmulation() async {
    stops++;
  }
}

class _FakeBleScanService extends Fake implements BleScanService {}

/// The OS prompt, answered when the test completes [answer]. authenticate()
/// is caught in noSuchMethod rather than overridden, so this doesn't break
/// when local_auth changes that method's optional parameters.
class _FakeLocalAuth implements LocalAuthentication {
  final answer = Completer<bool>();
  int prompts = 0;

  @override
  Future<bool> get canCheckBiometrics async => true;

  @override
  Future<bool> isDeviceSupported() async => true;

  @override
  dynamic noSuchMethod(Invocation invocation) {
    if (invocation.memberName == #authenticate) {
      prompts++;
      return answer.future;
    }
    return super.noSuchMethod(invocation);
  }
}

void main() {
  late _FakeNfcService nfc;
  late _FakeLocalAuth auth;
  late ProviderContainer container;

  setUp(() {
    nfc = _FakeNfcService();
    auth = _FakeLocalAuth();
    container = ProviderContainer(
      overrides: [
        nfcServiceProvider.overrideWithValue(nfc),
        bleScanServiceProvider.overrideWithValue(_FakeBleScanService()),
        localAuthProvider.overrideWithValue(auth),
      ],
    );
  });

  tearDown(() => container.dispose());

  /// Starts a check-in and lets it run up to the open fingerprint prompt.
  // Returned in a record: an async function returning the bare Future
  // would wait for it, and the run only ends once the prompt is answered.
  Future<({Future<void> run})> startUpToPrompt() async {
    // Keep the autoDispose provider alive, as the open sheet does.
    container.listen(nfcCheckInProvider, (_, _) {});
    final run = container
        .read(nfcCheckInProvider.notifier)
        .initiateCheckInProtocol(channel: CheckInChannel.nfc);
    for (var i = 0; i < 20 && auth.prompts == 0; i++) {
      await Future<void>.delayed(Duration.zero);
    }
    expect(auth.prompts, 1, reason: 'flow should be waiting on the prompt');
    return (run: run);
  }

  test('closing the sheet during the fingerprint prompt broadcasts nothing',
      () async {
    final (:run) = await startUpToPrompt();

    container.dispose(); // the sheet is swiped away; the provider goes
    auth.answer.complete(true); // ...and then the fingerprint succeeds
    await run;

    expect(nfc.broadcast, isEmpty);
    expect(nfc.stops, greaterThanOrEqualTo(1)); // onDispose still wipes
  });

  test('a second start while one is running is ignored', () async {
    final (run: first) = await startUpToPrompt();

    await container
        .read(nfcCheckInProvider.notifier)
        .initiateCheckInProtocol(channel: CheckInChannel.nfc);
    expect(auth.prompts, 1); // no second prompt, no second mint
    expect(
      container.read(nfcCheckInProvider).status,
      NfcCheckInStatus.authenticating,
    );

    auth.answer.complete(false); // let the first run finish (refused)
    await first;
    expect(container.read(nfcCheckInProvider).status, NfcCheckInStatus.error);
    expect(nfc.broadcast, isEmpty);
  });
}
