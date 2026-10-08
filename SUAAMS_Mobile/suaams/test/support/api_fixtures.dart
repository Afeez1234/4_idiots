// Loader for the recorded API response bodies in test/fixtures/api/.
//
// Each fixture is the FULL body a Flask endpoint returns -- envelope and all
// ({"success": true, "data": {...}}) -- not just the slice a model parses.
// The tests then unwrap it with the same key the real service uses
// (responseData['data'], ['today_protocol'], ['week'], ...), so an envelope
// change on the backend breaks a test here too, not only a field rename.
//
// Fixtures were transcribed from the jsonify(...) calls in SUAAMS/api/*.py,
// including the Python-specific value shapes a hand-written guess tends to
// miss: round(0, 1) serialising as the INT 0 rather than 0.0, str(time)
// giving "09:00:00" while strftime gives "09:00", isoformat() carrying
// microseconds, and keys (ad_hoc) that only some rows include. When a
// backend response shape changes, update the matching fixture in the same
// commit -- a fixture that no longer matches Flask is worse than none.
//
// Decoding goes through jsonDecode exactly like the services do, so nested
// objects arrive as Map<String, dynamic> and arrays as List<dynamic> -- the
// same runtime types the `as` casts in each fromJson see in production.

import 'dart:convert';
import 'dart:io';

/// Full decoded response body of test/fixtures/api/[name].json.
///
/// `flutter test` runs with the package root as the working directory,
/// which is what makes this relative path resolve.
Map<String, dynamic> loadApiFixture(String name) {
  final file = File('test/fixtures/api/$name.json');
  return jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
}

/// The `data` object of a {"success": true, "data": {...}} envelope -- the
/// shape most endpoints use and what their services pass to fromJson.
Map<String, dynamic> loadApiData(String name) =>
    loadApiFixture(name)['data'] as Map<String, dynamic>;
