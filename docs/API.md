# API Reference

The JSON endpoints that the mobile app and the terminal call. The web dashboards
(`blueprints/`) are server-rendered pages, not an API. They are listed at the
end for completeness.

- **Base URL (production):** `https://suaams.onrender.com`
- **App base path:** `/api/v1` (see
  [api_constants.dart](../SUAAMS_Mobile/suaams/lib/core/constants/api_constants.dart))
- **Auth types:**
  - **JWT**: `Authorization: Bearer <access token>`. Access tokens last
    30 min.
  - **JWT-refresh**: `Authorization: Bearer <refresh token>`. Refresh tokens
    last 14 days and rotate.
  - **Terminal**: `X-Terminal-Id` + `X-Terminal-Secret` headers.
  - **None**.
- **Rate limits** are per user for JWT routes and per IP otherwise.
- Errors come back as `{"error": "..."}`. Check-in errors are deliberately
  vague about *which* check failed.

---

## Check-in

### `POST /api/v1/student/checkin/beacon`: mint NFC code
- **Caller:** app, after the fingerprint check. **Auth:** JWT (student). **Limit:** 10/min.
- **Request:** no body.
- **200:** `{"success": true, "beacon_token": "<32 chars>", "expires_in": 10}`
- **403** not a student · **404** no active session for you · **503** `BEACON_SIGNING_SECRET` not set

### `POST /api/v1/student/checkin`: submit NFC code
- **Caller:** terminal. **Auth:** Terminal. **Limit:** 30/min per IP.
- **Request:** `{"beacon_token": "<32 chars>"}`
- **200:** `{"success": true, "message": "Attendance recorded successfully.", "student": {"id", "full_name"}}`
  This is also returned with `"Attendance already marked"` for a repeat, so a retry is safe.
- **401** bad terminal, or invalid/expired code · **400** missing token or not enrolled · **404** student/session gone · **409** session has ended

### `GET /api/v1/student/checkin/status`: did my tap land?
- **Caller:** app, polled about once a second for up to 25 s. **Auth:** JWT (student). **Limit:** 30/min.
- **200:** `{"success": true, "checked_in": true|false, "reason"?: "no_active_session"|"not_enrolled", "course_code"?}`
  `checked_in: false` with no `reason` means "not yet", so keep polling.

### `GET /api/v1/student/checkin/methods`: which channels are on
- **Caller:** app. **Auth:** JWT.
- **200:** `{"success": true, "nfc": bool, "ble": bool}`. This reflects only what the server has configured.

### `POST /api/v1/student/checkin/ble`: Bluetooth check-in
- **Caller:** app. **Auth:** JWT (student). **Limit:** 10/min.
- **Request:** `{"payload": "<28 hex chars = 14 bytes>", "rssi": -70}` (`rssi` is optional and only logged)
- **200:** `{"success": true, "message": "...", "course_code": "..."}`. A single definite answer, so no polling.
- **400** payload not hex · **401** `{"reason": "invalid_code"}` (forged, malformed or old) · **404** `{"reason": "no_active_session"}` · **503** BLE disabled

### `POST /api/v1/student/checkin/backlog`: offline taps
- **Caller:** terminal. **Auth:** Terminal. **Limit:** 30/min per IP. **Max** 50 records.
- **Request:** `{"records": [{"beacon_token": "..."}, ...]}`
- **200:** `{"success": true, "accepted": n, "received": n, "results": [{"beacon_token", "status": "pending_verification"|"superseded"|"rejected", "reason"?, "captured_at"?, ...}]}`
- Creates rows in `offline_checkin_logs` and **never** in `attendance`.

### `GET /healthz`
- **Caller:** terminal keep-warm ping. **Auth:** none. **200:** `{"status": "ok"}`. It doesn't touch the database.

---

## Auth (`/api/v1/auth`)

| Method | Path | Auth | Limit | Request → Response |
|---|---|---|---|---|
| POST | `/login` | none | 5/min/IP | `{username, password, device_id}` → `{success, token, refresh_token, user: {id, username, role, requires_password_change}}`. 403 with `SECURITY LOCK` / `DEVICE IN USE` / `DEVICE UNVERIFIED` for students (see [ARCHITECTURE §5](ARCHITECTURE.md#5-login-and-device-binding)) |
| POST | `/change-password` | JWT | 5/min | `{new_password}` |
| POST | `/refresh` | JWT-refresh | 10/min | → `{success, token, refresh_token}`. The old refresh token is now dead |
| POST | `/logout` | JWT-refresh | 10/min | Revokes the refresh token |

## Student (`/api/v1/student`), all JWT with role student

| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard` | Summary stats |
| GET | `/schedule/today` | Today's classes with live status |
| GET | `/schedule/week` | Weekly timetable |
| GET | `/course/<course_id>/history` | Per-session attendance for one course |
| GET | `/courses/available` | Courses open for registration this semester |
| POST | `/courses/<course_id>/register` | Register (10/min) |
| POST | `/courses/<course_id>/drop` | Drop (10/min) |
| GET | `/announcements` | Announcements that apply to this student |
| PATCH | `/announcements/seen` | `{announcement_id}`: mark as seen |
| GET | `/notifications` | In-app notifications |
| POST | `/notifications/<id>/read` | Mark read |
| POST | `/device-token` | `{fcm_token, platform}`: register for push |
| GET | `/device-info` | Bound-device status (read-only; unbinding is admin-only) |

## Lecturer (`/api/v1/lecturer`), JWT with role lecturer or hod

| Method | Path | Purpose |
|---|---|---|
| GET | `/dashboard` | Courses + today |
| GET | `/schedule/week` | Weekly teaching schedule |
| GET | `/course/<course_id>` | Course workspace |
| POST | `/course/<course_id>/start-session` | `{planned_start?: "HH:MM", planned_end?: "HH:MM"}` (10/min) |
| POST | `/course/<course_id>/end-session` | End the active session (10/min) |
| GET | `/course/<course_id>/history` | Past sessions |
| GET | `/course/<course_id>/session/<session_id>` | Who attended, live or past |
| POST | `/course/<course_id>/session/<session_id>/mark-present` | Mark an enrolled student present by hand (60/min). Stored as `method = manual` with `marked_by` |
| GET | `/course/<course_id>/analytics` | Attendance rates |
| GET | `/course/<course_id>/export` | CSV register |
| GET | `/announcements` | Own announcements |
| POST | `/course/<course_id>/announcements` | Post (pushes to enrolled students) |
| DELETE | `/announcements/<announcement_id>` | Delete |

## Legacy hardware routes (no `/api/v1` prefix)

These are kept for the old MFRC522 RFID prototype, which hardcoded these paths.

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/attendance` | Terminal | `{RFID_UID}`. Marks the newest active session, `method = rfid`. Delete it if the RFID path is truly retired |
| GET | `/sessions/active` | Terminal | Lists active sessions. No current client calls it |
| GET | `/sessions/active/<course_id>` | Terminal | Active session for one course. No current client calls it |

## Web dashboards (session cookie, not JSON)

`/login`, `/change-password`, `/logout` · `/admin/...` (organisation,
lecturers, hods, students + bulk-enrol + unbind, courses, semesters,
timetable, announcements, reports) · `/lecturer/...` · `/hod/...` ·
`/student/...`. See [FEATURE_MAP.md](FEATURE_MAP.md) for which file holds
each page.
