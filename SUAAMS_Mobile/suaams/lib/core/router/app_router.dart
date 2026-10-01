//This file is the main router for the SUAAMS app. It uses GoRouter to define the navigation structure and implements a security guard to handle authentication-based redirects.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:suaams/features/auth/providers/auth_provider.dart';
import 'package:suaams/features/auth/presentation/splash_screen.dart';
import 'package:suaams/features/auth/presentation/login_screen.dart';
import 'package:suaams/features/auth/presentation/change_password_screen.dart';
import 'package:suaams/core/providers/onboarding_provider.dart';
import 'package:suaams/features/onboarding/presentation/onboarding_screen.dart';

// Student
import 'package:suaams/features/student/presentation/student_shell_screen.dart';
import 'package:suaams/features/student/presentation/student_home_screen.dart';
import 'package:suaams/features/student/presentation/views/course_detail_screen.dart';
import 'package:suaams/features/student/presentation/views/student_timetable_screen.dart';
import 'package:suaams/features/student/presentation/views/day_detail_screen.dart';
import 'package:suaams/features/student/presentation/views/student_attendance_screen.dart';
import 'package:suaams/features/student/presentation/views/course_attendance_detail_screen.dart';
import 'package:suaams/features/student/presentation/views/session_history_screen.dart';
import 'package:suaams/features/student/presentation/views/session_detail_screen.dart';
import 'package:suaams/features/student/presentation/views/student_id_card_screen.dart';
import 'package:suaams/features/student/presentation/views/student_profile_screen.dart';
import 'package:suaams/features/student/presentation/views/linked_devices_screen.dart';
import 'package:suaams/features/student/presentation/views/notification_settings_screen.dart';
import 'package:suaams/features/student/presentation/views/announcements_screen.dart';
import 'package:suaams/features/student/presentation/views/course_registration_screen.dart';

// Lecturer
import 'package:suaams/features/lecturer/presentation/lecturer_shell_screen.dart';
import 'package:suaams/features/lecturer/presentation/lecturer_home_screen.dart';
import 'package:suaams/features/lecturer/presentation/lecturer_profile_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/course_workspace_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/lecturer_session_history_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/lecturer_session_detail_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/active_sessions_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/reports_list_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/course_analytics_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/announcements_list_screen.dart';
import 'package:suaams/features/lecturer/presentation/views/create_announcement_screen.dart';

// Lets code outside the widget tree (NotificationService's tap handler,
// which has no BuildContext of its own) navigate via
// rootNavigatorKey.currentContext -- the standard go_router pattern for
// this, since GoRouter itself lives inside a Riverpod Provider that isn't
// reachable from a plain singleton service.
final rootNavigatorKey = GlobalKey<NavigatorState>();

final appRouterProvider = Provider<GoRouter>((ref) {
  // 1. Create a simple ValueNotifier bridge for GoRouter
  final routerListener = ValueNotifier<bool>(false);

  // 2. Listen to the authProvider. Whenever it changes, trigger the routerListener!
  ref.listen(authProvider, (previous, next) {
    routerListener.value = !routerListener.value;
  });
  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/splash',
    //3. Pass the bridge to GoRouter so it can listen for changes in the auth state
    refreshListenable:
        routerListener, // This allows the router to listen for changes in the auth state
    redirect: (context, state) {
      final authState = ref.read(authProvider);
      final isLoggingIn = state.matchedLocation == '/login';
      final isSplash = state.matchedLocation == '/splash';
      final isChangingPassword = state.matchedLocation == '/change-password';
      final isOnboarding = state.matchedLocation == '/onboarding';
      final user = authState.user;
      // Synchronous by construction -- seeded from disk in main() before
      // runApp precisely so this read can't be an await.
      final hasSeenOnboarding = ref.read(onboardingProvider);

      if (isSplash) return null;

      if (user == null && !isLoggingIn && !isOnboarding) return '/login';

      if (user != null && user.requiresPasswordChange && !isChangingPassword) {
        return '/change-password';
      }

      // First run: everything signed-in routes through onboarding before
      // landing on a home screen. Placed after the password-change check so
      // a forced password change is never buried behind a walkthrough.
      if (user != null && !hasSeenOnboarding && !isOnboarding) {
        return '/onboarding';
      }

      // And the reverse, for when markSeen() has just flipped the flag --
      // without this the button would leave the user parked on a dead route.
      if (isOnboarding && hasSeenOnboarding) {
        if (user == null) return '/login';
        if (user.requiresPasswordChange) return '/change-password';
        if (user.role == 'student') return '/student/home';
        if (user.role == 'lecturer' || user.role == 'hod') return '/lecturer/home';
        if (user.role == 'admin') return '/admin';
        return '/login';
      }

      if (user != null && (isLoggingIn || isSplash)) {
        if (user.role == 'admin') return '/admin';
        // No HOD-specific mobile screen exists -- an HOD promoted from an
        // existing Lecturer account (see hods_page's action ==
        // 'promote_lecturer' in blueprints/admin.py) keeps that Lecturer
        // profile, so mobile is only ever useful to them for their own
        // teaching duties. Routes them into the same portal a plain
        // lecturer gets; get_lecturer_or_403 in api/lecturer.py accepts
        // role 'hod' too so the API calls that screen makes still work.
        if (user.role == 'lecturer' || user.role == 'hod') {
          return '/lecturer/home';
        }
        if (user.role == 'student') return '/student/home';
      }

      return null;
    },

    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(path: '/login', builder: (context, state) => const LoginScreen()),
      GoRoute(
        path: '/onboarding',
        builder: (context, state) => const OnboardingScreen(),
      ),
      GoRoute(
        path: '/admin',
        builder: (context, state) =>
            const Scaffold(body: Center(child: Text('Admin Dashboard'))),
      ),
      GoRoute(
        path: '/change-password',
        // Forced entries (redirect guard above, splash_screen.dart) don't
        // pass `extra` and keep the default isMandatory: true. Voluntary
        // entries (Profile > Account Security) pass extra: false to get a
        // back button -- see ChangePasswordScreen's doc comment.
        builder: (context, state) => ChangePasswordScreen(
          isMandatory: state.extra as bool? ?? true,
        ),
      ),

      // ============ STUDENT: 5-tab bottom nav ============
      // Home, Timetable, Attendance, ID Card, Profile. Each branch below is
      // its own Navigator stack (StatefulShellRoute.indexedStack), so
      // pushing a detail screen in one tab doesn't touch another tab's
      // stack, and switching tabs preserves each one's position.
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            StudentShellScreen(navigationShell: navigationShell),
        branches: [
          // Home
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/student/home',
                builder: (context, state) => const StudentHomeScreen(),
                routes: [
                  GoRoute(
                    path: 'course/:courseId',
                    builder: (context, state) => CourseDetailScreen(
                      courseId: int.parse(state.pathParameters['courseId']!),
                    ),
                  ),
                  GoRoute(
                    path: 'announcements',
                    builder: (context, state) => const AnnouncementsScreen(),
                  ),
                ],
              ),
            ],
          ),

          // Timetable
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/student/timetable',
                builder: (context, state) => const StudentTimetableScreen(),
                routes: [
                  GoRoute(
                    path: 'day/:day',
                    builder: (context, state) =>
                        DayDetailScreen(day: state.pathParameters['day']!),
                  ),
                ],
              ),
            ],
          ),

          // Attendance
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/student/attendance',
                builder: (context, state) => const StudentAttendanceScreen(),
                routes: [
                  GoRoute(
                    path: 'course/:courseId',
                    builder: (context, state) => CourseAttendanceDetailScreen(
                      courseId: int.parse(state.pathParameters['courseId']!),
                    ),
                  ),
                  GoRoute(
                    path: 'history',
                    builder: (context, state) => const SessionHistoryScreen(),
                    routes: [
                      GoRoute(
                        path: 'session/:sessionId',
                        builder: (context, state) => SessionDetailScreen(
                          sessionId: state.pathParameters['sessionId']!,
                        ),
                      ),
                    ],
                  ),
                  GoRoute(
                    path: 'register',
                    builder: (context, state) => const CourseRegistrationScreen(),
                  ),
                ],
              ),
            ],
          ),

          // ID Card
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/student/id-card',
                builder: (context, state) => const StudentIdCardScreen(),
              ),
            ],
          ),

          // Profile
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/student/profile',
                builder: (context, state) => const StudentProfileScreen(),
                routes: [
                  GoRoute(
                    path: 'devices',
                    builder: (context, state) => const LinkedDevicesScreen(),
                  ),
                  GoRoute(
                    path: 'notifications',
                    builder: (context, state) =>
                        const NotificationSettingsScreen(),
                  ),
                ],
              ),
            ],
          ),
        ],
      ),

      // ============ LECTURER: 5-tab bottom nav ============
      // Home, Sessions, Reports, Announce, Profile.
      StatefulShellRoute.indexedStack(
        builder: (context, state, navigationShell) =>
            LecturerShellScreen(navigationShell: navigationShell),
        branches: [
          // Home
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/lecturer/home',
                builder: (context, state) => const LecturerHomeScreen(),
                routes: [
                  GoRoute(
                    path: 'course/:courseId',
                    builder: (context, state) => CourseWorkspaceScreen(
                      courseId: int.parse(state.pathParameters['courseId']!),
                    ),
                    routes: [
                      GoRoute(
                        path: 'history',
                        builder: (context, state) =>
                            LecturerSessionHistoryScreen(
                              courseId: int.parse(
                                state.pathParameters['courseId']!,
                              ),
                            ),
                        routes: [
                          GoRoute(
                            path: 'session/:sessionId',
                            builder: (context, state) =>
                                LecturerSessionDetailScreen(
                                  courseId: int.parse(
                                    state.pathParameters['courseId']!,
                                  ),
                                  sessionId: state.pathParameters['sessionId']!,
                                ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),

          // Sessions
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/lecturer/sessions',
                builder: (context, state) => const ActiveSessionsScreen(),
                routes: [
                  GoRoute(
                    path: 'course/:courseId',
                    builder: (context, state) => CourseWorkspaceScreen(
                      courseId: int.parse(state.pathParameters['courseId']!),
                    ),
                    routes: [
                      GoRoute(
                        path: 'history',
                        builder: (context, state) =>
                            LecturerSessionHistoryScreen(
                              courseId: int.parse(
                                state.pathParameters['courseId']!,
                              ),
                            ),
                        routes: [
                          GoRoute(
                            path: 'session/:sessionId',
                            builder: (context, state) =>
                                LecturerSessionDetailScreen(
                                  courseId: int.parse(
                                    state.pathParameters['courseId']!,
                                  ),
                                  sessionId: state.pathParameters['sessionId']!,
                                ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),

          // Reports
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/lecturer/reports',
                builder: (context, state) => const ReportsListScreen(),
                routes: [
                  GoRoute(
                    path: 'course/:courseId',
                    builder: (context, state) => CourseAnalyticsScreen(
                      courseId: int.parse(state.pathParameters['courseId']!),
                    ),
                  ),
                ],
              ),
            ],
          ),

          // Announce
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/lecturer/announce',
                builder: (context, state) => const AnnouncementsListScreen(),
                routes: [
                  GoRoute(
                    path: 'create',
                    builder: (context, state) =>
                        const CreateAnnouncementScreen(),
                  ),
                ],
              ),
            ],
          ),

          // Profile
          StatefulShellBranch(
            routes: [
              GoRoute(
                path: '/lecturer/profile',
                builder: (context, state) => const LecturerProfileScreen(),
              ),
            ],
          ),
        ],
      ),
    ],
  );
});
