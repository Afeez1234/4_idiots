# SUAAMS — Smart Universal Automated Attendance Management System

Final-year Mechatronics Engineering capstone. Students mark attendance by
**tapping their phone on a small terminal at the lecture hall door**, after
proving who they are with their fingerprint. No paper register, no ID card,
no queue at a fingerprint scanner.

This document explains how the system works as it stands today. For the
details behind it, see [Where to go next](#11-where-to-go-next).

---

## 1. The idea in one minute

- A **lecturer** starts a class session (from the phone app or the web
  dashboard).
- A **student** walks in, opens the SUAAMS app, presses *Check in*, and puts
  their finger on the phone's sensor.
- The phone then gives the **terminal** (an ESP32 board with an NFC reader)
  a one-time code when it is tapped against it.
- The terminal sends that code to the **server**, which checks it and records
  the student as present (or late).
- The student gets a "you've been marked present" notification, and the
  lecturer sees them appear on the live attendance list.

**Why phones and not a fingerprint scanner on the door?** A door scanner takes
about 2 seconds per student, so a 200-student hall needs roughly 7 minutes
of queuing. A phone tap takes under half a second. Fingerprint scanners also
hold only a few hundred to ~1,000 fingerprints and are hard to keep in sync
across many doors. With SUAAMS, each student's fingerprint stays on their own
phone, and the terminal only ever handles a 32-character code. That means
there is no limit on how many students can enrol.

---

## 2. The three parts

```
 ┌──────────────────────┐        ┌──────────────────────┐        ┌──────────────────────┐
 │   Mobile app         │  NFC   │   Terminal           │  HTTPS │   Server             │
 │   (Flutter)          │ ─────► │   ESP32 + PN532      │ ─────► │   Flask API + MySQL  │
 │                      │  tap   │   at the door        │  Wi-Fi │   on Render          │
 │  students, lecturers │        │                      │        │                      │
 └──────────┬───────────┘        └──────────────────────┘        └──────────▲───────────┘
            │                    HTTPS (login, check-in code, dashboards)    │
            └────────────────────────────────────────────────────────────────┘
                                         ▲
                     Web dashboards ─────┘ (admin, HOD, lecturer, student)
```

| Part | What it is | Where in the repo |
|---|---|---|
| **Mobile app** | Flutter app for students and lecturers, Android and iOS | [SUAAMS_Mobile/suaams/](SUAAMS_Mobile/suaams/) |
| **Server** | Python/Flask API, plus web dashboards for admin, HOD, lecturer, student. MySQL database (17 tables) hosted on Clever Cloud, server hosted on Render | [SUAAMS/](SUAAMS/) |
| **Terminal** | ESP32 microcontroller + PN532 NFC reader. Also broadcasts a Bluetooth signal for phones without NFC | [ESP32_ARDUINO CODE/SUAAMS_HCE/](ESP32_ARDUINO%20CODE/SUAAMS_HCE/) |

The other sketches in `ESP32_ARDUINO CODE/` (`SUAAMS_ESP`, `SUAAMS_`) are the
original prototype that read plastic RFID cards with an MFRC522 reader. They
are kept for reference, but the phone-based system has replaced them.

---

## 3. How a check-in works

There are two ways to check in. **NFC tap** is the main one. **Bluetooth** is
the fallback for phones that can't do NFC (all iPhones, and budget Androids
without an NFC chip). Students can choose *Automatic / NFC / Bluetooth* in
their profile; *Automatic* uses NFC whenever the phone has it.

### 3a. NFC tap (main method, Android)

1. **Fingerprint first.** The student presses *Check in*. The app checks NFC
   is switched on, then asks for a fingerprint (or the phone's PIN). Nothing
   happens unless the phone confirms the identity.
2. **App asks the server for a code.** The server finds the class session the
   student is enrolled in that is running right now, and creates a code tied
   to *that student*, *that session*, and an *expiry time 10 seconds from now*.
3. **Phone acts like a contactless card.** Android's "Host Card Emulation"
   (HCE) lets the phone pretend to be an NFC card that holds the code.
4. **Student taps the terminal.** The PN532 reader asks the phone for the code
   and gets all 34 bytes back in a single exchange (about 0.1 s).
5. **Terminal forwards it.** The ESP32 sends the code to the server over
   Wi-Fi, together with its own terminal password.
6. **Server checks and records.** It verifies the code is genuine, not
   expired, and the session is still running, then saves an attendance record
   as `present` (or `late` if it's more than 10 minutes after the scheduled
   start).
7. **Phone gets confirmation.** The app checks with the server every second
   or so, shows a success screen, and a push notification arrives.

**What the code looks like.** It is not a password or a login token. It is
12 bytes of data (student number, session number, expiry time) plus a
12-byte signature that only the server can produce, encoded as 32 text
characters. Anyone who tries to change or forge it gets rejected. It was made
this small on purpose: the earlier version was about 360 bytes, had to be sent
in six pieces, and taps kept failing. Now it fits in one piece.

### 3b. Bluetooth (fallback, Android and iPhone)

This works the other way round. Every 5 seconds the **terminal** broadcasts
a new short code over Bluetooth. The phone listens for it (after the
fingerprint check) and sends it to the server through its own logged-in
connection. Hearing a current code shows that the phone is in the room.

Bluetooth is weaker evidence than NFC: Bluetooth reaches across a room, while
NFC needs the phone within about 4 cm. Someone inside could, in principle, pass
the code to an absent friend within its 10-second life. That's why Bluetooth
is only the fallback, and why **every attendance record stores which method
was used** (`nfc` or `ble`) so lecturers can see it.

Bluetooth check-in is switched off unless the server has its secret
configured. When it is off, the app hides the option.

### 3c. When the terminal is offline

If the terminal can't reach the server, it saves up to 16 taps and uploads
them when it reconnects. These **do not** count as attendance automatically,
because by then the codes have expired, and accepting expired codes would
reopen the cheating loophole. Instead the server stores them as "pending
verification" with the time of each tap, so a lecturer can decide. (The
records are stored, but there isn't a screen to review them yet. See §7.)

---

## 4. Who can do what

### Students — mobile app
- Log in (forced password change the first time) and a short onboarding
- Home dashboard with today's classes and their live status
- **Check in** by NFC or Bluetooth
- Attendance records: by course, by session, by day
- Register for and drop courses for the current semester
- Weekly timetable
- Digital student ID card
- Announcements and notifications (with push)
- Profile, linked device, check-in method, theme (Automatic / Dark / Light)

There is also a simple student web portal (dashboard, courses, attendance
history, announcements), but the app is the main way students use SUAAMS.

### Lecturers — mobile app and web dashboard
- Dashboard with their teaching schedule for today and the week
- **Start / end a class session** for a course
- Live view of who has checked in during an active session
- **Mark a student present by hand** when their phone can't check in, during
  or after the session. Every manual mark is saved with the lecturer's name
  and shown as "by lecturer", so it's never confused with a real tap.
- Session history and per-session detail, showing how each student checked
  in (tap, Bluetooth or by lecturer)
- Course analytics (attendance rates)
- Export a course register / reports as CSV
- Post and delete course announcements (students get a push notification)

### Head of Department (HOD) — web dashboard
- Department overview
- Attendance broken down by level (100L–500L)
- Student list with each student's attendance percentage
- *Sign-offs* tab is a placeholder for now

### Admin — web dashboard
- Set up faculties and departments
- Create lecturer, HOD and student accounts. Students can also be added in
  bulk from a CSV file. The roster has search, filters and pages.
- **Unbind a student's phone** (see §5)
- Create courses, semesters (one active at a time), and the weekly timetable
- The timetable page shows a live "Happening Now" banner for the class that
  should be running
- University-, department- or course-wide announcements
- Attendance reports with CSV export

---

## 5. Security: how cheating is prevented

| Way someone might cheat | How SUAAMS stops it |
|---|---|
| **A friend checks in for you** ("buddy punching") | The app won't produce a code until the phone confirms the owner's fingerprint/PIN. |
| **Logging into your account on a friend's phone** | Each student account is locked to the first phone it logs in from. Logging in from another phone is refused. Only an admin can unlock it, after the student shows their physical school ID. |
| **One phone holding several students' accounts** | It also works the other way: one phone can only be bound to one student account. Otherwise one person could check in a whole group with their own finger. |
| **Copying a code and using it later or elsewhere** ("relay attack") | Codes expire after **10 seconds** and are tied to one student and one session. For NFC, the attacker would also need to be within ~4 cm of the reader. |
| **Faking a code** | Codes are signed with a secret only the server knows; changing any part of one breaks the signature. |
| **Fake terminal sending codes to the server** | Terminals must send their own ID and secret with every request. |
| **Tampered / rooted / jailbroken phone** | The app runs integrity checks (freeRASP) and refuses to check in on a compromised phone. |
| **Marking attendance twice** | The database allows only one attendance record per student per session. |
| **Credit going to the wrong class** | The session is fixed when the code is created, so a tap can only ever count for the student's own running class, never for another course's session that happens to be running at the same time. (Terminals aren't tied to rooms yet, so the server can't tell *which* door the tap happened at. See §7.) |

All passwords and secret keys are stored in the server's environment settings,
never in the code. The server won't start if any required secret is missing.
Check-in is simply turned off if its secret is missing, rather than falling
back to a weak default.

**Why 10 seconds?** It was 3 seconds at first. Hardware testing showed almost
all of those 3 seconds went on the student walking up and holding the phone
steady, so real students were being rejected. 10 seconds is still far stricter
than common standards (authenticator apps use 30 seconds) and is too short to
carry a captured code anywhere useful.

---

## 6. Technology used

| Area | Technology |
|---|---|
| Mobile app | Flutter (Dart), Riverpod 3 (state), GoRouter (navigation), Flutter Secure Storage, `local_auth` (fingerprint), freeRASP (device integrity), Firebase Cloud Messaging (push) |
| Android-native | Kotlin HCE service (`SuaamsHceService.kt`) so the phone can act as an NFC card |
| Server | Python, Flask, SQLAlchemy, Flask-JWT-Extended (app login tokens), Flask-Migrate, Flask-Limiter (rate limits), Flask-WTF (CSRF protection), bcrypt (password hashing) |
| Web dashboards | Server-rendered HTML templates with Tailwind CSS |
| Database | MySQL on Clever Cloud |
| Hosting | Render |
| Terminal | ESP32, PN532 NFC reader (I²C), NimBLE (Bluetooth), Arduino framework |

Class times are handled in campus time (Africa/Lagos). Exact moments, such as
when a student checked in, are stored in UTC and converted when displayed.

---

## 7. Current status and known gaps

*As of 9 October 2026. Update this date whenever a line below changes.*

**Working and tested**
- NFC tap check-in, end to end, on real hardware
- Bluetooth fallback, end to end, on a real Android phone
- Full login flow with device binding, all four dashboards, notifications,
  course registration, timetable, reports

**Not built yet / limitations**
- **Biometric invalidation**: not built. The plan is to bind check-in to the
  phone's *current* set of enrolled fingerprints, so adding a friend's
  fingerprint to your phone would stop working. Right now the app accepts
  any successful fingerprint or PIN unlock from the phone.
- **Reviewing offline taps**: offline taps are saved (see §3c), but there is
  no screen yet for a lecturer to accept or reject them.
- **Automatic sessions**: sessions are started by hand. The timetable shows
  what *should* be running, but nothing starts or ends sessions
  automatically yet.
- **iPhone Bluetooth check-in**: should work, but nobody has tested it on an
  iPhone yet.
- **HOD sign-offs**: placeholder page only.
- **Terminals aren't tied to rooms**: all terminals share one ID and secret,
  and the server doesn't know which room a terminal is in. A student could
  tap the terminal at another door and still get credit for their own class.
- **No feedback at the door**: the terminal has no LED, buzzer or screen. The
  student only sees the result on their phone.
- **Cold server**: Render's free tier sleeps when idle and takes ~8 seconds
  to wake, which is longer than a code lasts. The terminal pings the server
  every 4 minutes to keep it awake.

---

## 8. Repository layout

```
4_idiots/
├── README.md                     ← this file
├── CLAUDE.md                     ← coding standards for this repo
├── docs/                         ← architecture, decisions, security, API, hardware
├── SUAAMS/                       ← server
│   ├── app.py                    ← starts the app, loads secrets, registers routes
│   ├── models.py                 ← database tables
│   ├── beacon.py                 ← NFC check-in code: create + verify
│   ├── ble_beacon.py             ← Bluetooth rotating code: verify
│   ├── campus_time.py            ← campus timezone helpers
│   ├── api/                      ← JSON endpoints for the app and terminal
│   │   ├── auth.py  student.py  lecturer.py  hardware.py
│   ├── blueprints/               ← web dashboards (admin, hod, lecturer, student, auth)
│   ├── templates/                ← HTML for the dashboards
│   ├── migrations/               ← database version history
│   └── tests/                    ← tests for beacons, campus time, templates
├── SUAAMS_Mobile/suaams/         ← mobile app
│   ├── lib/core/                 ← theme, routing, networking, security service
│   ├── lib/features/auth/        ← login, password change
│   ├── lib/features/student/     ← student screens, NFC + Bluetooth check-in
│   ├── lib/features/lecturer/    ← lecturer screens
│   ├── lib/shared/               ← shared widgets, logo, painters
│   └── android/.../SuaamsHceService.kt  ← native NFC card emulation
└── ESP32_ARDUINO CODE/
    ├── SUAAMS_HCE/               ← current terminal firmware
    ├── PN532_DetectTest/         ← reader bench-test sketch
    └── SUAAMS_ESP/, SUAAMS_/     ← old RFID-card prototype
```

---

## 9. Running it locally

### Server

```bash
cd SUAAMS
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # then fill in the values (ask the project lead)
flask --app app.py db upgrade
flask --app app.py run
```

The server refuses to start until `.env` has the database details,
`SECRET_KEY` and `JWT_SECRET_KEY`. Check-in also needs
`BEACON_SIGNING_SECRET`, `TERMINAL_ID` and `TERMINAL_SECRET`. Bluetooth
check-in needs `BLE_BEACON_SECRET`. The comments in
[SUAAMS/.env.example](SUAAMS/.env.example) explain each one.

### Mobile app

```bash
cd SUAAMS_Mobile/suaams
flutter pub get
flutter run
```

NFC check-in needs a real Android phone with NFC. Emulators can't do it.

### Terminal

Open `ESP32_ARDUINO CODE/SUAAMS_HCE/SUAAMS_HCE.ino` in the Arduino IDE.
Copy `secrets.h.example` to `secrets.h` and fill in Wi-Fi details and the
terminal and Bluetooth secrets (these must match the server's). Install
the *esp32* board package **3.x** (the sketch won't compile on 2.x), plus
*Adafruit PN532* and *NimBLE-Arduino 2.x*, then set **Tools → Partition
Scheme → Huge APP (3MB No OTA)** and upload.

**Update in this order:** server first, then the app, then the terminal. The
three must agree on the code format, so an old app talking to a new server
will fail.

---

## 10. Glossary

| Term | Meaning |
|---|---|
| **NFC** | Near-Field Communication: short-range (~4 cm) wireless, the same as contactless bank cards |
| **HCE** | Host Card Emulation: an Android feature that lets the phone behave like an NFC card |
| **APDU** | The message format NFC cards and readers use to talk to each other |
| **PN532** | The NFC reader chip on the terminal |
| **ESP32** | The Wi-Fi + Bluetooth microcontroller that runs the terminal |
| **BLE** | Bluetooth Low Energy |
| **HMAC** | A signature made with a secret key; it proves the server created a code and that nobody changed it |
| **JWT** | The login token the app uses for its requests to the server |
| **Session** | One class meeting (e.g. MCT 401, Monday 10:00), started and ended by the lecturer |
| **Device binding** | Locking a student account to one phone, and one phone to one student account |
| **Render / Clever Cloud** | The services that host the server and the database |

---

## 11. Where to go next

| If you want to… | Read |
|---|---|
| See each check-in path step by step, with diagrams | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Find where a feature lives in the code | [docs/FEATURE_MAP.md](docs/FEATURE_MAP.md) |
| Know why something was built the way it was | [docs/DECISIONS.md](docs/DECISIONS.md) |
| Read the threat model and the known security gaps | [docs/SECURITY.md](docs/SECURITY.md) |
| Look up an endpoint: who calls it, auth, request/response | [docs/API.md](docs/API.md) |
| Rehearse for the defence | [docs/DEFENSE_QA.md](docs/DEFENSE_QA.md) |
| Wire, flash or debug the terminal | [docs/HARDWARE.md](docs/HARDWARE.md) |
| Follow the coding rules for this repo | [CLAUDE.md](CLAUDE.md) |

Update the matching doc in the same commit as the feature.
