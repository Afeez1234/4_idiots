# Moved out of app.py -- these are the ESP32-facing routes (RFID attendance
# capture + active-session lookups), structurally the same kind of
# "hardware/JSON API blueprint" that api/auth.py and api/student.py already
# are for the mobile app, just never migrated when those were extracted.
# No url_prefix here (unlike api/auth.py's '/api/v1/auth' or
# api/student.py's '/api/v1/student') -- the ESP32 firmware has
# `https://suaams.onrender.com/attendance` hardcoded, so these routes must
# keep their exact original paths.
from flask import Blueprint, request, jsonify, redirect, url_for
from models import db, Student, Session, Enrollment, Attendance
from extensions import limiter
from utils import compute_attendance_status

api_hardware_bp = Blueprint('api_hardware', __name__)


def find_student_by_rfid(rfid_uid):
    return Student.query.filter_by(rfid_uid=rfid_uid).first()

def record_attendance(student_id, session):
    record = Attendance(student_id=student_id, session_id=session.id,
                         status=compute_attendance_status(session))
    db.session.add(record)
    db.session.commit()

def get_all_active_sessions():
    return Session.query.filter_by(is_active=True).all()

def get_active_sesh():
    return Session.query.filter_by(is_active=True).order_by(Session.id.desc()).first()

def did_student_register_course(student_id, course_id):
    return Enrollment.query.filter_by(
        student_id=student_id,
        course_id=course_id
    ).first() is not None

def attendance_already_recorded(session_id, student_id):
    return Attendance.query.filter_by(
        session_id=session_id,
        student_id=student_id
    ).first() is not None


@api_hardware_bp.route('/')
def home():
    return redirect(url_for('auth.login'))

@api_hardware_bp.route('/sessions/active', methods=['GET'])
def get_active_sessions():
    sessions = get_all_active_sessions()
    active_sessions = []
    for s in sessions:
        active_sessions.append({
            "id": s.id,
            "course_id": s.course_id,
            "start_time": str(s.planned_start),
            "stop_time": str(s.planned_end),
            "session_date": str(s.session_date)
        })
    return jsonify({"success": True, "active_sessions": active_sessions}), 200

@api_hardware_bp.route('/sessions/active/<int:course_id>', methods=['GET'])
def get_active_sessions_by_course_id(course_id):
    session = Session.query.filter_by(
        is_active=True,
        course_id=course_id
    ).order_by(Session.id.desc()).first()

    if not session:
        return jsonify({"error": "No active session found for the given course_id."}), 404

    return jsonify({
        "success": True,
        "session": {
            "id": session.id,
            "course_id": session.course_id,
            "start_time": str(session.planned_start),
            "stop_time": str(session.planned_end),
            "session_date": str(session.session_date)
        }
    }), 200

# Same reasoning as /api/v1/student/checkin in api/student.py: this is an
# unauthenticated, ESP32-facing endpoint (no JWT to key by), so it's rate
# limited per-IP. One reader posting a stream of card taps stays well under
# 30/minute; this mainly caps abuse/DoS against an endpoint anyone can hit.
#
# No @csrf.exempt needed here anymore -- app.py now exempts the whole
# api_hardware_bp blueprint in one call, the same way it already does for
# api_auth_bp/api_student_bp, instead of a one-off decorator on this route.
@api_hardware_bp.route('/attendance', methods=['POST'])
@limiter.limit("30 per minute")
def attendance():
    data = request.get_json()
    RFID_UID = data.get('RFID_UID')
    if not RFID_UID:
        return jsonify({"error": "RFID_UID is required"}), 400

    student = find_student_by_rfid(RFID_UID)
    if not student:
        return jsonify({"error": "No student found with that RFID UID."}), 404

    active_session = get_active_sesh()
    if not active_session:
        return jsonify({"error": "No active session"}), 404

    if not did_student_register_course(student.id, active_session.course_id):
        return jsonify({"error": "Student did not register this course"}), 400

    if attendance_already_recorded(active_session.id, student.id):
        return jsonify({"message": "Attendance already marked"}), 200

    record_attendance(student.id, active_session)

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully.",
        "student": {
            "id": student.id,
            "full_name": student.full_name,
            "level": student.level,
            "department": student.department.name if student.department else None
        }
    }), 200
