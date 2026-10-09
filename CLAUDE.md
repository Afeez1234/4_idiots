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

**Credentials come from the environment, never from source.** `app.py` reads
`SECRET_KEY`, `JWT_SECRET_KEY`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
through `_require_env()`, which **raises at startup if any is missing**. Copy
`SUAAMS/.env.example` to `SUAAMS/.env` for local work; the real values live
in Render's environment for production.

Never reintroduce an `os.environ.get(NAME, '<literal>')` fallback for a
credential. That pattern is what put the production database password and
both signing keys into git history — and because the resolved value was never
empty, the "missing environment variable" check beneath it could never fire.
It read like enforcement and enforced nothing. `BEACON_SIGNING_SECRET`,
`TERMINAL_ID` and `TERMINAL_SECRET` are checked lazily where they're used, so
their absence disables check-in only, with a logged reason, rather than
preventing the app from booting.

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
mobile (auth + lecturer flows). 17-table schema (see `models.py`), grown
from an original seven-table design built around ESP32 + RFID capture.

### Known active issue


## Security / threat model
Verify new code and flows against these anti-spoofing vectors:
- **Buddy punching**: biometric (FaceID/fingerprint) or device PIN/passcode
  verification is mandatory in-app immediately before any NFC/BLE transaction.
  The app only broadcasts a token after the OS returns a success boolean.
- **Device binding**: accounts are locked to the primary phone's hardware ID
  (`device_id`) at first login. Logging in from a different device is an
  instant lockout. Resetting requires an admin manually nulling the value via
  the Admin Web Dashboard (student presents physical school ID to request it).
  The binding runs both ways: a phone can hold **one student account only**
  (`students.device_id` is unique; `mobile_login` returns `DEVICE IN USE`).
  Without that, one phone could bind several classmates' accounts and its
  owner could check them all in with their own fingerprint. The app must
  never send a placeholder ID when the hardware ID can't be read — a shared
  constant makes every failing phone look like the same device — and the
  backend rejects the old placeholder strings (`DEVICE UNVERIFIED`).
- **Biometric invalidation**: biometric keys bind to the OS's current
  biometric set (`invalidateByBiometricEnrollment: true` on Android,
  `kSecAccessControlBiometryCurrentSet` on iOS). Adding/deleting a fingerprint
  in system settings must instantly invalidate the key, forcing a master
  passcode check — defends against the "add a classmate's print, let them
  check in, then delete it" exploit.
- **Relay attacks**: HCE and BLE proximity tokens carry short-lived,
  cryptographically signed timestamps. **10 seconds is the current strict
  server-side acceptance window** — ESP32 and backend reject any handshake
  older than that, regardless of how long the phone kept broadcasting.
  (`BEACON_TOKEN_TTL_SECONDS` in `beacon.py` is the single source of truth;
  it was 3 until 2026-09-27, when a hardware bench run showed the window was
  being spent on the wrong thing. See that constant for the full reasoning.)
  A relay attacker must capture *and* present the token within this window,
  and be within NFC range (~4cm) to do it — at 10s they cannot walk a
  captured phone anywhere meaningful. For calibration, TOTP/dynamic-password
  systems use 30s and Apple BLE proximity beacons run 5–30s, so this remains
  a tight bound; 3s was strict enough to break legitimate use while
  defending against little that 10s would not.
  The mobile app itself may keep the payload broadcasting a couple seconds
  longer as a UX/hardware buffer before wiping its buffers — those late reads
  are expected to fail server-side validation once the token has expired;
  that's intentional fail-safe behavior, not a bug.
- **Rooted/jailbroken devices**: on startup, run integrity-checking (e.g.
  `freerasp`) and refuse to generate transaction payloads if the OS is
  compromised — closes the runtime-injection bypass of the biometric check.

### Check-in beacon format (rebuilt 2026-09-25)

The beacon is **not** a JWT. It is a compact stateless HMAC handle defined in
`SUAAMS/beacon.py`:

```
payload = student_id(4B) || session_id(4B) || exp_unix(4B)   # 12 bytes
sig     = HMAC-SHA256(BEACON_SIGNING_SECRET, payload)[:12]  # 12 bytes
token   = base64url(payload || sig)                          # 32 chars
```

It replaces a ~360-byte Flask JWT that had to be chunked across six
`61xx`/GET RESPONSE round-trips (~650ms) to cross the PN532 radio link. The
link was measured degrading after ~119 bytes, so taps were unreliable. At
34 bytes the whole read is **one APDU exchange** — do not reintroduce
chunking; `tests/test_beacon.py` fails if the token outgrows a single frame.

Three rules that are load-bearing:
- **`BEACON_SIGNING_SECRET` and `TERMINAL_ID`/`TERMINAL_SECRET` have no
  defaults.** Unset means disabled, not weak. Never give them a fallback
  literal — that pattern is what made the guard in `app.py` dead code.
- **The session is bound at mint time**, not looked up at submit time. Both
  the mint and `/checkin/status` endpoints resolve it through
  `_active_session_for_student()`; they must agree or the app polls forever
  while attendance lands correctly.
- **The expiry is enforced natively** (`SystemClock.elapsedRealtime()`
  deadline in `SuaamsHceService`), not by a Dart `Timer`. Dart timers are
  throttled, don't fire when backgrounded, and used to be skipped entirely
  when the provider was disposed mid-flow.

## Core differentiator (production vision)
Smart ID via Android NFC HCE, with PN532 replacing MFRC522 as reader hardware.
Treat this as first-class whenever touching attendance/ID-related code.

Why phone NFC/BLE instead of door-mounted fingerprint scanners: a physical
scanner takes ~2s/student, so a 200-student lecture hall needs ~6.7 minutes
of queuing; an NFC/BLE handshake (<0.5s) drops that to under 2 minutes.
Physical readers also cap out at a few hundred to ~1000 local fingerprint
templates and don't sync reliably across door terminals at scale — using the
phone's own secure enclave for biometric storage means the ESP32 reader only
ever handles a 32-character signed beacon (not a JWT; see `beacon.py`), so the system scales to any enrollment size
without hardware/template-sync limits.

## Roadmap (planned, not yet built)
- **Timetable automation**: soft version first — web dashboard compares
  current time to the `Timetable` table and shows an "Open Terminal" banner
  when a class is due. Later, a fully autonomous version (Flask-APScheduler
  background worker) auto-starts/stops sessions at scheduled times and
  computes absentees hands-free. ESP32 caches each day's timetable each
  morning so it can log scans offline and push the backlog once
  connectivity returns. (This is why `Session.planned_start`/`planned_end`
  exist as fields distinct from actual check-in timestamps.)
- **Enrollment at scale**: self-service course registration in the Flutter
  app, plus an admin-side bulk CSV uploader (parses registration numbers,
  links to courses, generates default authorization codes).

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