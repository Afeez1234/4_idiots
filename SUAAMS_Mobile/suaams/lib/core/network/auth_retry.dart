// Shared "silent refresh, retry once" wrapper for authenticated API calls.
//
// Before this existed, each provider that made an authenticated call had to
// hand-roll its own expiry handling -- and most didn't: only
// student_provider.dart checked for "expired"/"unauthorized" in the error
// message and force-logged-out; today_schedule_provider.dart (added in an
// earlier session) had no such check at all, so an expired token there just
// surfaced a raw error and left stale data on screen. Routing every
// authenticated call through withAuthRetry fixes that inconsistency in one
// place instead of patching each provider separately, and is also where a
// 401 gets an actual chance to recover (via AuthNotifier.refreshSession())
// instead of immediately forcing the user back to the login screen.
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../features/auth/providers/auth_provider.dart';

bool _looksLikeAuthExpiry(Object error) {
  final msg = error.toString().toLowerCase();
  return msg.contains('expired') || msg.contains('unauthorized');
}

/// Runs `request` with the current access token. If it fails with an
/// expired/unauthorized-looking error, attempts one silent token refresh
/// and retries `request` exactly once with the new token. If the refresh
/// itself fails, or the retried request still fails, logs the user out and
/// rethrows the original/latest error so the caller's existing error UI
/// still shows something sensible.
Future<T> withAuthRetry<T>(
  Ref ref,
  Future<T> Function(String token) request,
) async {
  final token = ref.read(authProvider).user?.token;
  if (token == null) {
    throw Exception('Authentication token missing');
  }

  try {
    return await request(token);
  } catch (e) {
    if (!_looksLikeAuthExpiry(e)) rethrow;

    final refreshed = await ref.read(authProvider.notifier).refreshSession();
    final newToken = ref.read(authProvider).user?.token;

    if (!refreshed || newToken == null) {
      await ref.read(authProvider.notifier).logout();
      rethrow;
    }

    try {
      return await request(newToken);
    } catch (e2) {
      await ref.read(authProvider.notifier).logout();
      rethrow;
    }
  }
}
