/// Guarded avatar initials.
///
/// Every avatar in the app was written by hand as `name[0].toUpperCase()`,
/// which throws a `RangeError` on an empty string. `StudentProfile.fullName`
/// is declared non-nullable but nothing stops the API sending `""` -- the
/// model already has to think about this kind of thing (`rfidUid` is nullable
/// precisely because a student might not have been issued one yet), so a
/// blank name is a record state the client should survive rather than crash
/// on. An avatar is decoration: failing to draw one is always preferable to
/// taking the whole profile tab down with it.
///
/// The two home screens were already doing this correctly by hand
/// (`displayName.trim()` then `isNotEmpty`, with a role-specific fallback);
/// this folds that pattern into one place so the remaining three screens
/// don't each re-derive it.
library;

/// Returns the first letter of [name], uppercased, or [fallback] if [name]
/// is null/empty/whitespace.
///
/// Single letter rather than true two-letter initials: every existing avatar
/// in the app renders one letter, and switching the ID card to "AB" for
/// "Adebayo Balogun" would be a visual change to the screen students are
/// most likely to screenshot, for no functional gain.
String initialOf(String? name, {String fallback = '?'}) {
  final trimmed = name?.trim() ?? '';
  if (trimmed.isEmpty) return fallback;
  return trimmed[0].toUpperCase();
}
