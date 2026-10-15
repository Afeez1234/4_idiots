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
  switch to get right. The old sketches are kept for reference only; the
  server's `/attendance` RFID route was removed on 2026-10-12.

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
- **Trade-off:** Someone has to review them: the course lecturer does, on
  the session page (built 2026-10-12). When the queue is full, the oldest
  tap is dropped.

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

### D17. Bulk uploads: batched inserts and a cheap hash for default passwords (2026-10-12)

- **Problem:** Uploading a CSV of students returned a 502. Each row cost
  about 6 database round trips plus a bcrypt hash at cost 12 (~0.3 s on a
  PC, roughly 3 s on Render's free tier). Past about 10 students the request
  outlived gunicorn's 30 s limit and was killed, freezing the site for
  everyone while it ran.
- **Tried:** Raising the timeout alone. That only makes the site freeze for
  longer: a 500-student upload would block the single worker for ~25 minutes.
- **Chose:** Validate every row in memory against three up-front lookups,
  then insert in bulk, so round trips no longer grow with the file. Hash the
  *default* passwords at bcrypt cost 4 (~1 ms). Cap uploads at 1,000 rows.
  1,000 students now take ~1.3 s on a PC.
- **Trade-off:** A default password is the student's own matric number, which
  is printed on their ID card and in the CSV. A slow hash can't protect a
  password that's already known; the forced change at first sign-in is the
  protection, and the new password is hashed at full cost (12). Accounts
  created one at a time on the form keep cost 12. The upload is now
  all-or-nothing: a failure saves none of the file, rather than part of it.

### D18. Timetables imported from Student Affairs PDFs, with an ink check (2026-10-13)

- **Problem:** About 20 departments x 5 levels, each with its own weekly
  sheet. Entering every class by hand on the admin page wasn't feasible.
- **Tried:** Reading the PDF's text layer alone. The real sheets contain text
  that isn't visible: drawn in white, or invisible. A text-only reader
  imported classes nobody can see on the printed sheet.
- **Chose:** `pdfplumber` for the words and their positions, plus a render of
  the page (`pypdfium2`) to keep only letters with ink under them. One
  landscape page per sheet; other layouts are refused rather than guessed.
  The test fixture is a generated look-alike, so no real lecturer names are
  in the public repo.
- **Trade-off:** It's tied to Student Affairs' current layout. A new layout
  means updating the reader. Rendering costs about 0.7 s per sheet, so an
  upload is capped at 10 sheets.

### D19. Drafts, then Publish, then notify only who changed (2026-10-13)

- **Problem:** An import that went live row by row would leave students
  looking at half a timetable. And notifying everyone on every correction
  trains people to ignore notifications.
- **Chose:** Imports save drafts that only admins see. Publish swaps a
  course's drafts in for its published classes in one transaction. Then each
  person whose classes actually changed gets one notification listing their
  new times; a course re-published identically notifies nobody. Hand edits
  of published classes use the same rule.
- **Trade-off:** One more step (Publish) for the admins. The notification
  lists the new schedule, not a diff, which is longer but is what students
  need.

### D20. A course's level read from its code, not a new column (2026-10-13)

- **Problem:** The timetable page needs to filter by level, but courses have
  no level field; only students do.
- **Tried:** A `Course.level` column was considered. It needs a migration and
  every existing course filled in by hand.
- **Chose:** The first digit of the code is the level (MCT401 -> 400), which
  every code the school issues follows. Codes without one go under "Other".
- **Trade-off:** A course code that breaks the convention lands in the wrong
  level. If that happens, a real column is a cheap change later.

### D21. Copy "same semester last year", not "last semester" (2026-10-13)

- **Problem:** Re-entering a timetable every semester is wasteful when most
  classes repeat.
- **Tried:** Copying the previous semester. First and second semesters run
  different courses, so it would match almost nothing.
- **Chose:** The default source is the same-named semester a year earlier.
  It goes through the import's preview and checks, and a course that no
  longer exists is noted instead of blocking the copy.
- **Trade-off:** Courses are rows per semester, so they must exist in the new
  semester (by code) before their classes can be copied.

### D22. Status, never delete (2026-10-13)

- **Problem:** Nobody could be switched off: a lecturer who had left, or an
  expelled student, could still sign in. Deleting them would cascade away
  attendance and results.
- **Chose:** A status on students and lecturers. Anything but active turns
  the login off and revokes the refresh token. Student exits release the
  phone binding. A lecturer can't be marked Left while coordinating a running
  course, because a course must always have a coordinator.
- **Trade-off:** An app already signed in kept a valid access token for up
  to 30 minutes after being switched off. Closed on 2026-10-15: every app
  request now re-checks the account (one primary-key lookup), as the web
  already did.

### D23. Promotion: one button, once a year, undoable, never auto-graduates (2026-10-14)

- **Problem:** A student's level was typed at enrolment and never changed, so
  rosters and HOD reports drifted every year.
- **Tried:** Promoting automatically when a semester is activated. Semesters
  are activated twice a year and sometimes re-activated by mistake, which
  would promote twice.
- **Chose:** An explicit action with a preview, guarded to once per academic
  year (`promotion_runs.academic_year` is unique), runnable in a few bulk
  UPDATEs, and undoable. Final-year students are only listed as due to
  graduate, because carry-overs are common.
- **Trade-off:** Someone has to remember to run it each session. Graduating
  is a second step.

### D24. Lecturer and course uploads block on any error; the student upload skips (2026-10-13)

- **Problem:** Two upload styles now exist and look inconsistent.
- **Chose:** Lecturer and course uploads show a preview and refuse the whole
  file if any row has an error. Rows that already exist are skipped, not
  errors, so re-uploading is harmless. A half-saved course file (some
  courses created, their co-lecturers not) is harder to repair than a
  rejected one.
- **Trade-off:** The older student upload still saves good rows and skips
  bad ones. Bringing it in line is a small change if it ever confuses
  anyone.

### D25. Edit anything; delete only what has no history (2026-10-14)

- **Problem:** A course code or name typed wrong could not be fixed. The only
  delete was a whole department, which would take every student and course
  in it.
- **Chose:** Courses, lecturers and students can always be edited. A staff
  ID or matric number is the login username, so the login moves with it,
  and a password still at its default becomes the new ID. Delete is allowed
  only when nothing has happened yet: no sessions or results for a course;
  no coordinated course, class run, mark, announcement or result for a
  lecturer; no attendance, offline tap or result for a student. Anything
  with history is refused with the reason, and Status (D22) is the way out.
- **Trade-off:** A course that ran one test session can't be deleted, only
  edited. A type-the-name confirmation like faculty deletes would allow it,
  but would also let one click wipe a semester's attendance.
- **HODs:** "Remove as HOD" instead of delete. A promoted lecturer shares
  one login with their lecturer record, so removal sets the role back to
  lecturer, and an edit on either page is copied to the other. An HOD
  created directly loses the account, unless it has something on record, in
  which case sign-in is switched off and the account kept. Changing a
  department's HOD is remove, then assign, not a one-step swap.

### D26. The dashboard answers "is today's teaching happening?" (2026-10-14)

- **Problem:** The dashboard showed totals and an all-time department rate.
  It couldn't say whether the 10:00 class had started. The department rate
  also multiplied a department's total sessions by its total enrollments,
  so it ran far too low.
- **Chose:** Today's published slots matched to sessions, by
  `sessions.timetable_id` (now set when a class starts) or, for older
  sessions, by course and `planned_start`. A class is late 30 minutes after
  its start with no session, and missed once its end passes. Reminders are
  a manual button that notifies every lecturer on the course; the audit
  entry doubles as the "Reminded at" record, so no new table. Department
  rates are summed per course over the active semester only.
- **Trade-off:** No automatic reminders: that belongs with the scheduler on
  the roadmap, and a wrong automatic nag to a lecturer on a cancelled day is
  worse than none. Sessions started before this change, outside the
  timetable or with typed times, match no slot, so their class can show as
  missed while the session itself counts as live.

### D27. Analytics: the register's eligibility rule, and delivery from teaching start (2026-10-14)

- **Problem:** Exam eligibility could only be seen one course at a time,
  and nothing showed which timetabled classes never ran.
- **Chose:** Eligibility uses exactly the course register CSV's rule
  (finished sessions, present or late), so the page and the register a
  lecturer downloads can't disagree. A course is only checked after 3
  classes: after one, a single absence reads as 0%. Delivery counts each
  published slot once a week from the first class anyone ran this semester,
  not the semester's start date, because teaching starts a week or two
  after registration opens.
- **Then (2026-10-15):** a slot added or moved mid-semester was counted as
  missed back to week 1. Slots now carry `effective_from`, set when they're
  published or their course, day or time is edited. A re-published sheet
  that keeps a class's course, day and times keeps its date and sessions,
  so fixing a room on a re-issued sheet doesn't reset a course's history.
- **Trade-off:** Public holidays and cancelled classes aren't recorded, so
  they count as missed. (The student dashboard's different percentage,
  noted here at first, was fixed by D30.)

### D28. Offline taps carry the terminal's read time; late reads are rejected (2026-10-14)

- **Problem:** The live path rejects a token older than 10 s. The offline
  path accepted any correctly signed token for review, dated by when it was
  made, because the terminal was thought to have no clock. So a token kept
  and replayed while the terminal was offline reached "Accept all". The
  queue also held only 16 taps, and one malformed token or a read timeout
  could clear all of it.
- **Chose:** The terminal already syncs its clock for the Bluetooth codes,
  so it now sends each tap's read time. A read more than 15 s after the
  mint (the app's 10 s serving window plus clock drift) is rejected at
  upload, never shown for review. The read time becomes the tap time. The
  queue holds 100, uploads 25 per request, and only ever removes the chunk
  the server answered for. The reader refuses anything but a 32-character
  base64url token.
- **Trade-off:** A terminal that booted with no network has no synced
  clock, so its taps are reviewed as before. Firmware not yet reflashed
  sends no read time and behaves as before.

### D29. Phone pushes are sent after the request answers (2026-10-15)

- **Problem:** Check-in saved the attendance, then sent the "Attendance
  Recorded" push and waited for Firebase before answering the terminal.
  The terminal reads one student at a time, so every student waited for
  the previous one's push: ~0.3-0.5 s each, 1-1.7 extra minutes for a
  200-student hall, most of the "under 2 minutes" the design promises.
- **Chose:** The in-app notification row is still saved in the request.
  The phone push goes to a 2-thread pool and runs after the request
  answers. Nothing depends on the push arriving: the app confirms a tap by
  asking the server (`/checkin/status`). Every caller benefits, including
  announcements and timetable publishes.
- **Trade-off:** A push still queued when a worker restarts (a deploy) is
  lost; the in-app notification isn't. Tests run pushes inline (Flask's
  TESTING flag) so they can check what was sent.

### D30. One attendance rule, the register's, everywhere (2026-10-15)

- **Problem:** Eight places computed an attendance percentage, with three
  rules: all sessions or finished only; every attendance row or present
  and late. For one student, the app showed 60%, the HOD page 40% and the
  register 50%. The admin Reports page also ran three queries per course.
- **Chose:** The course register's rule, since it decides exam
  eligibility: a class counts as held once it has finished, and present or
  late counts as attended. It lives once in `utils.py` (`held_sessions`,
  `attended_by_course`, `attended_by_student`, `course_attendance`), each a
  grouped query for any number of courses. The student app and web, HOD
  pages, lecturer pages (web and app), admin Reports, the dashboard's
  department rates and Analytics all call it.
- **Trade-off:** Numbers people have already seen change slightly: a class
  now counts only once it ends, and an excused mark no longer counts as
  attended (none are written today). The app's JSON field names are
  unchanged.

### D31. A dedicated Android release key, set once (2026-10-15)

- **Problem:** Release builds were signed with the build machine's debug
  key, and freeRASP's expected certificate was a placeholder. Every release
  build therefore failed the integrity check and refused check-in; debug
  builds only logged it, so nobody noticed. The debug keystore's password
  is public, so it couldn't protect anything anyway.
- **Chose:** A release keystore (`android/suaams-release.jks`, RSA 2048,
  10,000 days) with its password in `android/key.properties`, both kept
  out of git and backed up by the project lead. Its SHA-256 is freeRASP's
  `signingCertHashes`. A release build without the key now fails, rather
  than falling back to the debug key. Done before any real student bound a
  phone, because Android scopes `ANDROID_ID` to the signing key.
- **Trade-off:** Lose the key and the app can never be updated in place,
  and a new key re-binds every student. Phones with an older debug-signed
  build must uninstall it before installing a release build.
