# Design Decisions

Why things are the way they are. Each entry has four parts: **Problem**,
**Tried**, **Chose** and **Trade-off**. Add a new entry when you make a
decision you might later have to defend or might be tempted to undo. Date it
if you know the date.

---

### D1. Phone fingerprint, not a door fingerprint scanner

- **Problem:** Attendance has to prove the student is physically present and
  is who they claim to be, at lecture-hall scale.
- **Tried:** Considered door-mounted fingerprint scanners, the obvious option.
  They take about 2 s per student, which is about 7 minutes of queuing for 200
  students. They also hold only a few hundred to ~1,000 templates and are hard
  to keep in sync across many doors.
- **Chose:** The student's own phone checks the fingerprint, then gives the
  terminal a short signed code. A tap takes under 0.5 s. No fingerprint ever
  leaves the phone, and the terminal stores no templates, so there is no
  enrolment limit.
- **Trade-off:** It depends on students having phones. It also trusts the
  phone's biometric check, which is why device binding, RASP and (planned)
  biometric invalidation exist. It accepts the device PIN as well as a
  fingerprint.

### D2. MFRC522 → PN532

- **Problem:** The first prototype read plastic RFID cards with an MFRC522.
  Cards are easy to lend, and the plan was to use the phone as the ID.
- **Tried:** The MFRC522 setup reads card UIDs (MIFARE). It does not hold the
  ISO 14443-4 APDU conversation that a phone doing Host Card Emulation needs.
- **Chose:** A PN532 over I²C. It can list an ISO 14443-4 target and exchange
  APDUs with it (`inListPassiveTarget` + `inDataExchange`).
- **Trade-off:** It's a different library, different wiring and a mode
  switch to get right. The old sketches and the `/attendance` RFID route are
  kept for reference only.

### D3. ~360-byte JWT in six chunks → 34-byte signed code in one exchange (2026-09-25)

- **Problem:** The phone used to broadcast a Flask JWT, about 360 bytes. The
  PN532 link was measured degrading after ~119 bytes, so the JWT went in six
  `61xx`/GET RESPONSE round-trips (~650 ms of holding still). Taps were
  unreliable.
- **Tried:** A chunked protocol with 64-byte slices. It worked on the bench
  but failed often in real taps.
- **Chose:** A purpose-built code: `student_id ‖ session_id ‖ expiry`
  (12 bytes) plus a 12-byte HMAC-SHA256, base64url-encoded to 32 characters.
  With the status word that's 34 bytes: one APDU, about 0.1 s. The terminal
  doesn't need to verify it because it only relays, and the server checks the
  HMAC. See [beacon.py](../SUAAMS/beacon.py).
- **Trade-off:** It's stateless, so it is not strictly single-use. A replay
  within the window can only re-mark the same student in the same session,
  and the unique constraint makes that harmless. A 96-bit truncated HMAC is
  far beyond brute-force reach behind a rate-limited endpoint.
  `tests/test_beacon.py` fails if the code ever outgrows one frame.

### D4. Code lifetime 3 s → 10 s (2026-09-27)

- **Problem:** At 3 s, real students were rejected.
- **Tried:** 3 s, the tightest window. A bench run measured the machine side
  at about 0.5 s on a warm server (read ~0.12 s, TLS + POST ~0.3 s, DB write
  ~0.1 s). Almost all of the remaining 2.5 s went on the student walking up
  and holding the phone steady. The clock starts at mint, before the student
  moves.
- **Chose:** 10 s. TOTP codes use 30 s, and BLE proximity beacons commonly
  use 5–30 s.
- **Trade-off:** A captured code is useful for 10 s instead of 3 s. A relay
  still needs to be within ~4 cm of the reader inside that time. 30 s was
  rejected because a code could then be walked to another terminal. Minting
  when the phone enters the RF field would allow 3 s again, but Android doesn't
  tell the app about field entry before the SELECT arrives.

### D5. Session bound at mint time

- **Problem:** The terminal doesn't know which class it is serving. The old
  submit looked up "the newest active session across all courses", so a tap
  in room A could be credited to a session in room B.
- **Tried:** Looking the session up when the terminal posts.
- **Chose:** Resolve the session when the code is minted, from courses the
  student is enrolled in, and sign it into the code. Mint and status share
  one helper so they can't disagree.
- **Trade-off:** If a student is in two overlapping active sessions, the most
  recently started one wins. A session that ends inside the window is
  re-checked at submit (`409`).

### D6. Code expiry enforced natively, not by a Dart timer

- **Problem:** A Dart `Timer` used to wipe the code. Dart timers can be
  throttled, don't fire while the app is in the background, and were skipped
  completely when the provider was disposed mid-flow. The code stayed readable.
- **Tried:** Making the Dart cleanup more careful (hoisted references,
  `ref.mounted` guards). That helped but didn't close the hole.
- **Chose:** `SuaamsHceService` stores a `SystemClock.elapsedRealtime()`
  deadline taken from the server's `expires_in`, and refuses to serve the code
  after it. The Dart countdown is now display only.
- **Trade-off:** The expiry logic is now in two languages. The Kotlin default
  (`DEFAULT_TTL_MILLIS`) must stay in step with the server.

### D7. Offline taps stored as "pending verification", not accepted

- **Problem:** If the terminal loses Wi-Fi, genuine taps would be lost.
- **Tried:** Accepting them on upload was considered. By then every code has
  expired, so accepting expired codes would make the 10 s window meaningless.
  Anyone holding an old code could then "upload" it later.
- **Chose:** The terminal queues up to 16 codes in flash (surviving power
  loss) and uploads them later. The server checks the signature only and
  stores each one as a `pending_verification` row with the tap time, which it
  works out from the code's own expiry. The terminal has no clock to trust.
- **Trade-off:** Someone has to review them, and the review screen isn't
  built yet. When the queue is full, the oldest tap is dropped.

### D8. BLE as a fallback, broadcasting from the terminal

- **Problem:** iPhones can't do card emulation (Apple only allows it in the
  EEA), and many budget Androids have no NFC.
- **Tried:** Card emulation on iOS isn't available. Phone-to-terminal BLE
  connections would open a GATT surface on the terminal.
- **Chose:** The terminal advertises a rotating, HMAC-signed code every 5 s.
  It is non-connectable, so nothing can connect to it. The phone hears the
  code and submits it over its own logged-in connection. Each attendance row
  records `method`.
- **Trade-off:** BLE codes are not bound to the phone that heard them, so
  someone in the room can relay one to an absent friend within ~10 s. That
  friend still needs their own bound phone, fingerprint and login. NFC
  doesn't have this hole, so NFC stays the default.

### D9. RSSI never decides acceptance

- **Problem:** It's tempting to use signal strength to prove "close enough".
- **Chose:** RSSI is only logged and used for the "move closer" hint.
- **Trade-off:** The phone reports RSSI, so a modified client could send any
  number. Trusting it would add a check that looks like security but proves
  nothing.

### D10. The terminal keeps the server warm itself

- **Problem:** Render's free tier sleeps and took **8.5 s** to wake in a
  measurement. A tap during a cold start is always rejected.
- **Tried:** An external uptime pinger was considered. It needs another
  account and is easy to forget when the demo moves.
- **Chose:** The terminal pings `/healthz` at boot, every 4 minutes when no
  phone is in the field, and right before a POST if the server hasn't been
  confirmed warm in the last 60 s.
- **Trade-off:** It uses some terminal time and network. A paid tier would
  remove the problem.

### D11. Secrets have no defaults; missing means off or won't start

- **Problem:** The original `os.environ.get(NAME, '<literal>')` code put the
  production DB password and signing keys in git. It also meant the
  "missing variable" check could never fire.
- **Chose:** `_require_env()` refuses to start without DB/session/JWT
  secrets. Check-in secrets (`BEACON_SIGNING_SECRET`, `TERMINAL_*`,
  `BLE_BEACON_SECRET`) are checked where they are used. If one is missing,
  that feature is off and the reason is logged.
- **Trade-off:** Setting up locally takes more steps. The old values are
  still in git history and must be treated as burned.

### D12. Device binding works in both directions

- **Problem:** "One account per phone" alone still let one phone bind several
  classmates' accounts. Its owner could then check them all in with one
  finger. Also, a phone that couldn't read its ID used to send a shared
  placeholder, which made every such phone look like the same device.
- **Chose:** `students.device_id` is unique. Login returns `DEVICE IN USE` for
  a second account and `DEVICE UNVERIFIED` for known placeholder strings. The
  app never sends a placeholder.
- **Trade-off:** A student with a new or reset phone needs an admin to unbind
  the old one. Android ID changes on factory reset.

### D13. Campus time for timetables, UTC for moments (2026-10-08)

- **Problem:** Render runs in UTC, an hour behind Lagos, so every late cutoff
  was an hour off.
- **Chose:** Times on the timetable are campus wall-clock time (Africa/Lagos).
  Moments are stored in UTC and converted for display.
- **Trade-off:** Two kinds of time in the code, and you have to know which one
  a field is.

### D14. BLE broadcasts nothing until NTP time is known

- **Problem:** A BLE slot is Unix time ÷ 5. Before NTP, the ESP32 thinks it is
  1970.
- **Chose:** The terminal stays silent until the clock is past Nov 2023. It
  also runs a known-answer self-test at boot and refuses to broadcast if its
  HMAC doesn't match the server's reference vector.
- **Trade-off:** BLE is unavailable for the first few seconds after boot.
  Silence is easier to diagnose than codes that never work.

### D15. Huge APP partition, no OTA

- **Problem:** BLE + Wi-Fi + HTTPS no longer fit the default 1.2 MB app
  partition.
- **Chose:** The "Huge APP (3MB No OTA)" partition scheme.
- **Trade-off:** No over-the-air firmware updates. Every update needs a USB
  cable.

### D16. Terminal verifies TLS with the whole CA bundle, not a pinned root (2026-10-09)

- **Problem:** The firmware used `setInsecure()`. Anyone on the venue Wi-Fi
  could pose as the server and collect `X-Terminal-Secret`, then submit their
  own codes from anywhere.
- **Tried:** Pinning Render's root certificate was considered. Render issues
  from Google Trust Services and also Let's Encrypt, and the terminal has no
  OTA (D15). A pin that Render later moved away from would break every
  terminal until each one was reflashed by hand.
- **Chose:** `useBuiltinCACertBundle()` (Mozilla's root list in the esp32
  3.x core). It checks the chain and hostname. A rejected certificate looks
  like a transport failure, so the tap goes to the offline queue rather than
  being lost.
- **Trade-off:** It trusts any public CA, not just Render's. Certificate
  dates aren't checked because the core has no time support, so an unsynced
  clock can't break check-in. It also requires board package 3.x.
