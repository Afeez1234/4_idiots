# SUAAMS — Smart Universal Automated Attendance Management System

## Overview
Capstone project (Mechatronics Engineering, final year). Solo-led development —
teammates handle peripheral tasks (documentation, landing page) only. High-
performance, security-hardened IoT hybrid system: Flutter frontend, Flask +
SQLAlchemy backend, physical ESP32 terminal hardware.

Repo layout:
- `SUAAMS/` — Flask API
- `SUAAMS_Mobile/` — Flutter mobile frontend

Changes to one side (e.g. an API response shape) often require corresponding
changes on the other (e.g. a Flutter model). Always consider both sides when
making changes near the API boundary.

## Working preference (important)
Discuss logic and reasoning first, before writing or generating code.
Explain the approach and tradeoffs, confirm direction, then implement.

## Architecture summary
- **Frontend**: Flutter (Dart), Riverpod v3.x, GoRouter (declarative routing),
  Flutter Secure Storage (hardware cryptographic key store)
- **Backend**: Python/Flask, Flask-SQLAlchemy (ORM), Flask-JWT-Extended
  (stateless auth), Flask-Migrate (version tracking), MySQL (Clever Cloud),
  deployed on Render
- **Hardware**: ESP32 microcontrollers via NFC HCE (APDU ISO 7816-4) and BLE
  (RSSI proximity)

## Frontend (`SUAAMS_Mobile/`) standards

**Imports — absolute only.** Never use relative imports
(`import '../providers/auth_provider.dart'`). Always use absolute package
imports (`import 'package:suaams/features/auth/providers/auth_provider.dart'`).
Relative imports collide with absolute paths in Dart's analyzer, causing
duplicate type definitions and generic bound errors in Riverpod compilation.

**UI performance:**
- Wrap `TextFormField`/dynamic widgets in `RepaintBoundary` — an un-isolated
  blinking cursor forces the whole parent canvas (e.g. `GridOverlayPainter`,
  gradient circles) to redraw 60 times/sec, crushing frame rates.
- Static backgrounds (grids, radial glows, decorative shapes) go inside a
  fixed-size box using `MediaQuery.sizeOf(context)`, with `const` constructors
  where possible.
- Keyboard slide: `resizeToAvoidBottomInset: true` on `Scaffold`,
  `ClampingScrollPhysics` on scroll views. Don't hand-roll animated spacers to
  calculate `viewInsets` height — conflicts with the native layout engine and
  causes skips/frame drops.

**Riverpod 3.x:**
- No legacy `StateNotifier` classes — extend `Notifier<StateT>`.
- Declare with `NotifierProvider.autoDispose<MyNotifier, MyState>(MyNotifier.new)`.
- Use `ref.mounted` for async lifecycle safety, not legacy notifier params.

**Design system:** midnight-black theme, Plus Jakarta Sans, terminal-style
language conventions, custom SUAAMS logo via `CustomPainter`.

**Status:** full auth flow implemented; student dashboard with four tabs;
50-item phased roadmap in place for remaining work.

### Known active issue

## Backend (`SUAAMS/`) standards

**Database — ORM only.** Never execute raw SQL or open direct cursors
(`cursor = connection.cursor()`). Always use SQLAlchemy ORM
(`db.session.add(record)`, `User.query.filter_by(...)`). Raw cursors lead to
thread leaks and connection exhaustion under concurrent IoT + mobile load;
SQLAlchemy's pooling handles this safely.

**Timezone/thread safety:** all timestamps use `datetime.now(timezone.utc)`.
Define strict cascades (`cascade="all, delete-orphan"`) on model relationships
so child records (e.g. attendance ledger nodes) are pruned cleanly when
parents (e.g. sessions) are cleared.

**Architecture:** Blueprint-based — auth, admin, lecturer, student, api.
bcrypt auth, role-based `login_required` decorator. JWT-based endpoints for
mobile (auth + lecturer flows). Seven-table schema, originally designed
around ESP32 + RFID attendance capture.

### Known active issue


## Security / threat model
Verify new code and flows against these anti-spoofing vectors:
- **Buddy punching**: biometric (FaceID/fingerprint) or device PIN/passcode
  verification is mandatory in-app immediately before any NFC/BLE transaction.
- **Device binding**: accounts are locked to the primary phone's hardware ID
  (`device_id`) at first login. Resetting requires an admin manually nulling
  the value via the Admin Web Dashboard.
- **Biometric invalidation**: biometric keys bind to the OS's current
  biometric set. Adding/deleting a fingerprint in system settings must
  instantly invalidate the key, forcing a master passcode check.
- **Relay attacks**: HCE and BLE proximity tokens carry short-lived,
  cryptographically signed timestamps. ESP32 and backend reject any handshake
  exceeding a 3-second window.

## Core differentiator (production vision)
Smart ID via Android NFC HCE, with PN532 replacing MFRC522 as reader hardware.
Treat this as first-class whenever touching attendance/ID-related code.

## File structure reference
- `lib/core/constants/api_constants.dart` — endpoint constants
- `lib/core/theme/app_theme.dart` — base design system
- `lib/core/providers/theme_provider.dart` — dark/light state notifiers
- `lib/features/auth/` — login, change password logic, models & services
- `lib/features/student/` — student dashboards, HCE services, radar drawers
- `lib/shared/` — custom painters and global shared assets
- `models.py` — SQLAlchemy entities
- `api/` — mobile Flask endpoints
- `blueprints/` — web application dashboards

## Conventions
- Keep backend and frontend terminology consistent (e.g. JWT payload field
  names should match what Flutter models expect) — flag mismatches
  proactively rather than assuming they'll be caught later.
- Priority order for all generated/refactored code: compiler stability, low
  UI thread rendering time, database connection safety.