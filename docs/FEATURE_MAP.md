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
| Offline queue | Stores up to 100 tokens with their read time in flash, uploads 25 at a time on reconnect. A token read more than 15 s after it was made is rejected at upload (a replay); only well-formed 32-character tokens are queued | `api/student.py` `sync_offline_checkin_backlog` | — | `HCE.ino` `appendToBacklog`, `flushBacklog` | `offline_checkin_logs` |
| Keep server warm | Pings `/healthz` every 4 min and before a POST if not warm | `app.py` `healthz` | — | `HCE.ino` `maybeKeepBackendWarm`, `ensureBackendWarmForPost` | — |
| Present vs late | `late` if > 10 min after `planned_start` (campus time) | `utils.py` `compute_attendance_status` | `shared/utils/attendance_status.dart` (display) | — | `attendance` |
| Legacy RFID capture | **Removed 2026-10-12.** The old sketches remain for reference and would now get a 404 | — | — | `SUAAMS_ESP/`, `SUAAMS_/` (old sketches) | `students.rfid_uid` (unused) |

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
| Forced password change | First-login change. On the web it's enforced on every request (`enforce_account_state`), so it can't be skipped | `api/auth.py` `/change-password`, `blueprints/auth.py` | `features/auth/presentation/change_password_screen.dart` | — | `users.requires_password_change` |
| Web login | Session-cookie login for dashboards; a disabled account is signed out mid-session | `blueprints/auth.py`, `utils.py` `login_required` | — | — | `users` |
| Personal admin logins | One login per person who runs the dashboard; create or disable from the command line | `create_admin.py` | — | — | `users` |
| Activity log (audit trail) | Who changed what on the admin dashboard, plus admin sign-ins; filter by person and type at `/admin/activity` | `audit.py` `log_action`; `blueprints/admin.py` `activity_page`; `templates/admin/activity.html` | — | — | `audit_logs` |
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
| Notifications + push | In-app list, FCM push. The in-app row is saved in the request; the phone push is sent from a 2-thread background pool after the request answers, so a check-in never waits on Firebase | `api/student.py` `/notifications`, `/device-token`; `push_notifications.py` | `core/services/notification_service.dart`, `notifications_provider.dart` | — | `notifications`, `device_tokens` |
| Notification taps | A timetable notification opens the user's own timetable tab (student or lecturer), reloading it first; attendance opens that session. A tap that opens a closed app is held until the splash screen restores the session | — | `core/services/notification_service.dart` `_routeForData`, `openPendingTap`; `features/auth/presentation/splash_screen.dart` | — | — |
| Loading skeletons | Placeholder layout on first load: home, today's list, timetable, day detail, attendance courses, history. Refreshes keep old data on screen; a failed first load shows a retry | — | `shared/widgets/app_skeleton.dart`; `student_home_screen.dart` `_HomeSkeleton`; `courses_view.dart` `_CoursesSkeleton`; `records_view.dart`; `student_timetable_screen.dart`; `day_detail_screen.dart`. Loaders: `student_provider.dart`, `today_schedule_provider.dart`, `week_schedule_provider.dart` | — | — |
| Theme | Automatic / Dark / Light | — | `core/providers/theme_provider.dart`, `shared/widgets/theme_mode_sheet.dart` | — | — |
| Student web portal | Dashboard, courses, attendance, announcements | `blueprints/student.py` | — | — | — |

## Lecturer features

| Feature | What it does | Server | App | Firmware | Tables |
|---|---|---|---|---|---|
| Dashboard + schedule | Today and week | `api/lecturer.py` `/dashboard`, `/schedule/week`; `blueprints/lecturer.py` | `lecturer_provider.dart`, `lecturer_week_schedule_provider.dart`, `lecturer_home_screen.dart` | — | `courses`, `timetable` |
| Several lecturers per course | One coordinator (`courses.lecturer_id`) plus co-lecturers (`course_lecturers`), all with the same powers. Admin manages them on the Courses page by staff ID; each session records who started it | `utils.py` `teaches`, `courses_taught_by`, `taught_course`; `blueprints/admin.py` `_manage_course_lecturer`; `models.py` `Course.co_lecturers` | — | — | `course_lecturers`, `sessions.started_by` |
| Start / end session | Opens or closes check-in for a course | `api/lecturer.py` `start_session`, `end_session`; `blueprints/lecturer.py` | `course_workspace_provider.dart`, `course_workspace_screen.dart` | — | `sessions` |
| Live attendance | Who has checked in so far | `api/lecturer.py` `/course/<id>/session/<id>`; `blueprints/lecturer.py` `/lecturer/sessions/active` | `session_detail_provider.dart`, `active_sessions_screen.dart`, `lecturer_session_detail_screen.dart` | — | `attendance` |
| Session history | Past sessions per course | `api/lecturer.py` `/course/<id>/history` | `session_history_provider.dart`, `lecturer_session_history_screen.dart` | — | `sessions` |
| Analytics | Attendance rates per course | `api/lecturer.py` `/course/<id>/analytics`; `blueprints/lecturer.py` `/lecturer/analytics` | `course_analytics_provider.dart`, `course_analytics_screen.dart` | — | `attendance` |
| CSV export | Course register / reports | `api/lecturer.py` `/course/<id>/export`; `utils.py` `build_course_register_csv` | `course_export_provider.dart`, `reports_list_screen.dart` | — | `attendance` |
| Announcements | Post/delete; pushes to students | `api/lecturer.py` `/announcements`; `utils.py` `students_for_announcement` | `announcements_provider.dart`, `create_announcement_screen.dart` | — | `announcements`, `notifications` |
| Manual marking | Lecturer marks an enrolled student present (during or after the session). Never overwrites a real check-in; always `present`; `method = manual` | `utils.py` `mark_student_present`; `api/lecturer.py` `mark_present`; `blueprints/lecturer.py` `mark_present_r` | `lecturer_service.dart`, `session_detail_provider.dart`, `lecturer_session_detail_screen.dart` | — | `attendance` (`marked_by`) |
| Offline-tap review | Lecturer accepts or rejects taps the terminal saved while offline; accepted ones become attendance with `method = offline` | `utils.py` `review_offline_tap`, `accept_all_offline_taps`; `api/lecturer.py`; `blueprints/lecturer.py` | `lecturer_service.dart`, `session_detail_provider.dart`, `lecturer_session_detail_screen.dart` | — | `offline_checkin_logs`, `attendance` |

## Admin and HOD (web only)

| Feature | What it does | Server | Templates | Tables |
|---|---|---|---|---|
| Admin dashboard (today) | Today's published timetable, each class Upcoming / Due / Late (no session 30 min after the start) / Missed / Live / Ended, with present ÷ enrolled. A banner per late class with "Notify lecturer" (in-app + push to every lecturer on the course, logged, shows "Reminded at"). Check-ins today by method; department rates for the active semester (sessions × enrolled per course); latest check-ins. Fixed number of queries. Timetable nav badge = unpublished drafts | `dashboard_today.py`; `blueprints/admin.py` `/dashboard`, `/timetable/<id>/remind`; `utils.py` `resolve_timetable_slot_for_course` (sets `sessions.timetable_id`) | `admin/dashboard.html`, `base_admin.html`; app: `notification_service.dart` (`class_reminder` tap opens the course) | `timetable`, `sessions`, `attendance`, `enrollments`, `audit_logs`, `notifications` |
| Analytics (semester-wide) | Any semester, picked on the page (default the active one; viewing a past one never changes the active semester), filterable by department (and level for eligibility). A past semester's eligibility list includes students who have since left. (1) Students below 75% in a course, by the course register's rule (finished classes, present or late), once the course has held 3 classes; roll-ups by department and level; lowest 100 on screen, everyone in the CSV (audited). (2) Classes held vs timetabled per course and department: each published slot due weekly from teaching start (first class of the semester), or from its own `effective_from` if it was added or moved later, to today; sessions matched by `timetable_id` or course + weekday + `planned_start`; unmatched ones (and ones from before the slot started) shown as extra. `effective_from` is set on publish and on a hand edit of course, day or time, and carried over when a re-published sheet keeps a class's course, day and times | `analytics.py`; `blueprints/admin.py` `/analytics`, `/analytics/eligibility.csv` | `admin/analytics.html` | `enrollments`, `sessions`, `attendance`, `timetable` (`effective_from`), `students` |
| Terminals (readers) and the room check | Each reader: code, own secret (shown once, SHA-256 stored), room, Bluetooth number, last seen, enable/disable, new secret. A check-in at a reader in another room from the class is flagged `wrong_room` (`ROOM_CHECK=flag`, default) or refused (`enforce`); lecturers see the flag on live/session/offline lists (web and app). The class's room is the one given at start (web form and app start screen, pre-filled from the timetable via the workspace's `today_room`), else its slot's. Old shared `TERMINAL_ID`/`TERMINAL_SECRET` accepted during the changeover | `terminal_rooms.py`; `models.Terminal`; `blueprints/admin.py` `/terminals`; `api/student.py` check-in routes; `utils.start_class_session` (`room`) | `admin/terminals.html`, `lecturer/session_detail.html`, `lecturer/course_workspace.html`; app: `session_detail_model.dart`, `lecturer_session_detail_screen.dart` | `terminals`, `attendance` (`terminal_id`, `wrong_room`), `offline_checkin_logs.wrong_room`, `sessions.room` |
| Faculties / departments | Organisation setup; each department's programme length (4 or 5 years), set in place. Counts come from GROUP BY queries | `blueprints/admin.py` `/organization`, `_organization_counts` | `admin/organization.html` | `faculties`, `departments` |
| Accounts | Lecturers, HODs, students. The student roster lists by matric number when filtered by department or level, newest first otherwise. The lecturer directory searches by name or staff ID, filters by department, and counts each lecturer's courses this semester (coordinated or co-lectured) | `blueprints/admin.py` `/lecturers`, `/hods`, `/students` | `templates/admin/` | `users` + profiles |
| Bulk students / lecturers / courses | CSV upload → preview → confirm. Students: rows with a problem are listed as skipped (with the reason) and the rest are saved. Lecturers and courses: any row error blocks the file. Existing rows are skipped unchanged. Courses list lecturers by staff ID, coordinator first. Template download per kind | `bulk_upload.py`; `blueprints/admin.py` `/bulk/<kind>`, `/bulk/confirm`, `/bulk/<kind>/template.csv` | `admin/bulk_preview.html`, cards on `students.html`, `lecturers.html`, `courses.html` | `users`, `students`, `lecturers`, `courses`, `course_lecturers` |
| Edit / delete (fixing mistakes) | Courses, lecturers, students and HODs: Edit on every row. A new staff ID / matric number moves the login, and the default password if unchanged. Delete only with no history (sessions, results, attendance, classes run); otherwise the reason shows. HODs are "removed as HOD" instead: a promoted lecturer goes back to teaching; a direct HOD's account is deleted, or switched off if it has a record. A promoted HOD's name and staff ID stay in sync with their lecturer record | `record_edits.py`; `blueprints/admin.py` `/<kind>/<id>/edit`, `/<kind>/<id>/delete` | `admin/_edit.html`, `courses.html`, `lecturers.html`, `students.html`, `hods.html` | `courses`, `lecturers`, `students`, `hods`, `users` |
| Status (who is still part of the school) | Students: active, suspended, rusticated, graduated, withdrawn, expelled, deceased. Lecturers: active, on leave, left. Not active = login off + refresh token revoked; student exits release the phone; a coordinator can't be marked Left. One at a time or by CSV with a preview. Never deletes | `people_status.py`; `blueprints/admin.py` `/<kind>/<id>/status`, `/<kind>/status/bulk` | `admin/_status.html`, `admin/status_preview.html` | `students.status`, `lecturers.status`, `users.is_active` |
| Promotion | Every active student up one level, once per academic year, after a preview. Repeaters by CSV; final-year students listed as due to graduate (CSV download feeds the status upload). Undoable | `promotion.py`; `blueprints/admin.py` `/students/promotion*` | `admin/promotion.html` | `students.level`, `departments.programme_years`, `promotion_runs` |
| Courses, semesters | One active semester at a time. The course catalog shows one semester (the active one by default) plus courses with no semester, with search and a department filter; Enroll Student and Course Lecturers list only that semester's courses; every lecturer is listed with their staff ID, coordinator first; Add Course defaults to the viewed semester. Copy courses from another semester (default: the same semester last year) into the viewed one: code, title, department, units, lecturers -- not students or timetable -- through the course upload's preview and checks; existing codes skipped; inactive co-lecturers left out, an inactive coordinator replaced by the next active lecturer, a course with no active lecturer blocks with the reason | `bulk_upload.py` `plan_course_copy`; `blueprints/admin.py` `/courses`, `/courses/copy`, `/semesters` | `templates/admin/` | `courses`, `semesters` |
| Timetable: PDF reader | Reads a Student Affairs one-page sheet: department, level, semester, classes (code, L/T/P, day, time, room). Renders the page to ignore text with no ink (hidden text) | `timetable_pdf.py` `parse_timetable_pdf` | — | — |
| Timetable: import | Up to 10 sheets → preview with checks (course exists, room/lecturer/co-lecturer clashes, same class on several sheets saved once) → saved as drafts. Confirm re-checks | `timetable_import.py`; `blueprints/admin.py` `/timetable/import`, `/timetable/import/confirm` | `admin/timetable_import.html` | `timetable` (`kind`, `is_published`) |
| Timetable: copy last year | Same semester a year earlier's published classes → drafts in this semester, matched by course code, through the import's preview and checks. Dropped courses are noted, not blocking | `timetable_import.py` `plan_copy`, `default_copy_source`; `blueprints/admin.py` `/timetable/copy` | `admin/timetable.html` (card), `admin/timetable_import.html` | `timetable` |
| Timetable: publish | Swaps a semester's drafts in for those courses' published classes in one transaction; notifies only students and lecturers whose classes changed, once each. Hand edits of published classes notify the same way | `timetable_publish.py`; `blueprints/admin.py` `/timetable/publish`, `_notify_timetable_edit` | `admin/timetable.html` | `timetable`, `notifications` |
| Timetable: page | Coverage table (one row per department + level) by default; the weekly grid, Add Slot and "Happening Now" once a department and level are chosen. Add Slot saves into the semester the grid shows (asking first if it isn't the active one). Draft classes are dashed and labelled "Draft" on the grid; Publish has its own "Drafts waiting" card. Level read from the course code | `blueprints/admin.py` `/timetable`, `_timetable_view`, `_timetable_coverage`, `/timetable/current`; `utils.py` `course_level`, `resolve_current_course` | `admin/timetable.html` | `timetable` |
| Reports | Attendance reports + CSV | `blueprints/admin.py` `/reports`, `/reports/export` | `templates/admin/` | `attendance` |
| HOD views | Overview, by level, students, sign-offs (placeholder) | `blueprints/hod.py` | `templates/hod/` | `students`, `attendance` |

## Tests

| What | Where |
|---|---|
| NFC token format, size, expiry, forgery | `SUAAMS/tests/test_beacon.py` |
| BLE payload + reference vector (same vector as firmware self-test) | `SUAAMS/tests/test_ble_beacon.py` |
| Campus time | `SUAAMS/tests/test_campus_time.py` |
| Templates: static checks / every page renders | `SUAAMS/tests/test_templates.py`, `SUAAMS/tests/render_check.py` |
| Check-in routes (NFC, BLE, offline) and login device binding | `SUAAMS/tests/test_checkin.py` |
| Manual marking / offline-tap review | `SUAAMS/tests/test_manual_marking.py`, `test_offline_tap_review.py` |
| Admin logins, activity log, bulk upload | `SUAAMS/tests/test_audit.py` |
| Rate-limit keys (per person, per terminal) | `SUAAMS/tests/test_rate_limits.py` |
| Start/end session | `SUAAMS/tests/test_class_sessions.py` |
| Bulk notifications and announcement audience | `SUAAMS/tests/test_notifications.py` |
| Disabled accounts, dropping courses, level rule | `SUAAMS/tests/test_account_rules.py` |
| Query counts: HOD, student dashboard, analytics | `SUAAMS/tests/test_hod_attendance.py`, `test_page_queries.py` |
| One attendance rule (finished classes, present or late) across student app, HOD, register, Reports | `SUAAMS/tests/test_attendance_rule.py` |
| Readers' own secrets, room check (flag / enforce / off), Terminals page | `SUAAMS/tests/test_terminal_rooms.py` |
| Several lecturers per course | `SUAAMS/tests/test_course_lecturers.py` |
| Timetable PDF reader (look-alike sheet; real sheets only if present locally) | `SUAAMS/tests/test_timetable_pdf.py`, fixture generator `tests/fixtures/timetables/make_sample.py` |
| Timetable import, publish + notifications, page view, copy | `SUAAMS/tests/test_timetable_import.py`, `test_timetable_publish.py`, `test_timetable_view.py`, `test_timetable_copy.py` |
| Bulk lecturers / courses | `SUAAMS/tests/test_bulk_upload.py` |
| Status, promotion, Organization counts | `SUAAMS/tests/test_people_status.py`, `test_promotion.py` |
| Edit / delete, HOD removal | `SUAAMS/tests/test_record_edits.py` |
| Admin dashboard: slot status, session matching, reminders, query count | `SUAAMS/tests/test_dashboard_today.py` |
| Analytics: eligibility rule, held vs timetabled, query count | `SUAAMS/tests/test_analytics.py` |
| Flutter tests | `SUAAMS_Mobile/suaams/test/` |
| **All of the above, on every push** | `.github/workflows/tests.yml` (GitHub Actions) |
