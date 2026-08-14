// Push notification plumbing: FCM message handling (foreground/background/
// terminated), local display while the app is foregrounded, tap-to-deep-
// link routing, and device-token sync with the backend. Kept as a plain
// singleton (not a Riverpod provider) because the background message
// handler below MUST be a top-level/static function Firebase can invoke in
// its own isolate, with no ProviderContainer available -- routing this
// through Riverpod would mean two different access patterns for the same
// service depending on app state, for no real benefit.
import 'dart:convert';
import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/data/auth_service.dart';
import '../../features/student/data/student_service.dart';
import '../router/app_router.dart';

// Must be a top-level function (not a class method/closure) -- Firebase
// runs this in a separate background isolate when a data message arrives
// while the app is backgrounded/terminated, which has no access to any
// state from the main isolate. Re-initializing Firebase here is required
// for that reason: this isolate hasn't run main()'s own
// Firebase.initializeApp() call.
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  // Nothing else to do here: the notification itself is already displayed
  // by the OS from the message's `notification` payload (FCM does this
  // automatically for background/terminated state, unlike foreground state
  // where onMessage below has to build+show it manually). The in-app
  // Notification row was already persisted server-side before the push was
  // even sent (see send_push_notification in push_notifications.py) -- this
  // handler exists only because firebase_messaging requires SOME handler to
  // be registered for background messages to be processed at all.
}

class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  static const _channelId = 'suaams_notifications';
  static const _channelName = 'SUAAMS Notifications';

  final FirebaseMessaging _messaging = FirebaseMessaging.instance;
  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();

  bool _initialized = false;

  Future<void> initialize() async {
    // main() calls this once at startup -- guards against a second call
    // (e.g. hot restart in debug) double-registering listeners.
    if (_initialized) return;
    _initialized = true;

    await _localNotifications.initialize(
      settings: const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(),
      ),
      onDidReceiveNotificationResponse: _onLocalNotificationTapped,
    );

    // Android 8+ requires the channel to exist before a notification can be
    // posted to it -- must match the id declared in AndroidManifest.xml's
    // default_notification_channel_id meta-data (used when a push arrives
    // while the app is backgrounded/terminated) so both paths post to the
    // SAME channel rather than the foreground path silently creating a
    // second, differently-configured one.
    const androidChannel = AndroidNotificationChannel(
      _channelId,
      _channelName,
      description: 'Attendance confirmations, security, and account alerts.',
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >()
        ?.createNotificationChannel(androidChannel);

    // iOS: without this, a notification that arrives while the app is in
    // the foreground is delivered silently (no banner) by default -- the OS
    // assumes a foregrounded app will handle display itself, which
    // onForegroundMessage below does via the same local-notifications path
    // used on Android, but the OS still needs this flag to know not to
    // suppress its own presentation.
    await _messaging.setForegroundNotificationPresentationOptions(
      alert: true,
      badge: true,
      sound: true,
    );

    await _messaging.requestPermission(alert: true, badge: true, sound: true);

    FirebaseMessaging.onMessage.listen(_onForegroundMessage);
    FirebaseMessaging.onMessageOpenedApp.listen(_onMessageOpenedApp);
    _messaging.onTokenRefresh.listen((_) => syncDeviceToken());

    // App was fully terminated and got opened BY tapping the notification --
    // onMessageOpenedApp (a stream) never fires for this case since the
    // stream only starts existing once the app is already running.
    final initialMessage = await _messaging.getInitialMessage();
    if (initialMessage != null) {
      _routeForData(initialMessage.data);
    }
  }

  // Called right after a successful login (AuthNotifier.login) and after a
  // restored/refreshed session is confirmed valid (AuthNotifier.
  // checkExistingAuth/refreshSession), plus on every onTokenRefresh above --
  // any of these is a legitimate moment for the backend's record of "which
  // token belongs to this user" to be stale. Fire-and-forget by design (see
  // StudentService.registerDeviceToken's docstring): never awaited by
  // callers, never throws somewhere a caller would need to catch it.
  Future<void> syncDeviceToken() async {
    try {
      final jwt = await AuthService().getToken();
      if (jwt == null) return; // not logged in yet -- nothing to sync against

      final fcmToken = await _messaging.getToken();
      if (fcmToken == null) return;

      final platform = Platform.isIOS ? 'ios' : 'android';
      await StudentService().registerDeviceToken(jwt, fcmToken, platform);
    } catch (e) {
      debugPrint('Device token sync failed (will retry next opportunity): $e');
    }
  }

  // App is in the foreground -- FCM does NOT auto-display anything in this
  // state (unlike background/terminated), so this is the one path
  // responsible for actually showing something to the user.
  void _onForegroundMessage(RemoteMessage message) {
    final notification = message.notification;
    if (notification == null) return;

    _localNotifications.show(
      id: message.hashCode,
      title: notification.title,
      body: notification.body,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      payload: jsonEncode(message.data),
    );
  }

  // App was backgrounded (not terminated) and the user tapped the system
  // tray notification -- FCM delivers the full RemoteMessage directly here,
  // no need to go through the local-notifications payload round-trip
  // _onLocalNotificationTapped below has to.
  void _onMessageOpenedApp(RemoteMessage message) {
    _routeForData(message.data);
  }

  void _onLocalNotificationTapped(NotificationResponse response) {
    final payload = response.payload;
    if (payload == null || payload.isEmpty) return;
    try {
      final data = jsonDecode(payload) as Map<String, dynamic>;
      _routeForData(data);
    } catch (e) {
      debugPrint('Failed to parse notification payload: $e');
    }
  }

  // Single place deciding where a tap lands, regardless of which of the
  // three paths above triggered it (foreground/local-notification tap,
  // background/system-tray tap, or cold-start-from-terminated). Only
  // 'attendance_marked' has enough context (session_id) to deep-link
  // somewhere specific -- the security-alert types (device_unlocked/
  // device_lockout_alert) have no dedicated detail screen yet, so they
  // fall through to the notification list itself, same as an unrecognized
  // future type would.
  void _routeForData(Map<String, dynamic> data) {
    final context = rootNavigatorKey.currentContext;
    if (context == null) return;

    final sessionId = data['session_id'];
    if (data['type'] == 'attendance_marked' && sessionId != null) {
      context.push('/student/attendance/history/session/$sessionId');
      return;
    }

    context.push('/student/profile/notifications');
  }
}
