from flask import Blueprint, request, jsonify, current_app
import hmac
import os
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt,
)
from datetime import date, datetime, timezone

# Import db and our elegant SQLAlchemy models
# (added Enrollment here for the check-in endpoints, Timetable for the
# today's-schedule endpoint below)
from models import db, Student, Course, Session as SessionModel, Attendance, Enrollment, Timetable, DeviceToken, Notification, Semester, Announcement, OfflineCheckinLog
from extensions import limiter, jwt_identity_or_ip, api_error_response
from push_notifications import send_push_notification
from utils import compute_attendance_status
# Compact HCE beacon minting/verification. See beacon.py for why the
# credential is a 32-char signed handle rather than a ~360-byte JWT.
from beacon import (
    mint_beacon, verify_beacon, verify_beacon_signature, BeaconError,
    BEACON_TOKEN_TTL_SECONDS,
)
# Rotating Bluetooth codes, the fallback for phones that can't tap in.
import ble_beacon

# Create the API blueprint for student mobile endpoints
api_student_bp = Blueprint('api_student', __name__, url_prefix='/api/v1/student')

# Cap on a single offline backlog batch. The terminal's own flash queue is
# the real bound (see MAX_OFFLINE_QUEUE in SUAAMS_HCE.ino); this is a second
# line of defence so a malfunctioning or compromised terminal can't turn
# the endpoint into a bulk-insert DoS against the attendance DB.
MAX_OFFLINE_BACKLOG_BATCH = 50


def _check_terminal_auth():
    """Validate the ESP32 terminal's shared secret.

    The submit endpoint is unauthenticated by design -- the terminal has no
    login session, it just relays what it physically read. But that left it
    completely open: without this check, any client that could reach the URL
    could POST a (stolen or minted) beacon and record anyone's attendance.

    This is a shared-secret header check, not a signature. It authenticates
    the terminal rather than the request, so a captured secret could be
    replayed -- which is why it only meaningfully helps alongside real TLS.
    The firmware currently uses client.setInsecure(), so treat this as
    attribution plus a meaningful hurdle, not as a complete fix. Pinning a
    CA bundle on the ESP32 is the follow-up.

    Fails closed when unconfigured, for the same reason as
    BEACON_SIGNING_SECRET: a missing secret must disable the route, not
    silently authenticate everyone.
    """
    expected_id = os.environ.get("TERMINAL_ID", "").strip()
    expected_secret = os.environ.get("TERMINAL_SECRET", "").strip()
    if not expected_id or not expected_secret:
        current_app.logger.error(
            "TERMINAL_ID/TERMINAL_SECRET not configured; rejecting terminal check-in."
        )
        return False

    supplied_id = request.headers.get("X-Terminal-Id", "")
    supplied_secret = request.headers.get("X-Terminal-Secret", "")

    # Constant-time on the secret so a wrong value can't be discovered a
    # byte at a time from response timing.
    if not hmac.compare_digest(supplied_secret, expected_secret):
        return False
    return hmac.compare_digest(supplied_id, expected_id)


def _active_session_for_student(student):
    """The active session this student should be checked into, or None.

    Scoped to courses the student is actually enrolled in. Both the mint
    endpoint and the confirmation-status endpoint resolve the session
    through this one helper, because they MUST agree: mint binds a
    session_id into the token, and if status then looked up a different
    session, the student's attendance would land correctly while the app
    polled forever and never showed confirmation. Keeping the resolution
    in a single function is what stops those two drifting apart again.

    Where a student is enrolled in two concurrently-running sessions we
    take the most recently started -- same tie-break as before, minus the
    "across all courses" behaviour that could target a course they weren't
    enrolled in.
    """
    return (
        SessionModel.query
        .join(Enrollment, Enrollment.course_id == SessionModel.course_id)
        .filter(
            Enrollment.student_id == student.id,
            SessionModel.is_active.is_(True),
        )
        .order_by(SessionModel.id.desc())
        .first()
    )

@api_student_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_student_dashboard():
    # 1) Get the user ID and claims from the JWT token
    current_user_id =int(get_jwt_identity())
    claims = get_jwt()
    
    # Security Check: Ensure only students can access this endpoint
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        # 2) Fetch the student record using ORM
        student = Student.query.filter_by(user_id=current_user_id).first()
        
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        # 3) Count enrollments using our new direct relationship!
        enrollment_count = len(student.courses)

        course_breakdown = []
        attended_sessions_count = 0
        total_sessions_count = 0

        # 4) Iterate through the enrolled courses cleanly without raw SQL JOINs
        for course in student.courses:
            # Count all active sessions for this course
            total_sessions = SessionModel.query.filter_by(course_id=course.id).count()

            # Count attended sessions using an ORM join
            attended_sessions = Attendance.query.join(SessionModel).filter(
                SessionModel.course_id == course.id,
                Attendance.student_id == student.id
            ).count()

            total_sessions_count += total_sessions
            attended_sessions_count += attended_sessions

            # Calculate the percentage safely
            pct = round((attended_sessions / total_sessions * 100) if total_sessions else 0, 1)
            course_breakdown.append({
                'id': course.id,
                # SCHEMA UPDATE: course_title/course_code (v2 schema
                # redesign renamed title/code -> course_title/course_code;
                # JSON key names 'name'/'code' are unchanged).
                'name': course.course_title,
                'code': course.course_code,
                'pct': pct,
                'attended': attended_sessions,
                'total': total_sessions,
            })

        # 5) Calculate overall stats
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        # 6) Get the recent attendance history elegantly via ORM
        # session_id included so the Flutter side can deep-link a tapped
        # record into its own detail view (see get_session_detail_for_student
        # below) -- previously omitted, which is why that tap-through wasn't
        # wired up on the client (see records_view.dart's own doc-comment
        # about this exact gap before this fix).
        recent_records = db.session.query(
            Course.course_code, SessionModel.session_date, SessionModel.planned_start, Attendance.status, SessionModel.id # SCHEMA UPDATE: code -> course_code
        ).select_from(Attendance).join(
            SessionModel, Attendance.session_id == SessionModel.id
        ).join(
            Course, SessionModel.course_id == Course.id
        ).filter(
            Attendance.student_id == student.id
        ).order_by(
            SessionModel.session_date.desc(), SessionModel.planned_start.desc() # FIX: order by planned_start
        ).limit(10).all()

        recent_attendance = []
        for course_code, session_date, start_time, status, session_id in recent_records:
            recent_attendance.append({
                'course': course_code,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if start_time else '--:--', # FIX: Safe null fallback
                'status': status,
                'session_id': session_id,
            })

        # 7) Bundle everything into a clean JSON object for Flutter
        return jsonify({
            "success": True,
            "data": {
                "student": {
                    "full_name": student.full_name or claims.get("username"),
                    "department": student.department.name if student.department else "Unknown", # FIX: extract .name string
                    "level": student.level,
                    "rfid_uid": student.rfid_uid,
                    "matric_number": student.matric_number
                },
                "stats": {
                    "overall_rate": overall_rate,
                    "attendance_count": attended_sessions_count,
                    "total_sessions": total_sessions_count,
                    "at_risk_count": at_risk_count,
                    "enrollment_count": enrollment_count
                },
                "courses": course_breakdown,
                "recent_attendance": recent_attendance
            }
        }), 200

    except Exception:
        # SECURITY FIX: was printing str(e) to the server console (fine)
        # AND returning it to the client as "details" (not fine -- can leak
        # DB schema/table/column names or query fragments to whoever calls
        # this API). api_error_response logs the full exception + traceback
        # server-side via the "suaams" logger and returns only a generic
        # message to the caller.
        return api_error_response("Mobile API Error", "Database error occurred")


@api_student_bp.route('/course/<int:course_id>/history', methods=['GET'])
@jwt_required()
def get_course_attendance_history(course_id):
    """
    Full per-session attendance breakdown for one course, scoped to the
    calling student -- mirrors get_session_history in api/lecturer.py
    (same response shape), but "who was present" becomes "was I present"
    since a student only ever sees their own record.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        current_user_id = int(get_jwt_identity())
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        course = Course.query.get(course_id)
        if not course:
            return jsonify({"error": "Course not found."}), 404

        enrolled = Enrollment.query.filter_by(student_id=student.id, course_id=course_id).first()
        if not enrolled:
            return jsonify({"error": "Not enrolled in this course."}), 403

        sessions = (
            SessionModel.query
            .filter_by(course_id=course_id, is_active=False)
            .order_by(SessionModel.session_date.desc())
            .all()
        )

        history = []
        for session in sessions:
            attendance = Attendance.query.filter_by(
                session_id=session.id, student_id=student.id
            ).first()
            history.append({
                'session_id': session.id,
                'date': session.session_date.strftime('%d %b %Y') if session.session_date else None,
                'planned_start': str(session.planned_start) if session.planned_start else None,
                'planned_end': str(session.planned_end) if session.planned_end else None,
                'status': attendance.status if attendance else 'absent',
                'time_in': attendance.time_in.strftime('%H:%M') if attendance and attendance.time_in else None,
            })

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.course_title,
                    "code": course.course_code,
                },
                "sessions": history,
            }
        }), 200

    except Exception:
        return api_error_response("Course Attendance History API Error", "Failed to load attendance history")


# Keyed by user id -- a real check-in only needs one beacon per attendance
# tap, so 10/minute comfortably covers retries (e.g. student re-opens the
# sheet after a failed read) while still capping a compromised/malicious
# client from spamming token minting.
@api_student_bp.route('/checkin/beacon', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def mint_checkin_beacon():
    """
    Step 1 of the HCE check-in flow. Called by the Flutter app, over its
    normal authenticated connection, right after the student passes the
    in-app biometric prompt. Returns a short-lived 32-char handle to
    broadcast over NFC HCE -- small enough that the terminal needs
    exactly one APDU exchange (see beacon.py for the reasoning).

    The active session is resolved HERE and bound into the token, rather
    than being looked up at submit time. The terminal doesn't know which
    course it belongs to today, so the previous implementation took
    "the most recently started active session across all courses" when
    the terminal's POST arrived. With two lecturers running concurrent
    sessions that meant a tap at a room-A terminal could be credited to
    a room-B session. Resolving early also lets the student get a clear
    "no session running" message immediately, instead of after the tap.
    """
    claims = get_jwt()

    # Only students wear/broadcast the check-in beacon; lecturers/admins
    # don't have an attendance record to create.
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    current_user_id = get_jwt_identity()

    student = Student.query.filter_by(user_id=current_user_id).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    # Only consider sessions for courses this student is actually
    # enrolled in, so we never mint a handle bound to a session they
    # couldn't be marked into anyway.
    active_session = _active_session_for_student(student)
    if not active_session:
        return jsonify({"error": "No active session for you right now"}), 404

    try:
        beacon_token = mint_beacon(
            student_id=student.id,
            session_id=active_session.id,
            ttl_seconds=BEACON_TOKEN_TTL_SECONDS,
        )
    except BeaconError as e:
        # Server misconfiguration (missing BEACON_SIGNING_SECRET), not a
        # client error. Log loudly, return a generic 500 so the student
        # isn't told their credentials are bad.
        current_app.logger.error("Beacon mint failed: %s", e)
        return jsonify({"error": "Check-in is temporarily unavailable"}), 503

    return jsonify({
        "success": True,
        "beacon_token": beacon_token,
        "expires_in": BEACON_TOKEN_TTL_SECONDS,
    }), 200


# No JWT here to key by (see docstring below), so this falls back to
# per-IP limiting. 30/minute is generous for one ESP32 terminal handling a
# stream of students tapping in, while still capping brute-force/DoS
# attempts against an unauthenticated endpoint.
@api_student_bp.route('/checkin', methods=['POST'])
@limiter.limit("30 per minute")
def submit_checkin_beacon():
    """
    Step 2 of the HCE check-in flow. Called by the ESP32 terminal (not the
    phone) after it reads the beacon token off the phone via HCE/APDU.
    Deliberately has no @jwt_required(): the ESP32 has no login session of
    its own -- it's just relaying what it physically read -- so the beacon
    token itself, once decoded and checked below, is the credential. This
    mirrors the existing unauthenticated /attendance route in app.py, which
    is posted to directly by ESP32 hardware the same way.
    """
    data = request.get_json()

    # Gate the terminal before doing anything with the payload. Without
    # this, the endpoint is open to anyone who can reach it.
    if not _check_terminal_auth():
        return jsonify({"error": "Unauthorized terminal"}), 401

    beacon_token = data.get('beacon_token') if data else None
    if not beacon_token:
        return jsonify({"error": "beacon_token is required"}), 400

    # Verified in beacon.py rather than via @jwt_required(): this arrives
    # in the request body (relayed by hardware), not as an Authorization
    # header. verify_beacon() checks the HMAC in constant time and
    # rejects anything expired, malformed, or forged.
    try:
        student_id, session_id = verify_beacon(beacon_token)
    except BeaconError:
        # Deliberately vague: the endpoint should not be an oracle that
        # tells an attacker *which* check failed.
        return jsonify({"error": "Invalid or expired beacon token"}), 401

    student = Student.query.get(student_id)
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    # Use the session bound into the token at mint time. Do NOT fall back
    # to "newest active session" here -- that reintroduces the
    # cross-session miscrediting bug this design exists to fix.
    active_session = SessionModel.query.get(session_id)
    if not active_session:
        return jsonify({"error": "Session no longer exists"}), 404

    # The session can legitimately end inside the acceptance window (a
    # lecturer ending class as the last student taps), so re-check that
    # it's still running rather than trusting the mint-time snapshot.
    if not active_session.is_active:
        return jsonify({"error": "That session has ended"}), 409

    enrolled = Enrollment.query.filter_by(
        student_id=student.id, course_id=active_session.course_id
    ).first()
    if not enrolled:
        return jsonify({"error": "Student did not register this course"}), 400

    already_recorded = Attendance.query.filter_by(
        session_id=active_session.id, student_id=student.id
    ).first()
    if already_recorded:
        return jsonify({"success": True, "message": "Attendance already marked"}), 200

    record = Attendance(student_id=student.id, session_id=active_session.id,
                         status=compute_attendance_status(active_session),
                         method='nfc')
    db.session.add(record)
    db.session.commit()

    # Best-effort push -- see send_push_notification's docstring for why a
    # failure here never affects the response below (attendance is already
    # committed by this point regardless).
    course = active_session.course
    send_push_notification(
        student.user,
        'attendance_marked',
        'Attendance Recorded',
        f"You've been marked present for {course.course_code}." if course else "You've been marked present.",
        data={'session_id': active_session.id, 'course_id': active_session.course_id},
    )

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully.",
        "student": {
            "id": student.id,
            "full_name": student.full_name,
        }
    }), 200


# Keyed by user id -- polled repeatedly (every ~1s, for up to ~10s per
# check-in attempt) by the app, so this needs a much more generous limit
# than the mint/submit endpoints above.
@api_student_bp.route('/checkin/status', methods=['GET'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def get_checkin_status():
    """
    Step 3 (optional) of the HCE check-in flow. Polled by the Flutter app
    after broadcasting a beacon, to find out whether the ESP32 terminal
    actually relayed it and Flask recorded attendance -- the app has no
    other way to know this, since the beacon broadcast itself is one-way
    (phone -> ESP32 -> Flask; nothing comes back to the phone over NFC).

    Resolves "the active session" via the shared
    _active_session_for_student() helper -- the same one mint_checkin_beacon
    uses to bind a session_id into the token. This has to agree with what
    was minted: if it checked a different session, attendance would land
    correctly but the app would poll to "unconfirmed" and tell the student
    their tap failed when it hadn't.

    checked_in=False alone doesn't say WHY -- "not enrolled in this
    course" is a definite, permanent failure (waiting longer never fixes
    it), while "no Attendance row yet" might just be a slow ESP32/backend
    round-trip still in flight. Without the `reason` field these look
    identical to the polling client, so it can't tell "stop waiting, this
    was never going to work" apart from "keep waiting, it might still
    land". Same idea for "no active session" -- checking it BEFORE
    enrollment (rather than after, like submit_checkin_beacon does) since
    there's nothing to be enrolled *in* if no session is running at all.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    current_user_id = get_jwt_identity()
    student = Student.query.filter_by(user_id=int(current_user_id)).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    active_session = _active_session_for_student(student)
    if not active_session:
        return jsonify({"success": True, "checked_in": False, "reason": "no_active_session"}), 200

    enrolled = Enrollment.query.filter_by(
        student_id=student.id, course_id=active_session.course_id
    ).first()
    if not enrolled:
        return jsonify({
            "success": True,
            "checked_in": False,
            "reason": "not_enrolled",
            "course_code": active_session.course.course_code if active_session.course else None,
        }), 200

    record = Attendance.query.filter_by(
        session_id=active_session.id, student_id=student.id
    ).first()

    if not record:
        return jsonify({"success": True, "checked_in": False}), 200

    return jsonify({
        "success": True,
        "checked_in": True,
        "course_code": active_session.course.course_code if active_session.course else None,
    }), 200


@api_student_bp.route('/checkin/methods', methods=['GET'])
@jwt_required()
def get_checkin_methods():
    """
    Which check-in channels this deployment has switched on. The app uses
    it to decide whether to offer Bluetooth at all: with BLE_BEACON_SECRET
    unset, BLE is off for everyone and the app hides the option rather than
    letting a student scan for a code the server would refuse.

    Reports configuration only. Whether a particular phone can do NFC is
    the app's own check (it's a hardware question the server can't see).
    """
    return jsonify({
        "success": True,
        "nfc": bool(os.environ.get("BEACON_SIGNING_SECRET", "").strip()),
        "ble": ble_beacon.is_enabled(),
    }), 200


# Same limit and keying as the NFC mint: one call per check-in attempt,
# with room for a few retries if the first scan heard a stale code.
@api_student_bp.route('/checkin/ble', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def submit_ble_checkin():
    """
    Bluetooth check-in, the fallback for phones that can't tap in by NFC.

    The terminal broadcasts a code that rotates every few seconds; the app
    scans for it after the student passes the fingerprint prompt and posts
    what it heard here, over its own authenticated connection. Unlike NFC,
    the terminal is not in this request at all -- hearing a current code is
    the proof of presence. See ble_beacon.py for the format and for the
    relay weakness that makes this the fallback rather than the default.

    Body: {"payload": "<28 hex chars>", "rssi": <int, optional>}
    `payload` is the 14 bytes after the company ID in the advertisement,
    forwarded as-is so the byte layout lives only here and in the firmware.

    Answers definitively in one round-trip (no status polling): unlike the
    NFC path, there's no third party whose POST might still be in flight.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    student = Student.query.filter_by(user_id=int(get_jwt_identity())).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    if not ble_beacon.is_enabled():
        return jsonify({"error": "Bluetooth check-in is not available"}), 503

    data = request.get_json(silent=True) or {}
    payload_hex = data.get('payload')
    try:
        payload = bytes.fromhex(payload_hex) if isinstance(payload_hex, str) else None
    except ValueError:
        payload = None
    if payload is None:
        return jsonify({"error": "payload must be a hex string"}), 400

    try:
        terminal, slot = ble_beacon.verify_payload(payload)
    except ble_beacon.BleBeaconError:
        # Vague on purpose (same as the NFC submit): don't reveal whether
        # the code was forged, malformed or just old. In practice it's
        # almost always old -- the app rescans and retries.
        return jsonify({"error": "Invalid or expired code", "reason": "invalid_code"}), 401

    # RSSI is phone-reported and therefore spoofable -- logged for
    # diagnostics and calibration only, never used to decide anything.
    current_app.logger.info(
        "BLE check-in: student=%s terminal=%s slot=%s rssi=%s",
        student.id, terminal, slot, data.get('rssi'),
    )

    # Same resolver as the NFC mint and /checkin/status, so the three can't
    # disagree about which session a check-in belongs to. It only returns
    # running sessions for courses the student is enrolled in.
    active_session = _active_session_for_student(student)
    if not active_session:
        return jsonify({
            "error": "No active session for you right now",
            "reason": "no_active_session",
        }), 404

    course_code = active_session.course.course_code if active_session.course else None

    already = Attendance.query.filter_by(
        session_id=active_session.id, student_id=student.id
    ).first()
    if already:
        return jsonify({
            "success": True,
            "message": "Attendance already marked",
            "course_code": course_code,
        }), 200

    record = Attendance(student_id=student.id, session_id=active_session.id,
                         status=compute_attendance_status(active_session),
                         method='ble')
    db.session.add(record)
    db.session.commit()

    send_push_notification(
        student.user,
        'attendance_marked',
        'Attendance Recorded',
        f"You've been marked present for {course_code}." if course_code else "You've been marked present.",
        data={'session_id': active_session.id, 'course_id': active_session.course_id},
    )

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully.",
        "course_code": course_code,
    }), 200


@api_student_bp.route('/schedule/today', methods=['GET'])
@jwt_required()
def get_today_schedule():
    """
    Returns the student's enrolled courses that are scheduled (per the
    recurring Timetable) for today's weekday, each with a live status --
    this replaces the hardcoded mock times/status that used to live in
    student_dashboard_screen.dart's "TODAY'S PROTOCOL" list. Deliberately a
    separate endpoint from /dashboard: dashboard stats are historical and
    barely change, but a course's status here changes live as a lecturer
    starts/ends a session and students check in, so it has its own refresh
    cadence.

    Status per course:
    - PENDING: no Session row for today yet (lecturer hasn't started
      class), OR a Session exists, is still active, and this student
      hasn't checked in yet.
    - PRESENT: a Session exists for today and Attendance was recorded for
      this student.
    - ABSENT: a Session existed for today, is no longer active, and no
      Attendance was recorded.

    Courses with no Timetable entry for today's weekday are omitted
    entirely -- this list is "what's on today", not every enrolled course.
    """
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()

    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        today = date.today()
        # Python's date.weekday(): Monday=0 .. Sunday=6 -- same convention
        # models.py documents for Timetable.day_of_week, so no conversion
        # needed here.
        today_weekday = today.weekday()

        # Reuse the Course objects already loaded via student.courses
        # instead of re-querying Course per timetable row below.
        courses_by_id = {course.id: course for course in student.courses}
        if not courses_by_id:
            return jsonify({"success": True, "today_protocol": []}), 200

        timetable_entries = Timetable.query.filter(
            Timetable.day_of_week == today_weekday,
            Timetable.course_id.in_(courses_by_id.keys()),
        ).order_by(Timetable.start_time.asc()).all()

        today_protocol = []
        # Courses already covered by a Timetable row above. Used below to
        # work out which active sessions are "ad-hoc" (no scheduled slot
        # today) and therefore still need an entry.
        covered_course_ids = set()
        for entry in timetable_entries:
            course = courses_by_id.get(entry.course_id)
            if course is None:
                continue
            covered_course_ids.add(entry.course_id)

            session_today = SessionModel.query.filter_by(
                course_id=entry.course_id, session_date=today
            ).order_by(SessionModel.id.desc()).first()

            status = 'PENDING'
            # Whether a check-in would actually succeed right now: a Session
            # row exists for today, is still active, and this student hasn't
            # already checked into it.
            #
            # This is separate from `status` on purpose. `status` defaults to
            # 'PENDING' and is ONLY narrowed once a session_today row exists,
            # so 'PENDING' collapses two very different situations the client
            # must not treat alike:
            #   1. a session is live and the student can check in, versus
            #   2. the lecturer hasn't started anything yet (the common case
            #      all morning, for a 2pm lecture).
            # A client gating its check-in UI on status == 'PENDING' alone
            # therefore invites a tap that is guaranteed to be rejected
            # server-side, and can even claim a session is "live" when none
            # exists. Note the timetable's own start_time is deliberately not
            # used for this -- lecturers routinely start late or early, and
            # the Session row is the only authority on what is really running.
            session_live = False

            # Default to the recurring Timetable slot; overridden below by
            # the actual Session's own planned_start/planned_end if one
            # exists for today (a lecturer may have adjusted the time when
            # starting the session).
            start_time = entry.start_time
            end_time = entry.end_time

            if session_today:
                start_time = session_today.planned_start or entry.start_time
                end_time = session_today.planned_end or entry.end_time

                attended = Attendance.query.filter_by(
                    session_id=session_today.id, student_id=student.id
                ).first()

                if attended:
                    status = 'PRESENT'
                elif not session_today.is_active:
                    status = 'ABSENT'
                # else: session is live and student hasn't checked in yet
                # -- status stays 'PENDING'.
                session_live = session_today.is_active and not attended

            today_protocol.append({
                'course_id': course.id,
                # SCHEMA UPDATE: course_title/course_code.
                'course_name': course.course_title,
                'course_code': course.course_code,
                'status': status,
                # Narrows the PENDING ambiguity described above. Consumed by
                # the dashboard's check-in card to decide whether the tap
                # target is armed -- see TodayProtocolEntry in the Flutter app.
                'session_live': session_live,
                'start_time': start_time.strftime('%H:%M') if start_time else None,
                'end_time': end_time.strftime('%H:%M') if end_time else None,
                'room': entry.room,
            })

        # ---- Ad-hoc / unscheduled sessions -------------------------------
        # A lecturer can start a session for ANY course they own at any
        # time -- start_session() in blueprints/lecturer.py has no timetable
        # check, and resolve_timetable_slot_for_course() simply returns None
        # when there's no slot today, leaving planned_start/end NULL. That's
        # how a make-up class or an extra lab works.
        #
        # The loop above only ever looks at courses that HAVE a Timetable row
        # for today's weekday, so an ad-hoc session for a course with no
        # scheduled slot today never appears at all -- the student would see
        # "No Upcoming Sessions" while a real, checkable session ran. Worse,
        # this is reachable in the check-in path independently: the beacon
        # mint resolves the session through _active_session_for_student(),
        # which filters on is_active and enrollment only and never consults
        # Timetable at all. So the session was always mintable; it was purely
        # invisible in the UI.
        #
        # Union it in so an ad-hoc session is as checkable as a scheduled
        # one. Scoped to the student's enrolled courses (same enrollment
        # join as _active_session_for_student), so this can't surface
        # someone else's class.
        adhoc_sessions = (
            SessionModel.query
            .join(Enrollment, Enrollment.course_id == SessionModel.course_id)
            .filter(
                Enrollment.student_id == student.id,
                SessionModel.session_date == today,
                SessionModel.is_active.is_(True),
                # Excluded above already -- otherwise a scheduled course
                # with a live session would be appended twice.
                SessionModel.course_id.notin_(covered_course_ids),
            )
            .order_by(SessionModel.start_time.asc())
            .all()
        )

        for session in adhoc_sessions:
            course = courses_by_id.get(session.course_id)
            if course is None:
                continue

            attended = Attendance.query.filter_by(
                session_id=session.id, student_id=student.id
            ).first()

            # An ad-hoc session that's still active and not yet attended is
            # exactly the "live, go check in" case. If the student somehow
            # already has attendance on it, report PRESENT rather than
            # advertising a check-in they no longer need.
            session_live = session.is_active and not attended

            today_protocol.append({
                'course_id': course.id,
                'course_name': course.course_title,
                'course_code': course.course_code,
                'status': 'PRESENT' if attended else 'PENDING',
                'session_live': session_live,
                # Fall back to the real start time the lecturer recorded
                # (set in start_session()), since there's no scheduled slot
                # to read from. end_time stays None -- an ad-hoc session has
                # no defined finish.
                'start_time': (
                    (session.planned_start or session.start_time).strftime('%H:%M')
                    if (session.planned_start or session.start_time)
                    else None
                ),
                'end_time': (
                    session.planned_end.strftime('%H:%M')
                    if session.planned_end
                    else None
                ),
                # No Timetable row means no room to report.
                'room': None,
                # Marks this as unscheduled so the Flutter client can label it
                # differently from an ordinary "not started yet" class. Purely
                # informational -- the check-in path ignores it.
                'ad_hoc': True,
            })

        return jsonify({"success": True, "today_protocol": today_protocol}), 200

    except Exception:
        return api_error_response("Today Schedule Error", "Failed to load today's schedule")


@api_student_bp.route('/schedule/week', methods=['GET'])
@jwt_required()
def get_week_schedule():
    """
    The student's full recurring weekly Timetable, across all enrolled
    courses -- backs the Timetable tab's day list and the Day Detail view
    (both filter this same response client-side by day_of_week rather than
    each making their own call). Unlike /schedule/today, this is purely the
    recurring schedule with no live Session/Attendance status attached,
    since most of the week hasn't happened yet.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        current_user_id = int(get_jwt_identity())
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        courses_by_id = {course.id: course for course in student.courses}
        if not courses_by_id:
            return jsonify({"success": True, "week": []}), 200

        entries = Timetable.query.filter(
            Timetable.course_id.in_(courses_by_id.keys())
        ).order_by(Timetable.day_of_week.asc(), Timetable.start_time.asc()).all()

        week = []
        for entry in entries:
            course = courses_by_id.get(entry.course_id)
            if course is None:
                continue
            week.append({
                'day_of_week': entry.day_of_week,
                'course_id': course.id,
                'course_name': course.course_title,
                'course_code': course.course_code,
                'start_time': entry.start_time.strftime('%H:%M') if entry.start_time else None,
                'end_time': entry.end_time.strftime('%H:%M') if entry.end_time else None,
                'room': entry.room,
            })

        return jsonify({"success": True, "week": week}), 200

    except Exception:
        return api_error_response("Week Schedule Error", "Failed to load week schedule")


# Called once at app start (and again whenever Firebase hands the app a
# fresh token via onTokenRefresh) -- generous limit since a refresh can
# legitimately happen a few times in a session (e.g. app reinstall, token
# rotation), not just once at login.
@api_student_bp.route('/device-token', methods=['POST'])
@limiter.limit("20 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def register_device_token():
    """
    Upserts by fcm_token, not by (user_id, platform): the same physical app
    instance can only ever be one row, and if the token shows up under a
    different user_id than before (e.g. a different student logged into the
    same physical phone), this re-points the existing row rather than
    leaving a stale duplicate pointed at the old user.
    """
    data = request.get_json()
    fcm_token = data.get('fcm_token') if data else None
    platform = data.get('platform') if data else None

    if not fcm_token or platform not in ('android', 'ios'):
        return jsonify({"error": "fcm_token and platform ('android'|'ios') are required"}), 400

    current_user_id = int(get_jwt_identity())

    try:
        existing = DeviceToken.query.filter_by(fcm_token=fcm_token).first()
        if existing:
            existing.user_id = current_user_id
            existing.platform = platform
        else:
            db.session.add(DeviceToken(
                user_id=current_user_id, fcm_token=fcm_token, platform=platform,
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        return api_error_response("Device Token Registration Error", "Failed to register device token")

    return jsonify({"success": True}), 200


@api_student_bp.route('/notifications', methods=['GET'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def get_notifications():
    current_user_id = int(get_jwt_identity())

    notifications = Notification.query.filter_by(user_id=current_user_id) \
        .order_by(Notification.created_at.desc()).limit(50).all()

    return jsonify({
        "success": True,
        "notifications": [{
            "id": n.id,
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "data": n.data,
            "read": n.read_at is not None,
            # MySQL's DATETIME column drops tzinfo on read-back even though
            # this was written as an aware UTC datetime (models.py's
            # default=lambda: datetime.now(timezone.utc)) -- a bare
            # .isoformat() on that naive value omits the offset entirely,
            # and the Flutter side's DateTime.parse() then misreads it as
            # LOCAL time instead of UTC, throwing the "time ago" display off
            # by the device's UTC offset. Reattaching tzinfo=utc before
            # serializing (safe: every value in this column is UTC by
            # construction) makes the ISO string carry an explicit +00:00.
            "created_at": n.created_at.replace(tzinfo=timezone.utc).isoformat(),
        } for n in notifications],
        "unread_count": sum(1 for n in notifications if n.read_at is None),
    }), 200


@api_student_bp.route('/notifications/<int:notification_id>/read', methods=['POST'])
@limiter.limit("60 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def mark_notification_read(notification_id):
    current_user_id = int(get_jwt_identity())

    notification = Notification.query.filter_by(
        id=notification_id, user_id=current_user_id
    ).first()
    if not notification:
        return jsonify({"error": "Notification not found"}), 404

    if notification.read_at is None:
        notification.read_at = datetime.now(timezone.utc)
        db.session.commit()

    return jsonify({"success": True}), 200


@api_student_bp.route('/announcements', methods=['GET'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def get_student_announcements():
    """Every announcement that applies to the signed-in student --
    university-wide, their own department, or any course they're currently
    enrolled in. Mirrors students_for_announcement() in utils.py (which
    resolves the opposite direction: announcement -> students, used to fan
    out push notifications when one is posted) -- keep both in sync if this
    scoping rule ever changes.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        current_user_id = int(get_jwt_identity())
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        course_ids = [c.id for c in student.courses]

        # Announcement.course_id.in_(course_ids) correctly evaluates to
        # "false for every row" when course_ids is empty -- no special-case
        # needed for a student with no enrollments yet.
        announcements = (
            Announcement.query
            .filter(
                Announcement.is_active == True,  # noqa: E712 -- SQLAlchemy comparator, not a Python bool check
                db.or_(
                    Announcement.scope == 'university',
                    db.and_(Announcement.scope == 'department', Announcement.department_id == student.department_id),
                    db.and_(Announcement.scope == 'course', Announcement.course_id.in_(course_ids)),
                )
            )
            .order_by(Announcement.created_at.desc())
            .all()
        )

        return jsonify({
            "success": True,
            # Sent alongside the list so the nav badge can render without a
            # second request. Deriving it here rather than in the app means
            # the definition of "unread" lives in exactly one place.
            "unread_count": sum(
                1 for a in announcements if a.id > (student.last_seen_announcement_id or 0)
            ),
            "announcements": [{
                "id": a.id,
                "title": a.title,
                "body": a.body,
                "scope": a.scope,
                "department_name": a.department.name if a.scope == 'department' and a.department else None,
                "course_code": a.course.course_code if a.scope == 'course' and a.course else None,
                # Per-item flag so the list can visually mark read rows
                # without the client having to know about the watermark.
                "is_read": a.id <= (student.last_seen_announcement_id or 0),
                # Same tzinfo-reattach fix as get_notifications() above --
                # MySQL's DATETIME drops the UTC offset on read-back even
                # though this column is always written UTC-aware.
                "created_at": a.created_at.replace(tzinfo=timezone.utc).isoformat(),
            } for a in announcements],
        }), 200

    except Exception:
        return api_error_response("Student Announcements Error", "Failed to load announcements")


@api_student_bp.route('/announcements/seen', methods=['PATCH'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def mark_announcements_seen():
    """Advance this student's announcement read watermark.

    Called when the student opens the announcements screen. The client
    sends the newest id it was shown; we only ever move the mark FORWARD,
    so a stale request arriving out of order (an old screen resuming after
    a newer one already marked) can't un-read anything.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        current_user_id = int(get_jwt_identity())
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        data = request.get_json(silent=True) or {}
        try:
            seen_id = int(data.get('announcement_id'))
        except (TypeError, ValueError):
            return jsonify({"error": "announcement_id must be an integer."}), 400

        # Monotonic by construction -- see the column comment on
        # Student.last_seen_announcement_id.
        current = student.last_seen_announcement_id or 0
        if seen_id > current:
            student.last_seen_announcement_id = seen_id
            db.session.commit()

        return jsonify({
            "success": True,
            "last_seen_announcement_id": student.last_seen_announcement_id,
        }), 200

    except Exception:
        return api_error_response("Mark Seen Error", "Failed to update announcement read state")


@api_student_bp.route('/device-info', methods=['GET'])
@jwt_required()
def get_device_info():
    """
    Read-only device-binding status for the "Linked Devices" screen.
    Deliberately no unbind/reset action here -- CLAUDE.md's threat model
    requires a physical ID check at the Admin Web Dashboard to reset a
    binding (see reset_student_binding in blueprints/admin.py), so a
    self-service reset in the app would defeat the whole point of device
    binding. This endpoint only reports status; the screen explains the
    admin-reset flow rather than offering to do it itself.
    """
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        current_user_id = int(get_jwt_identity())
        student = Student.query.filter_by(user_id=current_user_id).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        return jsonify({
            "success": True,
            "data": {
                "device_bound": bool(student.device_id),
            }
        }), 200

    except Exception:
        return api_error_response("Device Info Error", "Failed to load device info")


# ── Self-service course registration ────────────────────────────────────────
# Scoped to the student's own department + the currently active semester --
# matches how every other course-facing query in this file/admin.py already
# scopes courses (department_id, semester_id), and keeps a student from
# registering into a course that isn't actually theirs to take.

@api_student_bp.route('/courses/available', methods=['GET'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def get_available_courses():
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        student = Student.query.filter_by(user_id=int(get_jwt_identity())).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        active_semester = Semester.query.filter_by(is_active=True).first()
        if not active_semester:
            return jsonify({"success": True, "data": {"semester": None, "courses": []}}), 200

        enrolled_course_ids = {c.id for c in student.courses}

        courses = Course.query.filter(
            Course.department_id == student.department_id,
            Course.semester_id == active_semester.id,
        ).order_by(Course.course_code).all()

        return jsonify({
            "success": True,
            "data": {
                "semester": active_semester.name,
                "courses": [
                    {
                        "id": c.id,
                        "course_code": c.course_code,
                        "course_title": c.course_title,
                        "credit_units": c.credit_units,
                        "lecturer": c.lecturer.full_name if c.lecturer else None,
                        "enrolled": c.id in enrolled_course_ids,
                    }
                    for c in courses
                ],
            },
        }), 200

    except Exception:
        return api_error_response("Available Courses Error", "Failed to load available courses")


@api_student_bp.route('/courses/<int:course_id>/register', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def register_course(course_id):
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        student = Student.query.filter_by(user_id=int(get_jwt_identity())).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        course = Course.query.get(course_id)
        if not course:
            return jsonify({"error": "Course not found."}), 404

        active_semester = Semester.query.filter_by(is_active=True).first()
        if not active_semester or course.semester_id != active_semester.id:
            return jsonify({"error": "This course is not open for registration this semester."}), 400

        if course.department_id != student.department_id:
            return jsonify({"error": "This course is not offered by your department."}), 403

        if Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first():
            return jsonify({"error": "You are already registered for this course."}), 409

        db.session.add(Enrollment(student_id=student.id, course_id=course.id))
        db.session.commit()

        return jsonify({"success": True, "message": f"Registered for {course.course_code}."}), 201

    except Exception:
        db.session.rollback()
        return api_error_response("Course Registration Error", "Failed to register for course")


@api_student_bp.route('/courses/<int:course_id>/drop', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def drop_course(course_id):
    claims = get_jwt()
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    try:
        student = Student.query.filter_by(user_id=int(get_jwt_identity())).first()
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        enrollment = Enrollment.query.filter_by(student_id=student.id, course_id=course_id).first()
        if not enrollment:
            return jsonify({"error": "You are not registered for this course."}), 404

        db.session.delete(enrollment)
        db.session.commit()

        return jsonify({"success": True, "message": "Course dropped."}), 200

    except Exception:
        db.session.rollback()
        return api_error_response("Course Drop Error", "Failed to drop course")

# Offline backlog sync. Deliberately a SEPARATE route from /checkin, and
# deliberately incapable of crediting attendance -- see the OfflineCheckinLog
# docstring in models.py for the full reasoning.
#
# The short version: a beacon is only valid for a few seconds, so anything a
# terminal queued while offline has always expired by the time it arrives.
# The server verifies the HMAC anyway, which proves the token was genuinely
# ours and not forged, and reads the student/session binding out of the
# payload -- but it records provenance for a human to review rather than
# writing an Attendance row. Crediting them would reinstate exactly the
# relay/buddy-punching hole the short window exists to close.
@api_student_bp.route('/checkin/backlog', methods=['POST'])
@limiter.limit("30 per minute")
def sync_offline_checkin_backlog():
    """Accept a batch of beacons a terminal captured while it was offline.

    Body: {"records": [{"beacon_token": "<32 chars>"}, ...]}

    The terminal sends no timestamps. It has no RTC and cannot know
    wall-clock time while disconnected, so the capture time is derived here
    from the beacon's own `exp` field (minus the TTL) -- the only clock
    involved is the server's, which is the one that matters.
    """
    if not _check_terminal_auth():
        return jsonify({"error": "Unauthorized terminal"}), 401

    data = request.get_json()
    records = (data or {}).get('records')
    if not isinstance(records, list) or not records:
        return jsonify({"error": "records must be a non-empty list"}), 400

    # Bound the batch. A terminal with a full queue sends at most
    # MAX_OFFLINE_QUEUE; the cap is a second line of defence so a
    # compromised or malfunctioning terminal can't turn this into a
    # bulk-insert DoS against the attendance DB.
    if len(records) > MAX_OFFLINE_BACKLOG_BATCH:
        return jsonify({"error": f"Too many records (max {MAX_OFFLINE_BACKLOG_BATCH})"}), 400

    results = []
    accepted = 0

    for record in records:
        token = record.get('beacon_token') if isinstance(record, dict) else None
        entry = {"beacon_token": token}

        if not token:
            entry.update(status="rejected", reason="missing beacon_token")
            results.append(entry)
            continue

        # Signature is checked exactly as it is for a live check-in, so a
        # terminal cannot fabricate a capture. verify_beacon_signature()
        # deliberately does NOT reject an expired token -- every offline
        # capture is expired by definition, and expiry is the expected case
        # here rather than a failure. What it guarantees is that the token
        # is genuinely ours and that the student/session binding is real.
        try:
            student_id, session_id, expires_at = verify_beacon_signature(token)
        except BeaconError as e:
            entry.update(status="rejected", reason=str(e)[:60])
            results.append(entry)
            continue

        # Capture time = the moment the beacon was minted, which is when the
        # student was tapping. Everything after that (RF transfer, the
        # terminal's failed POST) is within a few hundred ms.
        captured_at = datetime.fromtimestamp(
            expires_at - BEACON_TOKEN_TTL_SECONDS, tz=timezone.utc
        )

        student = Student.query.get(student_id)
        session = SessionModel.query.get(session_id)
        if not student or not session:
            entry.update(status="rejected", reason="student or session no longer exists")
            results.append(entry)
            continue

        # Idempotent: (student, session) is unique, so a re-flushed queue
        # updates the existing row instead of erroring.
        existing = OfflineCheckinLog.query.filter_by(
            student_id=student_id, session_id=session_id
        ).first()
        if existing:
            entry.update(status=existing.status, reason="already recorded",
                         captured_at=captured_at.isoformat())
            results.append(entry)
            continue

        # If attendance already landed live while this sat in the queue,
        # the backlog entry is redundant -- note that rather than filing a
        # record a lecturer would have to dismiss for no reason.
        already_present = Attendance.query.filter_by(
            student_id=student_id, session_id=session_id
        ).first()
        status = 'superseded' if already_present else 'pending_verification'

        log = OfflineCheckinLog(
            student_id=student_id,
            session_id=session_id,
            terminal_id=request.headers.get('X-Terminal-Id', 'unknown'),
            captured_at=captured_at,
            status=status,
        )
        db.session.add(log)
        accepted += 1

        entry.update(
            status=status,
            student_id=student_id,
            session_id=session_id,
            full_name=student.full_name,
            course_code=session.course.course_code if session.course else None,
            captured_at=captured_at.isoformat(),
        )
        results.append(entry)

    db.session.commit()

    current_app.logger.info(
        "Offline backlog sync from terminal %s: %d record(s), %d newly stored",
        request.headers.get('X-Terminal-Id', 'unknown'), len(records), accepted
    )

    return jsonify({
        "success": True,
        "accepted": accepted,
        "received": len(records),
        "results": results,
    }), 200
