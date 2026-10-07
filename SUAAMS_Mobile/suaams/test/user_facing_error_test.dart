// Tests for userFacingError -- the boundary that decides what text a user
// sees when something fails.
//
// This is table-driven against the exact strings the app can actually throw
// or receive. It is worth pinning for three reasons:
//
//  1. The mapping decides what a user reads. "Server Error: 500" reaching a
//     login SnackBar is a defect, and nothing else would catch a regression.
//  2. Rule ORDER is load-bearing and invisible. "Failed to stop HCE: timeout"
//     matched the timeout rule first and told a user the server had been
//     slow, when no server was involved. That bug shipped to this file's
//     author, so there is an explicit regression test for it below.
//  3. The pass-through behaviour is deliberate. The backend's specific
//     messages are better copy than anything we would invent, and a future
//     "tidying" that starts rewriting them would be a regression.

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:suaams/core/network/user_facing_error.dart';

/// Silence the mapper's debugPrint chatter so a failure is readable.
void _quietLogs() {
  setUpAll(() {
    debugPrint = ((String? message, {int? wrapWidth}) {}) as DebugPrintCallback;
  });
  tearDownAll(() => debugPrint = debugPrintSynchronously);
}

void main() {
  _quietLogs();

  group('internal exceptions become human text', () {
    const cases = <String, String>{
      'Server Error: 500': 'Something went wrong on our side. Please try again.',
      'Server Error: 404': 'Something went wrong on our side. Please try again.',
      'No refresh token available':
          'Your session has ended. Please sign in again.',
      'Authentication token missing':
          'Your session has ended. Please sign in again.',
      'Data parsing error: FormatException: Unexpected character':
          "We couldn't read the server's response. Please try again.",
      'SocketException: Connection refused':
          "Can't reach the server. Check your connection and try again.",
      'Failed host lookup: suaams.onrender.com':
          "Can't reach the server. Check your connection and try again.",
      'TimeoutException after 10000ms':
          'The server took too long to respond. Please try again.',
      'Failed to mark announcements seen: 503':
          'Your announcements could not be updated. Try again shortly.',
    };

    cases.forEach((input, expected) {
      test('"$input"', () {
        expect(userFacingError(input), expected);
      });
    });
  });

  group('the Exception: prefix is stripped, not shown', () {
    test('a prefixed internal error maps identically to a bare one', () {
      expect(
        userFacingError('Exception: Server Error: 500'),
        userFacingError('Server Error: 500'),
      );
    });

    test('a prefixed server message is unprefixed', () {
      expect(
        userFacingError('Exception: Invalid password'),
        'Invalid password',
      );
    });
  });

  // The ordering bug. Kept as an explicit named case rather than folded
  // into the table above, because the failure it guards against is not
  // obvious from the strings involved.
  group('specific rules beat general ones', () {
    test('Failed to stop HCE: timeout reports the radio, not the server', () {
      final result = userFacingError('Failed to stop HCE: timeout');
      expect(result, contains('radio'));
      expect(result, isNot(contains('server took too long')));
    });

    test('a real timeout still reports the server', () {
      expect(
        userFacingError('TimeoutException after 10000ms'),
        contains('server took too long'),
      );
    });

    test('Hardware failure beats the generic platform catch', () {
      expect(
        userFacingError('Hardware failure: PlatformException(no such channel)'),
        contains('NFC'),
      );
    });
  });

  // Going offline is the single most common failure a student will hit, and
  // it produced two wrong messages before these were pinned:
  //
  //  - "It may be waking up from idle" -- Render free-tier trivia that means
  //    nothing on a device with no signal, and it matched no rule at all, so
  //    it reached the login SnackBar verbatim.
  //  - A real offline failure arrives as ClientException *wrapping*
  //    SocketException. The ClientException catch-all ran first and reported
  //    "We couldn't read the server's response" -- telling the user their
  //    server sent something malformed when their phone is simply offline.
  group('offline is reported as offline', () {
    const offlineClientException =
        'ClientException: SocketException: Connection failed '
        '(OS Error: Network is unreachable, errno 101), '
        'address = suaams.onrender.com, port = 443';

    test('a ClientException wrapping a socket failure says "no connection"',
        () {
      final result = userFacingError(offlineClientException);
      expect(result, contains("Can't reach the server"));
      expect(result, isNot(contains("couldn't read the server's response")));
    });

    test('no idle / Render trivia reaches the user', () {
      // The exact wording auth_service used to throw.
      final result = userFacingError(
        'Server is taking too long to respond. It may be waking up from '
        'idle -- please try again in a moment.',
      );
      expect(result, isNot(contains('idle')));
      expect(result, 'The server took too long to respond. Please try again.');
    });

    test('a bare ClientException message with no type prefix is handled', () {
      // Some http versions put only the message in toString().
      expect(
        userFacingError('Connection closed before full header was received'),
        contains("Can't reach the server"),
      );
    });

    test('a genuinely malformed response still reads as such', () {
      // The network rules sit above the ClientException catch-all, so this
      // guards the case that reordering could have over-corrected.
      expect(
        userFacingError('ClientException: Bad response format'),
        "We couldn't read the server's response. Please try again.",
      );
    });
  });

  group('the device lockout notice stays actionable', () {
    test('names the situation, the safety, and where to go', () {
      const raw =
          'SECURITY LOCK: Account is bound to another device. '
          'Please visit IT Administration to request a hardware unbind.';
      final result = userFacingError(raw);
      expect(result, contains('bound to another device'));
      expect(result, contains('IT Administration'));
      expect(result, isNot(contains('SECURITY LOCK')));
    });

    test('a phone already holding another account says so', () {
      final result = userFacingError(
        'DEVICE IN USE: This phone is already registered to another student '
        'account. Please visit IT Administration if this is your phone.',
      );
      expect(result, contains('another student'));
      expect(result, contains('IT Administration'));
      expect(result, isNot(contains('DEVICE IN USE')));
    });

    test('an unreadable hardware ID tells the user what to try', () {
      for (final raw in [
        "DEVICE UNVERIFIED: This phone's hardware ID could not be read. "
            'Please update the app and try again.',
        'Exception: Device identity unavailable',
      ]) {
        final result = userFacingError(raw);
        expect(result, contains("couldn't be verified"), reason: raw);
        expect(result, contains('update the app'), reason: raw);
      }
    });
  });

  group('generic backend catch-alls are suppressed', () {
    // These all name a symptom, never a cause, and carry no action. A screen
    // showing one already has a title saying the same thing, so passing it
    // through only duplicates that and displaces the actionable fallback.
    for (final raw in [
      'Failed to load dashboard',
      'Failed to post announcement',
      'Failed to start session.',
      'Could not load your courses',
      'Error loading attendance history',
    ]) {
      test('"$raw" falls back', () {
        expect(
          userFacingError(raw),
          'Check your connection and try again.',
        );
      });
    }

    test('an explicit fallback argument is honoured', () {
      expect(
        userFacingError('Failed to load dashboard', fallback: 'Try later.'),
        'Try later.',
      );
    });
  });

  group('good server copy passes through untouched', () {
    // The backend's specific messages are the best error text in the app.
    // Rewriting them would be a regression, so they are pinned here.
    for (final raw in [
      'You are already registered for this course.',
      'You are not registered for this course.',
      'Invalid password',
      'Not enrolled in this course.',
      'That session has ended',
      'New password is required',
      'This course is not open for registration this semester.',
    ]) {
      test('"$raw"', () {
        expect(userFacingError(raw), raw);
      });
    }
  });

  group('isGenericServerMessage', () {
    test('null counts as generic, so a caller always has a fallback', () {
      expect(isGenericServerMessage(null), isTrue);
    });

    test('recognises the catch-all shapes', () {
      expect(isGenericServerMessage('Failed to load dashboard'), isTrue);
      expect(isGenericServerMessage('Could not load your courses'), isTrue);
    });

    test('does not swallow specific messages', () {
      expect(isGenericServerMessage('Invalid password'), isFalse);
      expect(
        isGenericServerMessage('You are already registered for this course.'),
        isFalse,
      );
    });
  });

  group('nothing ever leaks a raw internal diagnostic', () {
    // The property that actually matters: for every input, the result must
    // not still contain the developer's own vocabulary.
    final inputs = [
      'Server Error: 503',
      'Exception: No refresh token available',
      'Data parsing error: FormatException: Unexpected character (at line 1)',
      'Hardware failure: PlatformException(no such channel, null, null)',
      'Failed to stop HCE: timeout',
      'ClientException: Connection closed before full header was received',
      'HandshakeException: Handshake error in client connection',
    ];

    for (final raw in inputs) {
      test('"$raw" contains no status code or stack vocabulary', () {
        final result = userFacingError(raw);
        expect(result, isNot(matches(RegExp(r'\b[45]\d\d\b'))));
        expect(result, isNot(contains('Exception')));
        expect(result, isNot(contains('PlatformException')));
        expect(result, isNot(contains('FormatException')));
        expect(result, isNot(contains('null')));
      });
    }
  });
}