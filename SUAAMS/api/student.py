from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt,
    create_access_token, decode_token,
)
from datetime import timedelta, date, datetime, timezone

# Import db and our elegant SQLAlchemy models
# (added Enrollment here for the check-in endpoints, Timetable for the
# today's-schedule endpoint below)
from models import db, Student, Course, Session as SessionModel, Attendance, Enrollment, Timetable, DeviceToken, Notification, Semester, Announcement
from extensions import limiter, jwt_identity_or_ip, api_error_response
from push_notifications import send_push_notification
from utils import compute_attendance_status

# Create the API blueprint for student mobile endpoints
api_student_bp = Blueprint('api_student', __name__, url_prefix='/api/v1/student')

# How long a minted HCE "beacon" token stays valid. Deliberately short --
# this is NOT the student's login session JWT, which lives for the whole
# session. CLAUDE.md's threat model calls 3 seconds the canonical, strict
# handshake-acceptance window for HCE/BLE proximity tokens; this constant
# must stay at 3 to match (previously set to 5, which allowed a longer
# replay window than the documented threat model permits). Reusing the
# long-lived session token here instead of a short-lived one would defeat
# the anti-relay requirement entirely.
BEACON_TOKEN_TTL_SECONDS = 3

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
    in-app biometric prompt. Returns a short-lived token to broadcast over
    NFC HCE -- see BEACON_TOKEN_TTL_SECONDS above for why this is a
    separate token from the login session JWT rather than reusing it.
    """
    claims = get_jwt()

    # Only students wear/broadcast the check-in beacon; lecturers/admins
    # don't have an attendance record to create.
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    current_user_id = get_jwt_identity()

    # additional_claims={"purpose": "checkin_beacon"} tags this token so the
    # verification endpoint below can reject a normal session token (or any
    # other token type) if one is mistakenly/maliciously submitted there.
    beacon_token = create_access_token(
        identity=str(current_user_id),
        additional_claims={"purpose": "checkin_beacon"},
        expires_delta=timedelta(seconds=BEACON_TOKEN_TTL_SECONDS),
    )

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
    beacon_token = data.get('beacon_token') if data else None
    if not beacon_token:
        return jsonify({"error": "beacon_token is required"}), 400

    # Manually decode instead of @jwt_required(): this token arrives in the
    # request body (relayed by hardware), not as a normal Authorization
    # header from a logged-in client. decode_token() verifies the signature
    # and expiry for us, so an expired or forged beacon is rejected here.
    try:
        decoded = decode_token(beacon_token)
    except Exception:
        return jsonify({"error": "Invalid or expired beacon token"}), 401

    if decoded.get("purpose") != "checkin_beacon":
        return jsonify({"error": "Token is not a valid check-in beacon"}), 401

    student = Student.query.filter_by(user_id=int(decoded["sub"])).first()
    if not student:
        return jsonify({"error": "Student profile not found"}), 404

    # The terminal doesn't know which course it belongs to today, so -- same
    # simplification the existing RFID /attendance flow makes in app.py's
    # get_active_sesh() -- we take the most recently started active session
    # across all courses.
    active_session = SessionModel.query.filter_by(is_active=True).order_by(SessionModel.id.desc()).first()
    if not active_session:
        return jsonify({"error": "No active session"}), 404
#testing something
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
                         status=compute_attendance_status(active_session))
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

    Resolves "the active session" with the EXACT same query
    submit_checkin_beacon uses above -- has to check the same session the
    beacon flow would have targeted, not just any active session.

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

    active_session = SessionModel.query.filter_by(is_active=True).order_by(SessionModel.id.desc()).first()
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
        for entry in timetable_entries:
            course = courses_by_id.get(entry.course_id)
            if course is None:
                continue

            session_today = SessionModel.query.filter_by(
                course_id=entry.course_id, session_date=today
            ).order_by(SessionModel.id.desc()).first()

            status = 'PENDING'
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

            today_protocol.append({
                'course_id': course.id,
                # SCHEMA UPDATE: course_title/course_code.
                'course_name': course.course_title,
                'course_code': course.course_code,
                'status': status,
                'start_time': start_time.strftime('%H:%M') if start_time else None,
                'end_time': end_time.strftime('%H:%M') if end_time else None,
                'room': entry.room,
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
            "announcements": [{
                "id": a.id,
                "title": a.title,
                "body": a.body,
                "scope": a.scope,
                "department_name": a.department.name if a.scope == 'department' and a.department else None,
                "course_code": a.course.course_code if a.scope == 'course' and a.course else None,
                # Same tzinfo-reattach fix as get_notifications() above --
                # MySQL's DATETIME drops the UTC offset on read-back even
                # though this column is always written UTC-aware.
                "created_at": a.created_at.replace(tzinfo=timezone.utc).isoformat(),
            } for a in announcements],
        }), 200

    except Exception:
        return api_error_response("Student Announcements Error", "Failed to load announcements")


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