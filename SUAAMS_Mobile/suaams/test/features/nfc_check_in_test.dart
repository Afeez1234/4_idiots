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
import 'package:suaams/features/auth/models/auth_user.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/student/data/ble_scan_service.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
import 'package:suaams/features/student/data/student_service.dart';
import 'package:suaams/features/student/providers/checkin_method_provider.dart';
import 'package:suaams/features/student/providers/nfc_provider.dart';
import 'package:suaams/features/student/providers/student_provider.dart';

/// Records what reached the native HCE service. Extends Fake, so any call a
/// test didn't plan for throws instead of passing silently.
class _FakeNfcService extends Fake implements NfcService {
  final List<String> broadcast = [];
  int stops = 0;

  /// What SuaamsHceService.wasTapDetected() reports: has a reader engaged
  /// the beacon? A test flips this to simulate the tap.
  bool tapped = false;

  @override
  Future<bool> wasTapDetected() async => tapped;

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

/// The server, as the check-in flow sees it: one mint, then status polls.
/// [statusPolls] is what the polling test counts.
class _FakeStudentService extends Fake implements StudentService {
  int statusPolls = 0;

  @override
  Future<BeaconMintResult> mintCheckinBeacon(String token) async =>
      BeaconMintResult(beaconToken: 'B' * 32, expiresIn: 10);

  @override
  Future<CheckinStatusResult> checkCheckinStatus(String token) async {
    statusPolls++;
    return CheckinStatusResult(checkedIn: true, courseCode: 'MCT 401');
  }
}

/// A signed-in student, so withAuthRetry has a token to hand the service.
class _SignedInAuth extends AuthNotifier {
  @override
  AuthState build() => AuthState(
    user: AuthUser(
      id: 23,
      role: 'student',
      username: 'MCT/2022/014',
      token: 'access-token',
    ),
  );
}

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
  late _FakeStudentService server;
  late ProviderContainer container;

  setUp(() {
    nfc = _FakeNfcService();
    auth = _FakeLocalAuth();
    server = _FakeStudentService();
    container = ProviderContainer(
      overrides: [
        nfcServiceProvider.overrideWithValue(nfc),
        bleScanServiceProvider.overrideWithValue(_FakeBleScanService()),
        localAuthProvider.overrideWithValue(auth),
        studentServiceProvider.overrideWithValue(server),
        authProvider.overrideWith(_SignedInAuth.new),
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

  test(
    'closing the sheet during the fingerprint prompt broadcasts nothing',
    () async {
      final (:run) = await startUpToPrompt();

      container.dispose(); // the sheet is swiped away; the provider goes
      auth.answer.complete(true); // ...and then the fingerprint succeeds
      await run;

      expect(nfc.broadcast, isEmpty);
      expect(nfc.stops, greaterThanOrEqualTo(1)); // onDispose still wipes
    },
  );

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

  // Every student in a hall used to poll /checkin/status once a second from
  // the moment the beacon went live, though nothing can land before the
  // tap. Those polls queue for the same 4-connection DB pool as the
  // terminal's /checkin POST. This pins "no server polls until a reader
  // has touched the phone, then polling finds the result". Real timers
  // (the poll tick is 1 s), so it takes about 4 s.
  test('polls the server only after a reader has touched the phone', () async {
    final (:run) = await startUpToPrompt();
    auth.answer.complete(true);
    await run;
    expect(nfc.broadcast, hasLength(1));
    expect(
      container.read(nfcCheckInProvider).status,
      NfcCheckInStatus.broadcasting,
    );

    // Two poll ticks with no reader: the phone is asked, the server isn't.
    await Future<void>.delayed(const Duration(milliseconds: 2300));
    expect(server.statusPolls, 0);

    nfc.tapped = true; // the student taps the reader
    await Future<void>.delayed(const Duration(milliseconds: 1500));
    expect(server.statusPolls, greaterThanOrEqualTo(1));
    expect(container.read(nfcCheckInProvider).status, NfcCheckInStatus.success);
  });
}
