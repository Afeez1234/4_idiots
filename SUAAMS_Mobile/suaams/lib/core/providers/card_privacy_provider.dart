import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Whether the ID card's identifying rows are currently shown.
///
/// WHAT THIS IS: a shoulder-surfing mitigation, the same one a banking app
/// applies to an account number. Someone standing behind you can otherwise
/// read your matric number and hardware UID off a propped-up phone.
///
/// WHAT THIS IS NOT: a security control, and it should not be described as
/// one. Check-in is gated on the biometric prompt (nfc_provider.dart hard-
/// fails without it) and on device binding -- an attacker cannot mark
/// attendance by photographing this screen, and hiding the digits does not
/// change that. Separately, the terminal reads the NFC chip, not the screen,
/// so masking has no effect on check-in working.
///
/// Local-only by design: there is no server round-trip, and no reason for
/// one. Nothing about whether you have your own number on screen is a fact
/// the backend needs.
class CardPrivacyNotifier extends Notifier<bool> {
  CardPrivacyNotifier() : _initial = false;

  CardPrivacyNotifier.seeded(this._initial);

  final bool _initial;

  @override
  bool build() => _initial;

  void toggle() {
    state = !state;
    // Write-through without awaiting: a failed write only means the card
    // shows the wrong state next launch, which is not worth blocking a tap
    // for. Seeded from storage at startup regardless.
    const FlutterSecureStorage().write(
      key: cardDetailsVisibleKey,
      value: state ? 'true' : 'false',
    );
  }
}

const cardDetailsVisibleKey = 'card_details_visible';

final cardPrivacyProvider =
    NotifierProvider<CardPrivacyNotifier, bool>(CardPrivacyNotifier.new);

Future<bool> readCardDetailsVisible() async {
  try {
    final value =
        await const FlutterSecureStorage().read(key: cardDetailsVisibleKey);
    // Absent means "show" only for someone who had it shown before; a fresh
    // install returns null and falls through to the provider's false, which
    // is the hidden default.
    return value == 'true';
  } catch (_) {
    return false;
  }
}