from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from datetime import datetime, timezone
from models import db, Lecturer, Course, Session as SessionModel, Attendance, Student, Enrollment, Department, Announcement
from extensions import limiter, jwt_identity_or_ip, api_error_response
from utils import resolve_timetable_slot_for_course

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

        # Mirrors blueprints/lecturer.py's web start_session(): if the
        # client didn't send explicit times, fall back to today's Timetable
        # slot for this course instead of recording NULL.
        if planned_start is None and planned_end is None:
            slot = resolve_timetable_slot_for_course(course_id)
            if slot:
                planned_start = slot.start_time
                planned_end = slot.end_time

        # STALE COMMENT FIX: this used to say Session had no start_time/
        # stop_time columns and that passing them would raise TypeError --
        # both columns do exist (models.py: "RE-ADDED: actual start/stop
        # timestamps"), they were just never being written from here.
        # Populating start_time now so this session's elapsed time can be
        # computed the same way blueprints/lecturer.py's web start_session()
        # (and the lecturer web portal's Active Sessions page) already do.
        new_session = SessionModel(
            course_id=course_id,
            session_date=datetime.now(timezone.utc).date(),
            is_active=True,
            start_time=datetime.now(timezone.utc).time(),
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

        # STALE COMMENT FIX: this used to say Session had no stop_time
        # column and dropped the assignment as dead code -- the column does
        # exist (models.py: "RE-ADDED: actual start/stop timestamps"), it
        # was just never being written from here. Same gap existed on the
        # web side (blueprints/lecturer.py's end_session_r) and has now
        # been fixed there too, so both surfaces record a real stop time.
        active_session.is_active = False
        active_session.stop_time = datetime.now(timezone.utc).time()
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
        course = Course.query.filter_by(id=course_id, lecturer_id=lecturer.id).first()
        if not course:
            return jsonify({"error": "Course not found or access denied."}), 404

        enrollments = Enrollment.query.filter_by(course_id=course_id).all()
        enrolled_count = len(enrollments)

        sessions = (
            SessionModel.query
            .filter_by(course_id=course_id, is_active=False)
            .order_by(SessionModel.session_date.asc())
            .all()
        )
        total_sessions = len(sessions)

        # Chronological trend -- one point per completed session.
        trend = []
        pct_sum = 0.0
        for session in sessions:
            present_count = Attendance.query.filter_by(session_id=session.id).count()
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

        students = []
        for enrollment in enrollments:
            student = Student.query.get(enrollment.student_id)
            if student is None:
                continue
            attended = Attendance.query.join(SessionModel).filter(
                SessionModel.course_id == course_id,
                SessionModel.is_active == False,
                Attendance.student_id == student.id,
            ).count()
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
        course_ids = [c.id for c in Course.query.filter_by(lecturer_id=lecturer.id).all()]
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
                'created_at': a.created_at.strftime('%d %b %Y, %H:%M') if a.created_at else None,
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
        course = Course.query.filter_by(id=course_id, lecturer_id=lecturer.id).first()
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

        return jsonify({"success": True, "message": "Announcement posted."}), 201

    except Exception:
        db.session.rollback()
        return api_error_response("Create Announcement API Error", "Failed to post announcement")


@api_lecturer_bp.route('/announcements/<int:announcement_id>', methods=['DELETE'])
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
