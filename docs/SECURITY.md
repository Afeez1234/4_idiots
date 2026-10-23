# Security and Threat Model

What SUAAMS defends against, how, and where the defences stop. The
coding rules that keep these defences intact are in
[CLAUDE.md](../CLAUDE.md). This file holds the reasoning.

---

## 1. What we are protecting

The thing that matters is the **attendance record**: a row saying student X
was present at session Y. Every attack on SUAAMS comes down to creating a row
that isn't true, usually for an absent friend. Secondary assets are accounts
(passwords, tokens), the signing secrets, and student personal data.

## 2. Trust boundaries

| Party | Trusted for | Not trusted for |
|---|---|---|
| Server | Everything; it is the only party that verifies | — |
| Terminal | Being physically at the door, relaying what it read | Deciding anything. It never verifies a code |
| App (unmodified) | Running the fingerprint check before minting/scanning | Anything it *reports*: RSSI, device ID, the fact a fingerprint passed |
| Phone OS | Biometric result, hardware-backed storage | Itself, if rooted/jailbroken (hence RASP) |
| Network | Nothing | — |

## 3. Threats and defences

| # | Threat | Defence | Where |
|---|---|---|---|
| T1 | **Buddy punching**: friend uses your phone to check in | Fingerprint/PIN before any code is minted or scanned | `nfc_provider.dart` `_verifyIdentity` |
| T2 | **Your account on a friend's phone** | Account bound to first phone; other phones get `SECURITY LOCK`; the bound phone gets a push alert | `api/auth.py` `mobile_login` |
| T3 | **Several accounts on one phone** | `students.device_id` unique; `DEVICE IN USE` | `api/auth.py`, `models.py` |
| T4 | **Shared placeholder device ID** | App never sends one; server rejects known placeholders (`DEVICE UNVERIFIED`) | `auth_provider.dart`, `api/auth.py` |
| T5 | **Relay / replay of an NFC code** | 10 s expiry; bound to one student + one session; ~4 cm NFC range | `beacon.py` |
| T6 | **Forged code** | HMAC-SHA256 (96-bit truncated), constant-time compare, vague error messages | `beacon.py`, `api/student.py` |
| T7 | **Fake terminal posting codes** | `X-Terminal-Id` / `X-Terminal-Secret`, constant-time compare, fail closed if unset. The terminal verifies the server's TLS certificate, so the secret can't be lifted by impersonating the server on the venue Wi-Fi | `api/student.py` `_check_terminal_auth`, `SUAAMS_HCE.ino` `useVerifiedTls` |
| T8 | **Tap credited to the wrong class** | Session fixed at mint time | `api/student.py` `_active_session_for_student` |
| T9 | **Double marking** | Unique `(student_id, session_id)` on `attendance` | `models.py` |
| T10 | **Rooted / hooked phone faking the fingerprint result** | freeRASP check at startup; check-in refused if compromised. Runs *before* the biometric prompt. In release builds it also checks the app is signed with the project's release certificate (`signingCertHashes`), so a repackaged APK with the fingerprint check removed is refused | `security_service.dart`, `android/app/build.gradle.kts` |
| T11 | **Code left readable after the window** | Native monotonic deadline in the HCE service | `SuaamsHceService.kt` |
| T12 | **Uploading old codes as "offline" taps** | Backlog rows are `pending_verification`, never attendance until the course lecturer accepts them (`method = offline`, under their name). The terminal sends each tap's read time; a token read more than 15 s after it was made is rejected outright, so "Accept all" never sees a replay. Gap: a terminal that booted with no network has no clock, and its taps are reviewed as before | `api/student.py` `sync_offline_checkin_backlog` |
| T13 | **Forged / relabelled BLE code** | HMAC over terminal number + slot with domain prefix | `ble_beacon.py` |
| T14 | **Password guessing** | bcrypt; 5/min login limit per username plus 200/min per address; forced first-login change, which refuses the username or current password as the new one | `api/auth.py`, `blueprints/auth.py` |
| T15 | **Stolen refresh token** | Rotation on every refresh; single current `jti` per user; logout revokes | `api/auth.py`, `users.current_refresh_jti` |
| T16 | **Leaked secrets** | No defaults; server won't start without core secrets; `.env`, `secrets.h`, Firebase key gitignored | `app.py`, `.gitignore` |
| T17 | **Web CSRF** | Flask-WTF on dashboard forms | `extensions.py` |
| T18 | **Untraceable admin changes** (several people sharing one admin login) | Personal admin logins; every dashboard change, admin sign-in and failed admin sign-in is recorded with the person's name; the log is read-only in the app | `create_admin.py`, `audit.py`, `/admin/activity` |
| T19 | **Temporary passwords left in place** | Web requests are refused until the password is changed; disabled accounts are signed out at once | `blueprints/auth.py` `enforce_account_state` |
| T20 | **Departed staff or removed students still signing in** | Status: anything but active turns the login off and revokes the refresh token; every app and web request re-checks the account, so it is refused at its next request (not when its token expires); student exits release the phone binding; changes are audited with a reason | `people_status.py`, `api/auth.py` `install_account_check`, `/refresh` |
| T21 | **Hidden text in an imported timetable PDF** | Only letters with ink under them are read; every import is previewed and saved as a draft until published | `timetable_pdf.py`, `timetable_import.py` |
| T22 | **Checking in to a session left open from an earlier day** (the lecturer forgot to press End) | Check-in only resolves and accepts sessions dated today on campus; the terminal submit refuses a token bound to an older one. Such sessions are also closed automatically (`utils.close_stale_sessions`), so they stop showing as live | `api/student.py` `_active_session_for_student`, `submit_checkin_beacon` |
| T24 | **Checking in at a reader in another room** (tapping in from a different lecture hall, or hearing another hall's Bluetooth code) | Each reader has a room; a check-in for a class in another room is marked `wrong_room` for the lecturer (`ROOM_CHECK=flag`, the default) or refused (`enforce`). The class's room is the one given at start, else its timetable slot's | `terminal_rooms.py`, `api/student.py` |
| T25 | **One dumped reader exposing every reader's secret** | Each reader has its own secret (only its SHA-256 is stored), which can be replaced or the reader disabled on the Terminals page; a disabled reader is refused even with the old shared secret, and its Bluetooth codes are refused too (they verify against the shared Bluetooth secret, so without this a disabled board's codes were accepted unflagged). A board that is actually lost also holds the shared `BLE_BEACON_SECRET`: rotate it on the server and every reader | `models.Terminal`, `terminal_rooms.authenticate`, `terminal_rooms.ble_reader_disabled`, `/admin/terminals` |
| T26 | **Someone with your unlocked phone setting a password of their own** (then using it on the web portal, which has no device binding) | A password change from the app's Profile needs the current password; only the forced first change skips it | `api/auth.py` `/change-password` |
| T23 | **A stolen or handed-on phone still receiving someone's notifications** | Push tokens are removed on logout, on an admin unbind, and when Status switches a login off; the app registers again at its next login | `api/auth.py` `/logout`, `blueprints/admin.py` `reset_student_binding`, `people_status.py` |

## 4. Known gaps (honest list)

Keep this list current. A gap you can name is worth far more in a defence than
one an examiner finds.

| Gap | Impact | Status / mitigation |
|---|---|---|
| **Biometric invalidation not built** | A student can add a friend's fingerprint to their phone, let the friend check in, then delete it | Planned: bind to the current biometric set (`invalidateByBiometricEnrollment` / `BiometryCurrentSet`) |
| **Device PIN accepted** | `local_auth`'s prompt allows the PIN as a fallback, so anyone who knows the PIN passes the "fingerprint" step | The same planned fix (a key bound to the biometric set) would tighten it |
| **BLE code relay** | Someone in the room can pass a code to an absent friend within ~10 s | Accepted; BLE is fallback only; `method` recorded on every row |
| **One shared terminal secret** | Dumping one board's flash exposes the secret every terminal uses | Fine for one terminal; per-terminal secrets needed at scale |
| **Terminal doesn't check certificate expiry** | The ESP32 core is built without time support, so it checks the certificate chain and hostname but not the dates | Chain + hostname is what stops an impostor; accepted so an unsynced clock at boot can't break check-in |
| **Stateless NFC code** | Not strictly single-use inside its 10 s | Harmless: replay can only re-mark the same student/session |
| **Rate limiter is in-memory** | Limits are per worker process and reset on restart | Set a Redis `storage_uri` if scaled past one worker (see `extensions.py`) |
| **Device ID can change** | Android ID changes on factory reset; iOS `identifierForVendor` changes if the app is uninstalled. That student then needs an admin unbind | Accepted; failure is safe (locks out, doesn't let in) |
| **Old credentials in git history** | DB password and signing keys from before the env-var fix are public | Treat as burned; rotate if not already done |
| **Manual marking trusts the lecturer** | A lecturer can mark any enrolled student present without them being there | By design: limited to the lecturer's own courses, recorded as `method = manual` with `marked_by`, and never overwrites a real check-in |
| **iOS BLE untested** | Unknown | Needs an iPhone test |
| **Default first passwords are guessable** | Accounts still on "Pending Setup" can be signed into with the matric number or staff ID | Forced change at first sign-in; random first passwords under consideration |

## 5. Secrets inventory

| Secret | Lives in | If missing |
|---|---|---|
| `SECRET_KEY`, `JWT_SECRET_KEY` | Server env | Server won't start |
| `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | Server env | Server won't start |
| `BEACON_SIGNING_SECRET` | Server env | NFC check-in off (mint returns 503) |
| Per-reader code + secret | Terminals page (hash only) **and** that reader's `secrets.h` | That reader's posts rejected (401) |
| `TERMINAL_ID`, `TERMINAL_SECRET` (old shared pair, changeover only) | Server env **and** terminal `secrets.h` | Readers not yet moved over are rejected (401) |
| `BLE_BEACON_SECRET` | Server env **and** terminal `secrets.h` (must match) | BLE off; app hides it |
| Wi-Fi SSID/password | Terminal `secrets.h` | Terminal runs offline, queues taps |
| `firebase-service-account.json` | `SUAAMS/` (gitignored) | No push; notifications are still saved in-app |

Generate secrets with
`python -c "import secrets; print(secrets.token_urlsafe(32))"`.
