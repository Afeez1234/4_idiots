// Every API call goes through here, imported in place of package:http:
//
//     import 'package:suaams/core/network/api_client.dart' as http;
//
// so the 30-odd `http.get(...)` / `http.post(...)` call sites in the three
// services stay exactly as they were. It does two things on every request:
//
// 1. Sends this build's number as X-App-Build (the part after the + in
//    pubspec's `version:`), read once in main() by loadAppBuild().
// 2. Catches 426 "UPDATE REQUIRED" -- the server's answer when this build
//    is older than MIN_APP_BUILD (see SUAAMS/app_version.py) -- before the
//    caller sees the response. It flips [updateRequired], which the router
//    watches and answers by sending every route to /update-required, and
//    throws [UpdateRequired] so the caller's own error path runs instead of
//    trying to parse a body it doesn't expect.
//
// Why here and not in each service: the gate exists because an old build
// fails silently when the wire format changes. One check that every
// request passes through can't be forgotten by the next endpoint added.
//
// Throwing (rather than returning the 426) also matters for sign-in state:
// AuthService.refreshAccessToken() treats any non-200 as AuthRejected and
// wipes the stored session. An exception lands in AuthNotifier's
// "unreachable" branch instead, so the student is still signed in once
// they've installed the update.

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:package_info_plus/package_info_plus.dart';

export 'package:http/http.dart' show Response, ClientException;

const _buildHeader = 'X-App-Build';

String? _appBuild;

/// Reads this build's number for the X-App-Build header. Called once in
/// main() before runApp. If it fails, requests go without the header; with
/// MIN_APP_BUILD set the server then asks for an update, which is the
/// safe direction to be wrong in.
Future<void> loadAppBuild() async {
  try {
    final info = await PackageInfo.fromPlatform();
    _appBuild = info.buildNumber;
  } catch (e) {
    debugPrint('[api] could not read app build number: $e');
  }
}

/// True once the server has said this build is too old. Never goes back to
/// false: the fix is installing a new build, which restarts the app.
final updateRequired = ValueNotifier<bool>(false);

/// The server's instructions for getting the new build (APP_UPDATE_MESSAGE),
/// or null when it didn't send any.
String? updateMessage;

class UpdateRequired implements Exception {
  const UpdateRequired();

  // Matched by userFacingError, like the backend's other all-caps codes.
  @override
  String toString() => 'UPDATE REQUIRED';
}

class _VersionedClient extends http.BaseClient {
  final http.Client _inner = http.Client();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final build = _appBuild;
    if (build != null) request.headers[_buildHeader] = build;

    final response = await _inner.send(request);
    if (response.statusCode != 426) return response;

    try {
      final body = jsonDecode(await response.stream.bytesToString());
      final message = body is Map ? body['message'] : null;
      if (message is String && message.isNotEmpty) updateMessage = message;
    } catch (_) {
      // No readable body: the screen's own wording is enough.
    }
    updateRequired.value = true;
    throw const UpdateRequired();
  }
}

final _client = _VersionedClient();

Future<http.Response> get(Uri url, {Map<String, String>? headers}) =>
    _client.get(url, headers: headers);

Future<http.Response> post(
  Uri url, {
  Map<String, String>? headers,
  Object? body,
  Encoding? encoding,
}) => _client.post(url, headers: headers, body: body, encoding: encoding);

Future<http.Response> patch(
  Uri url, {
  Map<String, String>? headers,
  Object? body,
  Encoding? encoding,
}) => _client.patch(url, headers: headers, body: body, encoding: encoding);

Future<http.Response> delete(
  Uri url, {
  Map<String, String>? headers,
  Object? body,
  Encoding? encoding,
}) => _client.delete(url, headers: headers, body: body, encoding: encoding);
