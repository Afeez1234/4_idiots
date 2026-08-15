# SUAAMS — Smart Universal Automated Attendance Management System

> Capstone project (Mechatronics Engineering, final year). Solo-led development — Flutter frontend, Flask + SQLAlchemy backend, ESP32 terminal hardware.

This README is a feature inventory of what's **actually built**, organized by who uses it. See [CLAUDE.md](CLAUDE.md) for coding standards and the security threat model in full detail.

---

## Repository layout

```
4_idiots/
├── SUAAMS/                    # Flask API + web dashboards
│   ├── api/                   # JWT-authenticated JSON endpoints (mobile app, ESP32)
│   ├── blueprints/            # Session-authenticated web dashboards (admin, lecturer)
│   ├── models.py              # SQLAlchemy schema (14 tables)
│   ├── push_notifications.py  # Firebase Cloud Messaging helper
│   └── app.py
├── SUAAMS_Mobile/suaams/       # Flutter app (student + lecturer)
│   └── lib/features/{auth,student,lecturer}/
└── ESP32_ARDUINO CODE/         # Terminal firmware
    ├── SUAAMS_HCE/             # Current: PN532 + NFC HCE reader (production track)
    └── SUAAMS_ESP, SUAAMS_/    # Legacy: MFRC522 physical-card RFID prototypes
```

---

## Feature inventory

### Admin (web dashboard — `blueprints/admin.py`)
- Organization management: faculties, departments (create + delete)
- Lecturer accounts (create, list)
- Student accounts (create, list, **bulk CSV enrollment**)
- Student device unbinding (`/students/unbind/<id>`) — the manual reset path for the device-binding security lock
- Course management (create/list, tied to department + semester)
- Timetable builder (weekly recurring slots, `scheduled` vs one-off `fixed` type)
- Semester management (create/list, one active semester at a time — app-enforced, not DB-enforced)
- HOD account management (`role='hod'` users, department-scoped)
- University/department/course-scoped announcements

### Lecturer
**Web dashboard** (`blueprints/lecturer.py`):
- Dashboard, per-course workspace view
- Session history, session detail
- Start / end a live session
- Announcements (view + post)
- Analytics, reports (+ export)

**Mobile app** (`lib/features/lecturer/`, backed by `api/lecturer.py`):
- Dashboard, course workspace screen
- Start-session / end-session
- Live attendance view (who has checked in, in real time, while a session is active)
- Session history + session detail
- Course analytics screen
- Announcements: list + create
- Reports list
- Profile screen

### Student
**Mobile app only** (`lib/features/student/`, backed by `api/student.py`) — the primary student surface; the web dashboard side (`blueprints/student.py`) is a single legacy stub route.
- Login, forced password change on first login, splash screen
- Home dashboard, courses view, course detail, records view
- **NFC HCE check-in**: broadcasts a short-lived signed beacon token to the ESP32 terminal (`nfc_provider.dart`, `nfc_service.dart`, `nfc_broadcast_sheet.dart`)
- Check-in status polling, attendance screen, course attendance detail, session detail, day detail
- Session/attendance history
- Digital student ID card screen
- Timetable screen (today's schedule + weekly view)
- Linked devices screen (shows the bound device; unbinding itself requires admin action)
- Push notification settings + in-app notification list
- Profile screen

### Auth (both web and mobile — `blueprints/auth.py`, `api/auth.py`)
- Login (bcrypt password + role lookup)
- Forced password change flow
- Mobile: JWT access/refresh tokens, with refresh-token rotation and revocation via `User.current_refresh_jti`
- Logout

### Notifications
- Firebase Cloud Messaging push, via `push_notifications.py`
- Device token registration per install (`DeviceToken` table — a user can hold tokens for multiple installs)
- Every push is also persisted as an in-app `Notification` row, so the notification list works even if the push itself was missed offline
- Deep-link payload support (`data` JSON column) to route a tapped notification straight to a screen

### Hardware (ESP32 terminal)
- **Current / production track**: `SUAAMS_HCE` — ESP32 + PN532 reader, speaks NFC HCE (ISO 7816-4 APDU) to the phone, submits the beacon token to `/api/v1/student/checkin`
- **Legacy prototypes**: `SUAAMS_ESP` / `SUAAMS_` — ESP32 + MFRC522, physical RFID card tap, posts to the older `/attendance` route. Kept in the repo but superseded by the HCE flow.
- ESP32-facing API blueprint (`api/hardware.py`): active-session lookup, attendance submission

---

## Security features (implemented)

| Threat | Defense | Where |
|---|---|---|
| Buddy punching | Mandatory biometric/PIN before any NFC/BLE transaction; app only broadcasts after OS returns success | `nfc_provider.dart` |
| Device binding | Account locked to first-login device's hardware ID; different device = instant lockout; reset requires admin action | `Student.device_id`, admin `/students/unbind` |
| Biometric invalidation | Keys bound to current biometric enrollment set; adding/removing a fingerprint invalidates the key | Android `invalidateByBiometricEnrollment`, iOS `kSecAccessControlBiometryCurrentSet` |
| Relay attacks | Signed, short-lived beacon token — **3-second server-side acceptance window** | `BEACON_TOKEN_TTL_SECONDS`, `api/student.py` |
| Rooted/jailbroken devices | Startup integrity check refuses to generate transaction payloads | `freerasp` integration |
| Duplicate attendance | DB-level unique constraint, one `Attendance` row per (student, session) | `models.py` |

---

## Architecture stack

- **Frontend**: Flutter (Dart), Riverpod 3.x, GoRouter, Flutter Secure Storage
- **Backend**: Flask, Flask-SQLAlchemy (ORM-only, no raw SQL), Flask-JWT-Extended, Flask-Migrate, Flask-Limiter, CSRF protection on session-authenticated routes
- **Database**: MySQL (Clever Cloud) — 14-table schema (organizations, auth, academic structure, timetable/sessions, attendance, announcements, results, notifications)
- **Deployment**: Render (backend), with a `/healthz` keep-warm endpoint for external uptime pinging
- **Hardware**: ESP32 + PN532 (NFC HCE) / MFRC522 (legacy RFID)

---

## Not yet built (roadmap, per CLAUDE.md)

- **Timetable automation**: no autonomous session start/stop yet — timetable rows exist as data, but nothing currently auto-opens a session when class time arrives (planned: web "Open Terminal" banner, then a Flask-APScheduler worker)
- **Self-service course enrollment**: students can't register for courses themselves yet — admin enrolls them (bulk CSV) today
- **HOD dashboard**: `role='hod'` accounts can be created via admin, but no HOD-facing dashboard exists yet

---

## Getting started

### Backend

```bash
cd SUAAMS
pip install -r requirements.txt
export FLASK_APP=app.py
flask db upgrade
flask run
```

### Mobile app

```bash
cd SUAAMS_Mobile/suaams
flutter pub get
flutter run
```

Requires: Python 3.8+, MySQL access, Flutter SDK 3.0+, Android SDK / Xcode.
