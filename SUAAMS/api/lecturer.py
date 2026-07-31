from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timezone
from models import db, Lecturer, Course, Session as SessionModel, Attendance, Student, Enrollment, Department
from extensions import limiter, jwt_identity_or_ip, api_error_response

api_lecturer_bp = Blueprint('api_lecturer', __name__, url_prefix='/api/v1/lecturer')


def get_lecturer_or_403():
    """Helper — fetches the lecturer from JWT identity, returns None if unauthorized."""
    claims = get_jwt()
    if claims.get('role') != 'lecturer':
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
        courses = Course.query.filter_by(lecturer_id=lecturer.id).all()

        active_session_count = SessionModel.query.join(Course).filter(
            Course.lecturer_id == lecturer.id,
            SessionModel.is_active == True
        ).count()

        today = datetime.now(timezone.utc).date()
        today_checkins = Attendance.query.join(SessionModel).join(Course).filter(
            Course.lecturer_id == lecturer.id,
            db.func.date(Attendance.time_in) == today
        ).count()

        course_list = []
        for course in courses:
            enrolled_count = Enrollment.query.filter_by(course_id=course.id).count()
            total_sessions = SessionModel.query.filter_by(course_id=course.id).count()
            total_attendance = Attendance.query.join(SessionModel).filter(
                SessionModel.course_id == course.id
            ).count()

            avg_attendance = round(
                (total_attendance / (total_sessions * enrolled_count) * 100)
                if total_sessions and enrolled_count else 0, 1
            )

            active_session = SessionModel.query.filter_by(
                course_id=course.id,
                is_active=True
            ).first()

            course_list.append({
                'id': course.id,
                # SCHEMA FIX: Course has `title`/`code`, not `course_title`/
                # `course_code` -- these would have raised AttributeError on
                # every request (same bug class already fixed this session
                # in blueprints/lecturer.py and blueprints/student.py).
                'title': course.title,
                'code': course.code,
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

@api_lecturer_bp.route('/course/<int:course_id>', methods=['GET'])
@jwt_required()
def get_course_workspace(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = Course.query.filter_by(
            id=course_id,
            lecturer_id=lecturer.id
        ).first()
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        active_session = SessionModel.query.filter_by(
            course_id=course_id,
            is_active=True
        ).first()

        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()
        total_sessions = SessionModel.query.filter_by(course_id=course_id).count()
        total_attendance = Attendance.query.join(SessionModel).filter(
            SessionModel.course_id == course_id
        ).count()

        avg_attendance = round(
            (total_attendance / (total_sessions * enrolled_count) * 100)
            if total_sessions and enrolled_count else 0, 1
        )

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
                    'time_in': time_in.strftime('%H:%M') if time_in else None,
                    'status': att_status,
                })

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.title,
                    "code": course.code,
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
                } if active_session else None,
                "live_attendance": live_attendance,
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
    def _parse_time(value, field_name):
        if not value:
            return None
        try:
            return datetime.strptime(value, '%H:%M').time()
        except ValueError:
            raise ValueError(f"{field_name} must be in HH:MM format")

    try:
        planned_start = _parse_time(data.get('planned_start'), 'planned_start')
        planned_end = _parse_time(data.get('planned_end'), 'planned_end')
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        course = Course.query.filter_by(
            id=course_id,
            lecturer_id=lecturer.id
        ).first()
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        existing = SessionModel.query.filter_by(
            course_id=course_id,
            is_active=True
        ).first()
        if existing:
            return jsonify({"error": "A session is already active for this course."}), 409

        # SCHEMA FIX: Session has no start_time/stop_time columns --
        # passing them here used to raise TypeError at construction time
        # (SQLAlchemy's default __init__ rejects unknown kwargs), meaning
        # starting a session would have failed 100% of the time.
        new_session = SessionModel(
            course_id=course_id,
            session_date=datetime.now(timezone.utc).date(),
            is_active=True,
            planned_start=planned_start,
            planned_end=planned_end,
        )
        db.session.add(new_session)
        db.session.commit()

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
        course = Course.query.filter_by(
            id=course_id,
            lecturer_id=lecturer.id
        ).first()
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        active_session = SessionModel.query.filter_by(
            course_id=course_id,
            is_active=True
        ).first()
        if not active_session:
            return jsonify({"error": "No active session found for this course."}), 404

        # SCHEMA FIX: dropped `active_session.stop_time = ...` -- Session
        # has no such column, so this line used to silently set a plain
        # Python attribute that was never persisted (not an error, just
        # dead code that did nothing).
        active_session.is_active = False
        db.session.commit()

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


# ── 5. Live attendance ────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/live-attendance', methods=['GET'])
@jwt_required()
def get_live_attendance(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        active_session = SessionModel.query.filter_by(
            course_id=course_id,
            is_active=True
        ).first()
        if not active_session:
            return jsonify({"error": "No active session found."}), 404

        # SCHEMA FIX: same Student.department -> Department.name join fix
        # as get_course_workspace above.
        records = db.session.query(
            Student.full_name,
            Student.matric_number,
            Student.level,
            Department.name,
            Attendance.time_in,
            Attendance.status,
        ).join(Attendance, Attendance.student_id == Student.id)\
         .join(Department, Student.department_id == Department.id)\
         .filter(Attendance.session_id == active_session.id)\
         .order_by(Attendance.time_in.asc()).all()

        attendance_list = []
        for full_name, matric, level, dept_name, time_in, att_status in records:
            attendance_list.append({
                'full_name': full_name,
                'matric_number': matric,
                'level': level,
                'department': dept_name,
                'time_in': time_in.strftime('%H:%M') if time_in else None,
                'status': att_status,
            })

        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

        return jsonify({
            "success": True,
            "data": {
                "session_id": active_session.id,
                "present_count": len(attendance_list),
                "enrolled_count": enrolled_count,
                "absent_count": enrolled_count - len(attendance_list),
                "attendance": attendance_list,
            }
        }), 200

    except Exception:
        return api_error_response("Live Attendance API Error", "Failed to load live attendance")


# ── 6. Session history ────────────────────────────────────────────────────────

@api_lecturer_bp.route('/course/<int:course_id>/history', methods=['GET'])
@jwt_required()
def get_session_history(course_id):
    lecturer, error_response, status = get_lecturer_or_403()
    if error_response:
        return error_response, status

    try:
        course = Course.query.filter_by(
            id=course_id,
            lecturer_id=lecturer.id
        ).first()
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
        ).outerjoin(Attendance, Attendance.session_id == SessionModel.id)\
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
                    "title": course.title,
                    "code": course.code,
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
        course = Course.query.filter_by(
            id=course_id,
            lecturer_id=lecturer.id
        ).first()
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
        records = db.session.query(
            Student.full_name,
            Student.matric_number,
            Student.level,
            Department.name,
            Attendance.time_in,
            Attendance.status,
        ).join(Attendance, Attendance.student_id == Student.id)\
         .join(Department, Student.department_id == Department.id)\
         .filter(Attendance.session_id == session_id).all()

        attendance_list = []
        for full_name, matric, level, dept_name, time_in, att_status in records:
            attendance_list.append({
                'full_name': full_name,
                'matric_number': matric,
                'level': level,
                'department': dept_name,
                'time_in': time_in.strftime('%H:%M') if time_in else None,
                'status': att_status,
            })

        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

        return jsonify({
            "success": True,
            "data": {
                "course": {
                    "id": course.id,
                    "title": course.title,
                    "code": course.code,
                },
                "session": {
                    "id": session.id,
                    "date": session.session_date.strftime('%d %b %Y') if session.session_date else None,
                    # SCHEMA FIX: dropped redundant/nonexistent start_time/
                    # stop_time keys -- planned_start/planned_end below are
                    # the only real time fields on Session.
                    "planned_start": str(session.planned_start) if session.planned_start else None,
                    "planned_end": str(session.planned_end) if session.planned_end else None,
                },
                "stats": {
                    "present_count": len(attendance_list),
                    "absent_count": enrolled_count - len(attendance_list),
                    "enrolled_count": enrolled_count,
                },
                "attendance": attendance_list,
            }
        }), 200

    except Exception:
        return api_error_response("Session Detail API Error", "Failed to load session detail")
