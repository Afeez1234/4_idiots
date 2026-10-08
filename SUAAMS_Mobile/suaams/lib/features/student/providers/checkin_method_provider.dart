import 'package:flutter/foundation.dart' show debugPrint;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:suaams/core/network/auth_retry.dart';
import 'package:suaams/features/student/data/nfc_service.dart';
import 'package:suaams/features/student/data/student_service.dart'
    show CheckinMethods;
import 'package:suaams/features/student/providers/nfc_provider.dart'
    show nfcAvailabilityProvider;
import 'package:suaams/features/student/providers/student_provider.dart';

/// The student's choice in Profile > System preferences > Check-in method.
enum CheckInMethodPref {
  /// NFC when this phone can tap, Bluetooth otherwise. The default.
  automatic,
  nfc,
  bluetooth,
}

/// Which channel a check-in will actually use, once the preference, this
/// phone's NFC and the server's switches have all been taken into account.
enum CheckInChannel { nfc, ble }

const _prefKey = 'checkin_method';

/// Stored on the phone with the other preferences (theme, card privacy).
/// Nothing about it is a fact the server needs.
class CheckInMethodPrefNotifier extends Notifier<CheckInMethodPref> {
  @override
  CheckInMethodPref build() {
    _load();
    return CheckInMethodPref.automatic;
  }

  Future<void> _load() async {
    try {
      final stored = await const FlutterSecureStorage().read(key: _prefKey);
      final match = CheckInMethodPref.values.where((p) => p.name == stored);
      if (match.isNotEmpty && ref.mounted) state = match.first;
    } catch (e) {
      debugPrint('[CHECKIN] could not read method preference: $e');
    }
  }

  void set(CheckInMethodPref pref) {
    state = pref;
    // Write-through without awaiting, same as card privacy: a failed write
    // only means the default comes back next launch.
    const FlutterSecureStorage().write(key: _prefKey, value: pref.name);
  }
}

final checkInMethodPrefProvider =
    NotifierProvider<CheckInMethodPrefNotifier, CheckInMethodPref>(
      CheckInMethodPrefNotifier.new,
    );

/// Which channels the server has switched on. If the call fails, Bluetooth
/// counts as off: offering a scan the server might refuse is worse than
/// falling back to NFC, which is what every phone did before BLE existed.
final checkinMethodsProvider = FutureProvider.autoDispose<CheckinMethods>((
  ref,
) async {
  try {
    return await withAuthRetry(
      ref,
      (token) => ref.read(studentServiceProvider).fetchCheckinMethods(token),
    );
  } catch (e) {
    debugPrint('[CHECKIN] could not fetch methods, assuming NFC only: $e');
    return const CheckinMethods(nfc: true, ble: false);
  }
});

/// The one rule for choosing a channel. Used by the entry points (to label
/// and enable themselves) and by the check-in itself, so they always agree.
///
/// Automatic prefers NFC whenever this phone has it, even when it's merely
/// switched off: NFC's ~4cm range is much stronger evidence of presence
/// than Bluetooth, and switching it on is one tap away. The sheet still
/// offers Bluetooth as a way out on the NFC-off screen.
CheckInChannel resolveCheckInChannel({
  required CheckInMethodPref pref,
  required NfcAvailability nfc,
  required bool serverBle,
}) {
  if (!serverBle) return CheckInChannel.nfc;
  switch (pref) {
    case CheckInMethodPref.nfc:
      return CheckInChannel.nfc;
    case CheckInMethodPref.bluetooth:
      return CheckInChannel.ble;
    case CheckInMethodPref.automatic:
      return nfc.cannotTapIn ? CheckInChannel.ble : CheckInChannel.nfc;
  }
}

/// The channel the entry points should present. While anything is still
/// loading, assumes NFC -- the pre-Bluetooth behaviour -- rather than
/// flashing a different state on every phone.
final checkInChannelProvider = Provider.autoDispose<CheckInChannel>((ref) {
  return resolveCheckInChannel(
    pref: ref.watch(checkInMethodPrefProvider),
    nfc: ref.watch(nfcAvailabilityProvider).value ?? NfcAvailability.ready,
    serverBle: ref.watch(checkinMethodsProvider).value?.ble ?? false,
  );
});
