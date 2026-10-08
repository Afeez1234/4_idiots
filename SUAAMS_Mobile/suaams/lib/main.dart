//The oga nla, This is the main entry point of the app. It sets up the MaterialApp, applies the dark theme, and configures routing with GoRouter.

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:suaams/core/router/app_router.dart';
import 'package:suaams/core/services/notification_service.dart';
import 'package:suaams/core/services/security_service.dart';
import 'package:suaams/core/theme/app_theme.dart';
import 'package:suaams/core/providers/card_privacy_provider.dart';
import 'package:suaams/core/providers/onboarding_provider.dart';
import 'package:suaams/core/providers/theme_provider.dart';
import 'package:suaams/features/student/data/nfc_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Started before anything else touches the network or renders a screen --
  // CLAUDE.md's threat model wants integrity-checking to run "on startup",
  // and SecurityService.isCompromised needs to already be populated by the
  // time a user could reach the check-in flow.
  //
  // Guarded: Talsec/FreeRASP throws PlatformException on devices without
  // Google Play Services or with a missing native library, and an
  // unhandled throw here happened before runApp -- so the app crashed on
  // launch rather than degrading. A failed integrity check is a security
  // event, not a reason to refuse to boot; SecurityService records it as
  // "not armed" and the check-in flow fails closed (see isCompromised).
  try {
    await SecurityService.instance.initialize();
  } catch (e) {
    debugPrint('[main] RASP initialization failed: $e');
  }
  await Firebase.initializeApp();
  // Must be registered before runApp -- this is what lets FCM invoke
  // firebaseMessagingBackgroundHandler in its own isolate for messages that
  // arrive while the app is backgrounded/terminated.
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  await NotificationService.instance.initialize();

  // Drop any armed check-in beacon the moment the app stops being
  // foreground. HCE keeps answering SELECTs while the process lives, so a
  // beacon left armed when the student switches apps stays readable to a
  // terminal for the rest of its window. The native side has its own
  // monotonic deadline as the real guarantee -- this just closes the gap
  // immediately rather than leaving a few seconds of exposure.
  //
  // Deliberately onPause/onHide rather than onResume: by the time the app
  // comes back, the window has already closed and clearing then would be
  // too late to matter.
  WidgetsBinding.instance.addObserver(
    AppLifecycleListener(
      onPause: () => NfcService().stopHceEmulation(),
      onHide: () => NfcService().stopHceEmulation(),
    ),
  );

  // Read the first-run flag BEFORE runApp. GoRouter's redirect is
  // synchronous and cannot await a storage read, so a lazily-loaded
  // provider would read as "never seen" on every launch and bounce a
  // returning user back into onboarding every time the app started.
  final seenRoles = await readSeenOnboardingRoles();
  // Same reason as the onboarding read above: the ID card's mask state has to
  // be known before the first frame, or the card visibly flips from masked to
  // revealed a moment after the screen opens.
  final cardDetailsVisible = await readCardDetailsVisible();
  // And the theme: loaded lazily it started dark and flipped a moment
  // later, a visible flash for anyone not on dark.
  final themeMode = await readThemeMode();

  runApp(
    ProviderScope(
      overrides: [
        onboardingProvider.overrideWith(
          () => OnboardingNotifier.seeded(seenRoles),
        ),
        cardPrivacyProvider.overrideWith(
          () => CardPrivacyNotifier.seeded(cardDetailsVisible),
        ),
        themeProvider.overrideWith(() => ThemeNotifier.seeded(themeMode)),
      ],
      child: const MobileClientApp(),
    ),
  );
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
