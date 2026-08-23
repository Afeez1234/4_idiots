//The oga nla, This is the main entry point of the app. It sets up the MaterialApp, applies the dark theme, and configures routing with GoRouter.

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'core/router/app_router.dart';
import 'core/services/notification_service.dart';
import 'core/services/security_service.dart';
import 'core/theme/app_theme.dart';
import 'core/providers/theme_provider.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Started before anything else touches the network or renders a screen --
  // CLAUDE.md's threat model wants integrity-checking to run "on startup",
  // and SecurityService.isCompromised needs to already be populated by the
  // time a user could reach the check-in flow.
  await SecurityService.instance.initialize();
  await Firebase.initializeApp();
  // Must be registered before runApp -- this is what lets FCM invoke
  // firebaseMessagingBackgroundHandler in its own isolate for messages that
  // arrive while the app is backgrounded/terminated.
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  await NotificationService.instance.initialize();
  runApp(const ProviderScope(child: MobileClientApp()));
}

class MobileClientApp extends ConsumerWidget {
  const MobileClientApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final router = ref.watch(appRouterProvider);
    final themeMode = ref.watch(themeProvider);
    return MaterialApp.router(
      theme: AppTheme.lightTheme,
      darkTheme: AppTheme.darkTheme,
      themeMode: themeMode,
      title: 'Attendance Mobile',
      debugShowCheckedModeBanner: false,
      routerConfig: router,
    );
  }
}
