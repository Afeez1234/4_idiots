import 'package:flutter/foundation.dart';

/// Translates an internal exception into something worth showing a user.
///
/// Every provider does `errorMessage: e.toString().replaceAll('Exception: ', '')`,
/// and whatever was thrown becomes the text on screen. That works fine for
/// the backend's *specific* messages -- the device-lockout notice, "You are
/// already registered for this course" -- which are written for humans and
/// should pass through untouched. It is actively wrong for the internal
/// ones, all of which were reaching the UI verbatim:
///
///     Server Error: 500
///     No refresh token available
///     Data parsing error: FormatException: Unexpected character
///     Hardware failure: PlatformException(no such channel)
///
/// Those are developer diagnostics. A user who hits a 500 during login was
/// being shown "Server Error: 500".
///
/// This runs at the boundary rather than at each of the 21 call sites, so a
/// newly thrown internal string is handled by adding one line here rather
/// than by auditing every provider again. The original is preserved to the
/// debug console, where it is genuinely useful.
String userFacingError(Object error, {String? fallback}) {
  final raw = _clean(error.toString());

  // Ordered most-specific first: the first match wins, so a specific rule
  // placed above a general one always takes precedence.
  // Ordered most-specific FIRST: the first match wins, so a rule naming one
  // specific message must be tested before any rule matching a general
  // failure mode. "Failed to stop HCE: timeout" is the case that forced this
  // ordering -- it matched the timeout rule first and told the user the
  // server had been slow, when no server was involved at all.
  final rules = <(RegExp, String)>[
    // --- one specific message -------------------------------------------
    (
      RegExp(r'Failed to mark announcements seen', caseSensitive: false),
      'Your announcements could not be updated. Try again shortly.',
    ),
    (
      RegExp(r'Failed to stop HCE', caseSensitive: false),
      'The radio could not be stopped cleanly. Close and reopen the app.',
    ),
    // --- auth / session -------------------------------------------------
    (
      RegExp(r'SECURITY LOCK', caseSensitive: false),
      'Your account is bound to another device. Visit IT Administration to '
          'request a hardware unbind.',
    ),
    (
      RegExp(r'No refresh token available|Authentication token missing'),
      'Your session has ended. Please sign in again.',
    ),
    (
      RegExp(r'token.*expired|expired.*token|Session has been revoked', caseSensitive: false),
      'Your session has ended. Please sign in again.',
    ),
    // --- backend transport ----------------------------------------------
    (
      RegExp(r'^Server Error: \d+'),
      'Something went wrong on our side. Please try again.',
    ),
    (
      RegExp(r'Data parsing error|FormatException', caseSensitive: false),
      "We couldn't read the server's response. Please try again.",
    ),
    (
      RegExp(r'SocketException|Connection refused|Failed host lookup|Network is unreachable', caseSensitive: false),
      "Can't reach the server. Check your connection and try again.",
    ),
    (
      RegExp(r'Connection closed before full header|Connection terminated', caseSensitive: false),
      "Can't reach the server. Check your connection and try again.",
    ),
    (
      RegExp(r'ClientException|Bad response format|HandshakeException', caseSensitive: false),
      "We couldn't read the server's response. Please try again.",
    ),
    // Two shapes seen in the wild that the broader rules above miss:
    // a bare ClientException message with no type prefix in
    // e.toString(), and the auth service's own timeout wording.
    (
      RegExp(r'Server (?:is taking|took) too long', caseSensitive: false),
      'The server took too long to respond. Please try again.',
    ),
    (
      RegExp(r'Hardware failure|PlatformException', caseSensitive: false),
      "This device couldn't complete the request. Check that NFC and "
          'biometrics are enabled, then try again.',
    ),
    // --- general failure modes, tested last -----------------------------
    (
      RegExp(r'TimeoutException|timeout', caseSensitive: false),
      'The server took too long to respond. Please try again.',
    ),
  ];

  for (final (pattern, replacement) in rules) {
    if (pattern.hasMatch(raw)) {
      debugPrint('[userFacingError] matched ${pattern.pattern}');
      debugPrint('[userFacingError] raw: $raw');
      return replacement;
    }
  }

  // No rule matched. If the server sent something specific, it is almost
  // certainly better copy than anything we would invent -- the device
  // lockout notice and the course-conflict messages all arrive this way, and
  // they are the best error text in the app.
  //
  // The one class we refuse to pass through is the backend's generic
  // catch-alls ("Failed to load dashboard", "Failed to post announcement").
  // They name a symptom, never a cause, and no action. A screen showing one
  // already has a title saying the same thing, so passing it through only
  // duplicates that and displaces the actionable fallback underneath.
  if (_isGenericServerMessage(raw)) {
    debugPrint('[userFacingError] generic server message suppressed: $raw');
    return fallback ?? 'Check your connection and try again.';
  }

  return raw;
}

/// True for the backend's catch-all failures, which all share a
/// "Failed to ..." shape and carry no information a screen's own title
/// doesn't already convey.
bool _isGenericServerMessage(String message) {
  return RegExp(
    r'^(Failed to |Error loading |Could not load )',
    caseSensitive: false,
  ).hasMatch(message);
}

/// Whether a server message is one of the generic catch-alls. Exposed so a
/// screen can decide between its own fallback and the server's text.
bool isGenericServerMessage(String? message) {
  if (message == null) return true;
  return _isGenericServerMessage(_clean(message));
}

/// Strip the `Exception: ` prefix that `Exception.toString()` adds, which
/// providers were removing by hand at every call site.
String _clean(String raw) {
  var out = raw.trim();
  if (out.startsWith('Exception: ')) out = out.substring(11);
  if (out.startsWith('Exception:')) out = out.substring(10).trim();
  return out;
}