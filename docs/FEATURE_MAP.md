# Feature Map: where is X implemented?

Paths are shortened:

- `api/`, `blueprints/`, `templates/` and root `.py` files are under `SUAAMS/`
- `lib/` is `SUAAMS_Mobile/suaams/lib/`
- `HCE.ino` is `ESP32_ARDUINO CODE/SUAAMS_HCE/SUAAMS_HCE.ino`

A dash means that part isn't involved. Update this file in the same commit as
the feature.

## Check-in

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| NFC code format | Creates and checks the 32-char signed code | `beacon.py` | — | — | — |
| NFC: mint code | Gives the phone a code bound to student + session + 10 s expiry | `api/student.py` `mint_checkin_beacon` | `features/student/data/student_service.dart` `mintCheckinBeacon` | — | `sessions`, `enrollments` |
| NFC: card emulation | Phone answers the reader's SELECT with the code; native expiry | — | `android/.../SuaamsHceService.kt`, `android/.../MainActivity.kt` (method channel `suaams/hce`), `res/xml/apduservice.xml` (AID) | — | — |
| NFC: Dart bridge | Starts/stops HCE, checks NFC availability | — | `features/student/data/nfc_service.dart` | — | — |
| NFC: read + submit | Reads the code in one APDU and POSTs it with terminal headers | `api/student.py` `submit_checkin_beacon`, `_check_terminal_auth` | — | `HCE.ino` `readBeacon`, `submitBeaconToken` | `attendance` |
| NFC: confirmation | App polls until attendance appears (up to 25 s) | `api/student.py` `get_checkin_status` | `features/student/providers/nfc_provider.dart` `_startConfirmationPolling` | — | `attendance` |
| Check-in flow / states | RASP gate → channel choice → fingerprint → mint/scan → result | — | `features/student/providers/nfc_provider.dart`, `presentation/views/nfc_broadcast_sheet.dart` | — | — |
| BLE code format | Rotating 14-byte payload, 5 s slots; bench checker `python ble_beacon.py <hex>` | `ble_beacon.py` | — | `HCE.ino` `bleBuildPayload`, `bleSelfTest` | — |
| BLE: broadcast | Advertises the code, rotates every 5 s, waits for NTP | — | — | `HCE.ino` `bleSetup`, `bleUpdate` | — |
| BLE: scan + submit | Listens up to 8 s, posts the payload | `api/student.py` `submit_ble_checkin` | `features/student/data/ble_scan_service.dart`, `nfc_provider.dart` `_runBleCheckIn` | — | `attendance` |
| Which channels are on | Server reports `{nfc, ble}` from its configured secrets | `api/student.py` `get_checkin_methods` | `features/student/providers/checkin_method_provider.dart` | — | — |
| Check-in method setting | Automatic / NFC / Bluetooth choice in profile | — | `features/student/presentation/views/checkin_method_sheet.dart`, `checkin_method_provider.dart` | — | — |
| Offline queue | Stores up to 16 tokens in flash, uploads on reconnect | `api/student.py` `sync_offline_checkin_backlog` | — | `HCE.ino` `appendToBacklog`, `flushBacklog` | `offline_checkin_logs` |
| Keep server warm | Pings `/healthz` every 4 min and before a POST if not warm | `app.py` `healthz` | — | `HCE.ino` `maybeKeepBackendWarm`, `ensureBackendWarmForPost` | — |
| Present vs late | `late` if > 10 min after `planned_start` (campus time) | `utils.py` `compute_attendance_status` | `shared/utils/attendance_status.dart` (display) | — | `attendance` |
| Legacy RFID capture | Old MFRC522 card route, terminal-secret gated | `api/hardware.py` `/attendance` | — | `SUAAMS_ESP/`, `SUAAMS_/` (old sketches) | `students.rfid_uid` |

## Security

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| Fingerprint / PIN gate | `local_auth` prompt before mint or scan | — | `nfc_provider.dart` `_verifyIdentity` | — | — |
| Device integrity (RASP) | freeRASP startup check; blocks check-in if compromised | — | `core/services/security_service.dart`, `main.dart` | — | — |
| Device binding | Locks account to phone and phone to account; rejects placeholders | `api/auth.py` `mobile_login` | `features/auth/providers/auth_provider.dart` (reads hardware ID) | — | `students.device_id` |
| Unbind phone | Admin clears `device_id` | `blueprints/admin.py` `/students/unbind/<id>` | `features/student/presentation/views/linked_devices_screen.dart` (read-only view) | — | `students` |
| Device info | Shows the bound device to the student | `api/student.py` `get_device_info` | `features/student/providers/device_info_provider.dart` | — | `students` |
| Required secrets | Server refuses to boot without DB/session/JWT secrets | `app.py` `_require_env`, `.env.example` | — | `secrets.h.example` | — |
| Rate limits | Per-IP or per-user limits on every write route | `extensions.py` (`limiter`), decorators on routes | — | — | — |
| CSRF (web) | Flask-WTF on dashboard forms | `extensions.py` (`csrf`) | — | — | — |

## Accounts and login

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| Mobile login | Password + device binding, issues JWT pair | `api/auth.py` `mobile_login` | `features/auth/data/auth_service.dart`, `presentation/login_screen.dart` | — | `users`, `students` |
| Token refresh / logout | Rotating refresh token; logout revokes it | `api/auth.py` `/refresh`, `/logout` | `core/network/auth_retry.dart`, `auth_service.dart` | — | `users.current_refresh_jti` |
| Forced password change | First-login change | `api/auth.py` `/change-password`, `blueprints/auth.py` | `features/auth/presentation/change_password_screen.dart` | — | `users.requires_password_change` |
| Web login | Session-cookie login for dashboards | `blueprints/auth.py`, `utils.py` `login_required` | — | — | `users` |
| Onboarding | First-run screens | — | `features/onboarding/presentation/onboarding_screen.dart`, `core/providers/onboarding_provider.dart` | — | — |
| Routing / role shells | Sends each role to its home | — | `core/router/app_router.dart`, `student_shell_screen.dart`, `lecturer_shell_screen.dart` | — | — |

## Student features

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| Dashboard stats | Attendance summary | `api/student.py` `/dashboard` | `features/student/providers/student_provider.dart`, `student_home_screen.dart` | — | `attendance`, `enrollments` |
| Today's classes | Live status per class today | `api/student.py` `/schedule/today` | `today_schedule_provider.dart` | — | `timetable`, `sessions` |
| Weekly timetable | Recurring schedule | `api/student.py` `/schedule/week` | `week_schedule_provider.dart`, `student_timetable_screen.dart`, `day_detail_screen.dart` | — | `timetable` |
| Attendance records | By course / session / day | `api/student.py` `/course/<id>/history` | `course_attendance_history_provider.dart`, `records_view.dart`, `course_attendance_detail_screen.dart`, `session_history_screen.dart` | — | `attendance`, `sessions` |
| Course registration | Register/drop for the active semester | `api/student.py` `/courses/available`, `/courses/<id>/register`, `/drop` | `course_registration_provider.dart`, `course_registration_screen.dart` | — | `enrollments`, `semesters` |
| Digital ID card | On-screen student ID | — | `student_id_card_screen.dart`, `core/providers/card_privacy_provider.dart` | — | — |
| Announcements | Course/dept/university notices | `api/student.py` `/announcements`, `/announcements/seen` | `student_announcements_provider.dart`, `announcements_screen.dart` | — | `announcements` |
| Notifications + push | In-app list, FCM push | `api/student.py` `/notifications`, `/device-token`; `push_notifications.py` | `core/services/notification_service.dart`, `notifications_provider.dart` | — | `notifications`, `device_tokens` |
| Theme | Automatic / Dark / Light | — | `core/providers/theme_provider.dart`, `shared/widgets/theme_mode_sheet.dart` | — | — |
| Student web portal | Dashboard, courses, attendance, announcements | `blueprints/student.py` | — | — | — |

## Lecturer features

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| Dashboard + schedule | Today and week | `api/lecturer.py` `/dashboard`, `/schedule/week`; `blueprints/lecturer.py` | `lecturer_provider.dart`, `lecturer_week_schedule_provider.dart`, `lecturer_home_screen.dart` | — | `courses`, `timetable` |
| Start / end session | Opens or closes check-in for a course | `api/lecturer.py` `start_session`, `end_session`; `blueprints/lecturer.py` | `course_workspace_provider.dart`, `course_workspace_screen.dart` | — | `sessions` |
| Live attendance | Who has checked in so far | `api/lecturer.py` `/course/<id>/session/<id>`; `blueprints/lecturer.py` `/lecturer/sessions/active` | `session_detail_provider.dart`, `active_sessions_screen.dart`, `lecturer_session_detail_screen.dart` | — | `attendance` |
| Session history | Past sessions per course | `api/lecturer.py` `/course/<id>/history` | `session_history_provider.dart`, `lecturer_session_history_screen.dart` | — | `sessions` |
| Analytics | Attendance rates per course | `api/lecturer.py` `/course/<id>/analytics`; `blueprints/lecturer.py` `/lecturer/analytics` | `course_analytics_provider.dart`, `course_analytics_screen.dart` | — | `attendance` |
| CSV export | Course register / reports | `api/lecturer.py` `/course/<id>/export`; `utils.py` `build_course_register_csv` | `course_export_provider.dart`, `reports_list_screen.dart` | — | `attendance` |
| Announcements | Post/delete; pushes to students | `api/lecturer.py` `/announcements`; `utils.py` `students_for_announcement` | `announcements_provider.dart`, `create_announcement_screen.dart` | — | `announcements`, `notifications` |
| Manual marking | Lecturer marks an enrolled student present (during or after the session). Never overwrites a real check-in; always `present`; `method = manual` | `utils.py` `mark_student_present`; `api/lecturer.py` `mark_present`; `blueprints/lecturer.py` `mark_present_r` | `lecturer_service.dart`, `session_detail_provider.dart`, `lecturer_session_detail_screen.dart` | — | `attendance` (`marked_by`) |
| Offline-tap review | **Not built** (rows exist in `offline_checkin_logs`) | — | — | — | `offline_checkin_logs` |

## Admin and HOD (web only)

| Feature | What it does | Server | Templates | Tables |
|---|---|---|---|---|
| Faculties / departments | Organisation setup | `blueprints/admin.py` `/organization` | `templates/admin/` | `faculties`, `departments` |
| Accounts | Lecturers, HODs, students; CSV bulk enrol | `blueprints/admin.py` `/lecturers`, `/hods`, `/students`, `/students/bulk-enroll` | `templates/admin/` | `users` + profiles |
| Courses, semesters | One active semester at a time | `blueprints/admin.py` `/courses`, `/semesters` | `templates/admin/` | `courses`, `semesters` |
| Timetable + "Happening Now" | Weekly slots, live banner | `blueprints/admin.py` `/timetable`, `/timetable/current`; `utils.py` `resolve_timetable_slot_for_course` | `templates/admin/` | `timetable` |
| Reports | Attendance reports + CSV | `blueprints/admin.py` `/reports`, `/reports/export` | `templates/admin/` | `attendance` |
| HOD views | Overview, by level, students, sign-offs (placeholder) | `blueprints/hod.py` | `templates/hod/` | `students`, `attendance` |

## Tests

| What | Where |
|---|---|
| NFC token format, size, expiry, forgery | `SUAAMS/tests/test_beacon.py` |
| BLE payload + reference vector (same vector as firmware self-test) | `SUAAMS/tests/test_ble_beacon.py` |
| Campus time | `SUAAMS/tests/test_campus_time.py` |
| Templates render | `SUAAMS/tests/test_templates.py` |
| Flutter tests | `SUAAMS_Mobile/suaams/test/` |
