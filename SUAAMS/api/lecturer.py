from campus_time import campus_fmt
from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timezone
from models import db, Lecturer, Course, Session as SessionModel, Attendance, Student, Enrollment, Department, Announcement, Timetable
from extensions import limiter, jwt_identity_or_ip, api_error_response
from utils import (build_course_register_csv, start_class_session, end_class_session,
                   taught_course, courses_taught_by, teaches, current_courses, current_slot_filter,
                   students_not_checked_in, mark_student_present,
                   pending_offline_taps, review_offline_tap, accept_all_offline_taps,
                   notify_announcement, course_attendance, ATTENDED_STATUSES,
                   attended_by_session, attended_by_student,
                   resolve_timetable_slot_for_course)
import terminal_rooms

api_lecturer_bp = Blueprint('api_lecturer', __name__, url_prefix='/api/v1/lecturer')


def get_lecturer_or_403():
    """
    Helper — fetches the lecturer from JWT identity, returns None if
    unauthorized. Accepts role 'hod' too, matching login_required(('lecturer',
    'hod')) on the web side (blueprints/lecturer.py) -- an HOD who was
    promoted from an existing Lecturer account (see hods_page's
    action == 'promote_lecturer' in blueprints/admin.py) keeps that Lecturer
    profile row, and without this they'd lose mobile access to their own
    course workspace/session start-stop the moment they got promoted, even
    though the web dashboard already keeps working for them.
    """
    claims = get_jwt()
    if claims.get('role') not in ('lecturer', 'hod'):
        return None, jsonify({"error": "Unauthorized access. Lecturers only."}), 403
    current_user_id = int(get_jwt_identity())
    lecturer = Lecturer.query.filter_by(user_id=current_user_id).first()
    if not lecturer:
        return None, jsonify({"error": "Lecturer profile not found."}), 404
    return lecturer, None, None


# ── 1. Dashboard ──────────────────────────────────────────────────────────────

@api_lecturer_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_lecturer_dashboard():
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        # This semester's courses: courses_taught_by is every course they
        # have ever taught, and last year's would sit beside this year's.
        courses = current_courses(courses_taught_by(lecturer)).all()

        active_session_count = SessionModel.query.join(Course).filter(
            teaches(lecturer),
            SessionModel.is_active == True
        ).count()

        today = datetime.now(timezone.utc).date()
        today_checkins = Attendance.query.join(SessionModel).join(Course).filter(
            teaches(lecturer),
            db.func.date(Attendance.time_in) == today
        ).count()

        # The shared attendance rule (finished classes, present or late), for
        # every course in a few grouped queries rather than three per course.
        stats = course_attendance([c.id for c in courses])

        course_list = []
        for course in courses:
            enrolled_count = stats[course.id]['enrolled']
            total_sessions = stats[course.id]['held']
            avg_attendance = stats[course.id]['pct']

            active_session = SessionModel.query.filter_by(
                course_id=course.id,
                is_active=True
            ).first()

            course_list.append({
                'id': course.id,
                # SCHEMA UPDATE: Course columns renamed title/code ->
                # course_title/course_code in the v2 schema redesign. JSON
                # key names ('title'/'code') stay as-is -- only the ORM
                # attribute read changes -- so the Flutter side needs no
                # changes for this rename.
                'title': course.course_title,
                'code': course.course_code,
                'enrolled_count': enrolled_count,
                'total_sessions': total_sessions,
                'avg_attendance': avg_attendance,
                'has_active_session': active_session is not None,
                'active_session_id': active_session.id if active_session else None,
            })

        return jsonify({
            "success": True,
            "data": {
                "lecturer": {
                    "full_name": lecturer.full_name,
                    "staff_id": lecturer.staff_id,
                    # SCHEMA FIX: Lecturer.department is a relationship to a
                    # Department object, not a string -- jsonify() can't
                    # serialize it directly (same bug class as the
                    # student.department fix earlier this session).
                    "department": lecturer.department.name if lecturer.department else None,
                },
                "stats": {
                    "total_courses": len(courses),
                    "active_sessions": active_session_count,
                    "today_checkins": today_checkins,
                },
                "courses": course_list,
            }
        }), 200

    except Exception:
        # SECURITY FIX: was print(f"...: {e}") + jsonify({..., "details":
        # str(e)}) -- leaked raw exception text (can include DB schema/
        # column names) to the API caller. api_error_response logs the full
        # exception + traceback server-side and returns only a generic
        # message, consistent with every other mobile API route.
        return api_error_response("Lecturer Dashboard API Error", "Failed to load dashboard")


# ── 2. Course workspace ───────────────────────────────────────────────────────

@api_lecturer_bp.route('/schedule/week', methods=['GET'])
@limiter.limit("30 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def get_lecturer_week_schedule():
    """
    The lecturer's own recurring weekly Timetable, across every course they
    are assigned to teach.

    Mirrors get_week_schedule in api/student.py exactly -- same JSON keys,
    same ordering, same 0=Monday day_of_week convention -- so the Flutter
    side reuses WeekScheduleEntry and the day-tile UI unchanged. The only
    difference is the filter: a student gets the courses they are enrolled
    in, a lecturer the courses assigned to them.

    Without this a lecturer could see their courses and their live sessions
    but never their own week, which is the one question the app exists to
    help them answer.
    """
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        # This semester's courses and slots only (see current_courses).
        courses_by_id = {
            c.id: c for c in current_courses(courses_taught_by(lecturer)).all()
        }
        if not courses_by_id:
            return jsonify({"success": True, "week": []}), 200

        entries = Timetable.query.filter(
            Timetable.course_id.in_(courses_by_id.keys()),
            Timetable.is_published.is_(True),  # drafts stay hidden until published
            *[f for f in [current_slot_filter()] if f is not None],
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


@api_lecturer_bp.route('/course/<int:course_id>', methods=['GET'])
@jwt_required()
def get_course_workspace(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        active_session = SessionModel.query.filter_by(
            course_id=course_id,
            is_active=True
        ).first()

        # The shared attendance rule: finished classes, present or late.
        course_stats = course_attendance([course_id])[course_id]
        enrolled_count = course_stats['enrolled']
        total_sessions = course_stats['held']
        avg_attendance = course_stats['pct']

        live_attendance = []
        if active_session:
            # SCHEMA FIX: Student.department is a relationship, not a
            # column -- selecting it directly in this tuple-query's column
            # list (as the original draft did) is invalid query
            # construction, not just a serialization problem. Joining
            # Department explicitly and selecting Department.name instead.
            records = db.session.query(
                Student.full_name,
                Student.matric_number,
                Student.level,
                Department.name,
                Attendance.time_in,
                Attendance.status,
            ).join(Attendance, Attendance.student_id == Student.id)\
             .join(Department, Student.department_id == Department.id)\
             .filter(Attendance.session_id == active_session.id).all()

            for full_name, matric, level, dept_name, time_in, att_status in records:
                live_attendance.append({
                    'full_name': full_name,
                    'matric_number': matric,
                    'level': level,
                    'department': dept_name,
                    'time_in': campus_fmt(time_in) if time_in else None,
                    'status': att_status,
                })

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    # SCHEMA UPDATE: course_title/course_code (see comment
                    # in get_dashboard_data above).
                    "title": course.course_title,
                    "code": course.course_code,
                },
                "stats": {
                    "enrolled_count": enrolled_count,
                    "total_sessions": total_sessions,
                    "avg_attendance": avg_attendance,
                    "present_now": len(live_attendance),
                },
                "active_session": {
                    "id": active_session.id,
                    # SCHEMA FIX: Session has no start_time/stop_time
                    # columns, only planned_start/planned_end -- dropped the
                    # redundant/nonexistent start_time key, planned_start/
                    # planned_end below are the only real time fields.
                    "planned_start": str(active_session.planned_start) if active_session.planned_start else None,
                    "planned_end": str(active_session.planned_end) if active_session.planned_end else None,
                    "session_date": str(active_session.session_date),
                    # Where the class is (given at start, else its slot's);
                    # readers in another room are flagged against it.
                    "room": terminal_rooms.class_room(active_session),
                } if active_session else None,
                "live_attendance": live_attendance,
                # Today's timetable room, to pre-fill the start screen's Room
                # field. None with a class running or no slot today.
                "today_room": None if active_session else getattr(
                    resolve_timetable_slot_for_course(course_id), 'room', None),
            }
        }), 200

    except Exception:
        return api_error_response("Course Workspace API Error", "Failed to load course workspace")


# ── 3. Start session ──────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/start-session', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def start_session(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    data = request.get_json() or {}

    # BUG FIX: the request sends planned_start/planned_end as "HH:MM"
    # strings, but Session.planned_start/planned_end are db.Time columns.
    # Passing the raw string straight into the constructor (as this draft
    # and blueprints/lecturer.py's web version both did) raises a hard
    # TypeError against SQLite, and isn't correct SQLAlchemy usage
    # regardless of whether a given MySQL driver happens to coerce it
    # silently. Parsing explicitly here so this works regardless of
    # backend -- confirmed by testing against a real SQLite DB.
    # Returns (value, error_message) instead of raising -- avoids the
    # str(e)-on-a-caught-exception pattern flagged elsewhere in this
    # codebase (api/auth.py, api/student.py, blueprints/lecturer.py all have
    # "SECURITY FIX" comments removing that pattern), even though the
    # message here was always self-authored and never leaked anything from
    # the exception itself.
    def _parse_time(value, field_name):
        if not value:
            return None, None
        try:
            return datetime.strptime(value, '%H:%M').time(), None
        except ValueError:
            return None, f"{field_name} must be in HH:MM format"

    planned_start, error_message = _parse_time(data.get('planned_start'), 'planned_start')
    if error_message is None:
        planned_end, error_message = _parse_time(data.get('planned_end'), 'planned_end')
    if error_message:
        return jsonify({"error": error_message}), 400

    try:
        # Ownership check, "already running?" and the timetable fallback
        # all live in utils.start_class_session, shared with the web portal.
        # Any of the course's lecturers can start it; it records which one.
        # Optional: where the class actually is, if not its timetable room.
        room = data.get('room') if isinstance(data.get('room'), str) else None
        outcome, new_session = start_class_session(lecturer, course_id, planned_start, planned_end, room)
        if outcome == 'not_found':
            return jsonify({"error": "Course not found or access denied."}), 404
        if outcome == 'already_active':
            return jsonify({"error": "A session is already active for this course."}), 409
        if outcome == 'past_semester':
            course = Course.query.get(course_id)
            return jsonify({"error": f"{course.course_code} belongs to {course.semester.name if course.semester else 'another semester'}, not the current semester, so a class can't be started on it."}), 409

        return jsonify({
            "success": True,
            "message": "Session started successfully.",
            "session": {
                "id": new_session.id,
                "planned_start": str(new_session.planned_start) if new_session.planned_start else None,
                "session_date": str(new_session.session_date),
            }
        }), 201

    except Exception:
        db.session.rollback()
        return api_error_response("Start Session API Error", "Failed to start session.")


# ── 4. End session ────────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/end-session', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def end_session(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        # Shared with the web portal; closes every running session for the
        # course, so a duplicate can never be left open (see utils).
        outcome, active_session = end_class_session(lecturer, course_id)
        if outcome == 'not_found':
            return jsonify({"error": "Course not found or access denied."}), 404
        if outcome == 'none_active':
            return jsonify({"error": "No active session found for this course."}), 404

        final_count = Attendance.query.filter_by(
            session_id=active_session.id
        ).count()

        return jsonify({
            "success": True,
            "message": "Session ended successfully.",
            "summary": {
                "session_id": active_session.id,
                "total_present": final_count,
            }
        }), 200

    except Exception:
        db.session.rollback()
        return api_error_response("End Session API Error", "Failed to end session.")


# ── 6. Session history ────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/history', methods=['GET'])
@jwt_required()
def get_session_history(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

        # SCHEMA FIX: SessionModel.start_time/stop_time -> planned_start/
        # planned_end (no start_time/stop_time columns exist).
        history = db.session.query(
            SessionModel.id,
            SessionModel.session_date,
            SessionModel.planned_start,
            SessionModel.planned_end,
            db.func.count(Attendance.id)
        ).outerjoin(Attendance, (Attendance.session_id == SessionModel.id)
                    & Attendance.status.in_(ATTENDED_STATUSES))\
         .filter(
             SessionModel.course_id == course_id,
             SessionModel.is_active == False
         )\
         .group_by(SessionModel.id)\
         .order_by(SessionModel.session_date.desc()).all()

        sessions = []
        for session_id, session_date, planned_start, planned_end, present_count in history:
            sessions.append({
                'session_id': session_id,
                'date': session_date.strftime('%d %b %Y') if session_date else None,
                'planned_start': str(planned_start) if planned_start else None,
                'planned_end': str(planned_end) if planned_end else None,
                'present_count': present_count,
                'absent_count': enrolled_count - present_count,
                'enrolled_count': enrolled_count,
            })

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.course_title,
                    "code": course.course_code,
                },
                "sessions": sessions,
            }
        }), 200

    except Exception:
        return api_error_response("Session History API Error", "Failed to load session history")


# ── 7. Session detail ─────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/session/<int:session_id>', methods=['GET'])
@jwt_required()
def get_session_detail(course_id, session_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        session = SessionModel.query.filter_by(
            id=session_id,
            course_id=course_id
        ).first()
        if not session:
            return jsonify({"error": "Session not found."}), 404

        # SCHEMA FIX: same Student.department -> Department.name join fix
        # as get_course_workspace/get_live_attendance above.
        # student_id and method added for manual marking: the app needs the
        # id to act on a student, and shows the method so a lecturer can
        # tell a tap (nfc) from a Bluetooth code (ble) from a hand mark
        # (manual).
        records = db.session.query(
            Student.id,
            Student.full_name,
            Student.matric_number,
            Student.level,
            Department.name,
            Attendance.time_in,
            Attendance.status,
            Attendance.method,
            Attendance.wrong_room,
        ).join(Attendance, Attendance.student_id == Student.id)\
         .join(Department, Student.department_id == Department.id)\
         .filter(Attendance.session_id == session_id).all()

        attendance_list = []
        for student_id, full_name, matric, level, dept_name, time_in, att_status, method, wrong_room in records:
            attendance_list.append({
                'student_id': student_id,
                'full_name': full_name,
                'matric_number': matric,
                'level': level,
                'department': dept_name,
                'time_in': campus_fmt(time_in) if time_in else None,
                'status': att_status,
                'method': method,
                # True = checked in at a reader in another room (flag mode;
                # see terminal_rooms.py). False otherwise.
                'wrong_room': bool(wrong_room),
            })

        # Enrolled students with no record yet -- the ones a lecturer can
        # mark present by hand (see mark_present below).
        not_checked_in = [
            {
                'student_id': s.id,
                'full_name': s.full_name,
                'matric_number': s.matric_number,
            }
            for s in students_not_checked_in(session)
        ]

        # Taps the terminal read while it couldn't reach the server, waiting
        # for the lecturer to accept or reject (see review_offline_tap).
        # tapped_at is when the student actually tapped, in campus time.
        offline_taps = [
            {
                'id': log.id,
                'student_id': log.student_id,
                'full_name': log.student.full_name,
                'matric_number': log.student.matric_number,
                'tapped_at': campus_fmt(log.captured_at, '%H:%M:%S'),
                'terminal_id': log.terminal_id,
                # Read by a reader in another room (terminal_rooms.py).
                'wrong_room': bool(log.wrong_room),
            }
            for log in pending_offline_taps(session)
        ]

        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.course_title,
                    "code": course.course_code,
                },
                "session": {
                    "id": session.id,
                    "date": session.session_date.strftime('%d %b %Y') if session.session_date else None,
                    # SCHEMA FIX: dropped redundant/nonexistent start_time/
                    # stop_time keys -- planned_start/planned_end below are
                    # the only real time fields on Session.
                    "planned_start": str(session.planned_start) if session.planned_start else None,
                    "planned_end": str(session.planned_end) if session.planned_end else None,
                    # Lets the app label the screen live vs. ended; manual
                    # marking itself is allowed on both.
                    "is_active": bool(session.is_active),
                },
                "stats": {
                    "present_count": len(attendance_list),
                    "absent_count": enrolled_count - len(attendance_list),
                    "enrolled_count": enrolled_count,
                },
                "attendance": attendance_list,
                "not_checked_in": not_checked_in,
                "offline_taps": offline_taps,
            }
        }), 200

    except Exception:
        return api_error_response("Session Detail API Error", "Failed to load session detail")


# ── 7b. Manual marking ────────────────────────────────────────────────────────

# Keyed by lecturer, generous enough to work through a whole class whose
# terminal failed, while still capping a runaway client.
@api_lecturer_bp.route('/course/<int:course_id>/session/<int:session_id>/mark-present', methods=['POST'])
@limiter.limit("60 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def mark_present(course_id, session_id):
    """
    Mark one student present by hand -- the fallback when a student's phone
    can't check in. Works on live and ended sessions (register corrections
    after class). The rules live in utils.mark_student_present, shared with
    the web dashboard.

    Body: {"student_id": <int>}
    """
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    data = request.get_json(silent=True) or {}
    student_id = data.get('student_id')
    # bool is a subclass of int in Python, so `true` would otherwise pass.
    if not isinstance(student_id, int) or isinstance(student_id, bool):
        return jsonify({"error": "student_id must be an integer"}), 400

    try:
        # Ownership: only the course's own lecturer may vouch for presence.
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        session = SessionModel.query.filter_by(id=session_id, course_id=course_id).first()
        if not session:
            return jsonify({"error": "Session not found."}), 404

        outcome = mark_student_present(session, student_id, lecturer.user)
        if outcome == 'not_enrolled':
            return jsonify({"error": "That student isn't registered for this course."}), 400
        if outcome == 'already_marked':
            return jsonify({"success": True, "message": "Already marked for this session."}), 200
        return jsonify({"success": True, "message": "Marked present."}), 200

    except Exception:
        db.session.rollback()
        return api_error_response("Mark Present API Error", "Failed to mark student present.")


# ── 7c. Offline tap review ───────────────────────────────────────────────────

def _owned_session_or_404(lecturer, course_id, session_id):
    """(session, None) if the lecturer owns the course and the session is in
    it, else (None, (response, status)). Same ownership rule as mark_present."""
    course = taught_course(lecturer, course_id)
    if not course:
        return None, (jsonify({"error": "Course not found or access denied."}), 404)
    session = SessionModel.query.filter_by(id=session_id, course_id=course_id).first()
    if not session:
        return None, (jsonify({"error": "Session not found."}), 404)
    return session, None


@api_lecturer_bp.route('/course/<int:course_id>/session/<int:session_id>/offline-taps/<int:tap_id>/review',
                       methods=['POST'])
@limiter.limit("60 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def review_offline_tap_api(course_id, session_id, tap_id):
    """
    Accept or reject one tap a terminal read while it was offline. Accepting
    creates attendance with method='offline' at the time of the tap. Rules
    live in utils.review_offline_tap, shared with the web dashboard.

    Body: {"accept": true | false}
    """
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    data = request.get_json(silent=True) or {}
    accept = data.get('accept')
    if not isinstance(accept, bool):
        return jsonify({"error": "accept must be true or false"}), 400

    try:
        session, failure = _owned_session_or_404(lecturer, course_id, session_id)
        if failure:
            return failure

        outcome = review_offline_tap(session, tap_id, lecturer.user, accept)
        if outcome == 'not_found':
            return jsonify({"error": "That tap isn't part of this session."}), 404
        messages = {
            'accepted': "Tap accepted.",
            'rejected': "Tap rejected.",
            'already_marked': "Student already has attendance for this session.",
            'already_reviewed': "That tap was already reviewed.",
            'not_enrolled': "Student is no longer registered for this course, so the tap was rejected.",
        }
        return jsonify({"success": True, "outcome": outcome, "message": messages[outcome]}), 200

    except Exception:
        db.session.rollback()
        return api_error_response("Offline Tap Review API Error", "Failed to review the tap.")


@api_lecturer_bp.route('/course/<int:course_id>/session/<int:session_id>/offline-taps/accept-all',
                       methods=['POST'])
@limiter.limit("20 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def accept_all_offline_taps_api(course_id, session_id):
    """Accept every pending offline tap for the session. See
    utils.accept_all_offline_taps for why bulk acceptance is safe."""
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        session, failure = _owned_session_or_404(lecturer, course_id, session_id)
        if failure:
            return failure

        counts = accept_all_offline_taps(session, lecturer.user)
        accepted = counts.get('accepted', 0)
        return jsonify({
            "success": True,
            "accepted": accepted,
            "counts": counts,
            "message": f"Accepted {accepted} tap{'s' if accepted != 1 else ''}.",
        }), 200

    except Exception:
        db.session.rollback()
        return api_error_response("Accept All Offline Taps API Error", "Failed to accept the taps.")


# ── 8. Course analytics ───────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/analytics', methods=['GET'])
@jwt_required()
def get_course_analytics(course_id):
    """
    Summary stats + a chronological attendance-percentage trend across
    sessions + a per-student breakdown (sorted ascending by pct, so the
    most at-risk students surface first). Only considers completed
    sessions (is_active=False), same scoping as get_session_history above.
    """
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        # PERF: this used to run one query per session and two per student
        # (load the student, count their attendance) -- about 415 queries
        # for a 200-student course after 15 sessions, every time the screen
        # opened. Now four queries, whatever the size. Same numbers.
        enrolled_students = (
            Student.query
            .join(Enrollment, Enrollment.student_id == Student.id)
            .filter(Enrollment.course_id == course_id)
            .all()
        )
        enrolled_count = len(enrolled_students)

        sessions = (
            SessionModel.query
            .filter_by(course_id=course_id, is_active=False)
            .order_by(SessionModel.session_date.asc())
            .all()
        )
        total_sessions = len(sessions)

        # Present count per completed session. The shared attendance rule
        # (utils), not a copy of it: this endpoint used to write both of
        # these queries out by hand.
        present_by_session = attended_by_session([course_id])

        # Chronological trend -- one point per completed session.
        trend = []
        pct_sum = 0.0
        for session in sessions:
            present_count = present_by_session.get(session.id, 0)
            pct = round((present_count / enrolled_count * 100) if enrolled_count else 0, 1)
            pct_sum += pct
            trend.append({
                'session_id': session.id,
                'date': session.session_date.strftime('%d %b %Y') if session.session_date else None,
                'present_count': present_count,
                'enrolled_count': enrolled_count,
                'pct': pct,
            })

        # Average of each session's own pct (not total-present /
        # total-possible) -- matches what the trend line itself shows.
        avg_attendance = round(pct_sum / total_sessions, 1) if total_sessions else 0

        # Completed sessions attended per student, in one grouped query.
        attended_map = attended_by_student([course_id])

        students = []
        for student in enrolled_students:
            attended = attended_map.get((student.id, course_id), 0)
            pct = round((attended / total_sessions * 100) if total_sessions else 0, 1)
            students.append({
                'student_id': student.id,
                'full_name': student.full_name,
                'matric_number': student.matric_number,
                'attended': attended,
                'total': total_sessions,
                'pct': pct,
            })
        students.sort(key=lambda s: s['pct'])

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.course_title,
                    "code": course.course_code,
                },
                "summary": {
                    "enrolled_count": enrolled_count,
                    "total_sessions": total_sessions,
                    "avg_attendance": avg_attendance,
                },
                "trend": trend,
                "students": students,
            }
        }), 200

    except Exception:
        return api_error_response("Course Analytics API Error", "Failed to load course analytics")


@api_lecturer_bp.route('/course/<int:course_id>/export', methods=['GET'])
@jwt_required()
def export_course_register(course_id):
    """Per-student attendance register CSV for one course (exam eligibility list)."""
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        # Ownership check: a lecturer may only export their own courses.
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        csv_text = build_course_register_csv(course)
        filename = f"{course.course_code}_attendance_register.csv".replace(' ', '_')
        return Response(
            csv_text,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename={filename}'},
        )

    except Exception:
        return api_error_response("Course Register Export API Error", "Failed to export attendance register")


# ── 9. Announcements ──────────────────────────────────────────────────────────
# Deliberately scoped to scope='course' only -- a lecturer posting to their
# own course's students, not university- or department-wide (those stay
# admin-only, see blueprints/admin.py's announcements_page). Keeps a
# lecturer from broadcasting outside what they actually own.

@api_lecturer_bp.route('/announcements', methods=['GET'])
@jwt_required()
def get_lecturer_announcements():
    """All course-scoped announcements the lecturer has posted, across all
    of their courses, newest first."""
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course_ids = [c.id for c in courses_taught_by(lecturer).all()]
        if not course_ids:
            return jsonify({"success": True, "data": []}), 200

        announcements = (
            Announcement.query
            .filter(
                Announcement.course_id.in_(course_ids),
                Announcement.scope == 'course',
                Announcement.is_active == True,  # noqa: E712 -- SQLAlchemy comparator, not a Python bool check
            )
            .order_by(Announcement.created_at.desc())
            .all()
        )

        courses_by_id = {c.id: c for c in Course.query.filter(Course.id.in_(course_ids)).all()}

        data = []
        for a in announcements:
            course = courses_by_id.get(a.course_id)
            data.append({
                'id': a.id,
                'title': a.title,
                'body': a.body,
                'course_id': a.course_id,
                'course_code': course.course_code if course else None,
                'created_at': campus_fmt(a.created_at, '%d %b %Y, %H:%M') if a.created_at else None,
            })

        return jsonify({"success": True, "data": data}), 200

    except Exception:
        return api_error_response("Lecturer Announcements API Error", "Failed to load announcements")


@api_lecturer_bp.route('/course/<int:course_id>/announcements', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def create_lecturer_announcement(course_id):
    """Posts a course-scoped announcement, visible to that course's
    enrolled students. sender_id is the lecturer's own User row."""
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = taught_course(lecturer, course_id)
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        payload = request.get_json(silent=True) or {}
        title = (payload.get('title') or '').strip()
        body = (payload.get('body') or '').strip()

        if not title or not body:
            return jsonify({"error": "Title and body are both required."}), 400

        announcement = Announcement(
            title=title,
            body=body,
            sender_id=lecturer.user_id,
            scope='course',
            course_id=course.id,
        )
        db.session.add(announcement)
        db.session.commit()

        # Same notification as the web portal's version. This route used to
        # save the announcement and stop, so posting from the app reached no
        # one's notifications.
        notify_announcement(announcement)

        return jsonify({"success": True, "message": "Announcement posted."}), 201

    except Exception:
        db.session.rollback()
        return api_error_response("Create Announcement API Error", "Failed to post announcement")


@api_lecturer_bp.route('/announcements/<int:announcement_id>', methods=['DELETE'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def delete_lecturer_announcement(announcement_id):
    """Soft-delete (is_active=False), scoped to sender_id -- a lecturer can
    only delete their own posted announcements. Mirrors the web equivalent
    in blueprints/lecturer.py; admin's version in blueprints/admin.py has no
    ownership check since admin can delete any announcement."""
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        announcement = Announcement.query.filter_by(
            id=announcement_id, sender_id=lecturer.user_id
        ).first()
        if not announcement:
            return jsonify({"error": "Announcement not found or access denied."}), 404

        announcement.is_active = False
        db.session.commit()

        return jsonify({"success": True, "message": "Announcement deleted."}), 200

    except Exception:
        db.session.rollback()
        return api_error_response("Delete Announcement API Error", "Failed to delete announcement")
