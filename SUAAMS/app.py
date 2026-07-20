from flask import Flask, request, jsonify, redirect, url_for
from datetime import date, timedelta
from flask_migrate import Migrate
import os
import logging
from flask_jwt_extended import JWTManager
from models import db
from extensions import limiter, csrf
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.lecturer import lecturer_bp
from blueprints.student import student_bp
from api.auth import api_auth_bp
from api.student import api_student_bp

# Gives the "suaams" logger (see extensions.py's log_exception/
# api_error_response) an actual handler + format. Without this, exceptions
# logged via logger.exception() still surface (Python's logging module logs
# WARNING+ to stderr by default even unconfigured), but without timestamps
# or a named source -- this makes server-side logs actually readable when
# debugging a reported issue, instead of just a bare traceback.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
)

SECRET_KEY = os.environ.get('SECRET_KEY')
JWT_SECRET = os.environ.get('JWT_SECRET_KEY')

# Database connection string for SQLAlchemy
DB_HOST = os.environ.get('DB_HOST')
DB_USER = os.environ.get('DB_USER')
DB_PASSWORD = os.environ.get('DB_PASSWORD')
DB_NAME = os.environ.get('DB_NAME')
DB_PORT = os.environ.get('DB_PORT', '3306')

_required = {
    'SECRET_KEY': SECRET_KEY, 'JWT_SECRET_KEY': JWT_SECRET, 'DB_HOST': DB_HOST,
    'DB_USER': DB_USER, 'DB_PASSWORD': DB_PASSWORD, 'DB_NAME': DB_NAME,
}
_missing = [k for k, v in _required.items() if not v]
if _missing:
    raise RuntimeError(
        f"Missing required environment variables: {', '.join(_missing)}. "
        "Set them in your environment or a local .env — do not hardcode credentials in source."
    )

app = Flask(__name__)

# Core config
app.secret_key = SECRET_KEY
app.config['JWT_SECRET_KEY'] = JWT_SECRET

# Explicit JWT lifetimes -- previously unset, which silently rode on
# Flask-JWT-Extended's built-in 15-minute access-token default with no
# refresh token at all. Now explicit and paired with a real refresh flow
# (see api/auth.py's /refresh endpoint and User.current_refresh_jti in
# models.py for the rotation/revocation mechanics).
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=14)

# SQLAlchemy config
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 280  # Recycle connections before MySQL times them out
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 20
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,   # Recycle connections before the 300-second cloud timeout
    'pool_pre_ping': True  # Test the connection to ensure it's alive before querying
}

# Initialize extensions
db.init_app(app)
migrate = Migrate(app,db)
jwt = JWTManager(app)
# See extensions.py for the in-memory-vs-Redis storage tradeoff note.
limiter.init_app(app)
csrf.init_app(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(lecturer_bp)
app.register_blueprint(student_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(api_student_bp)

# CSRFProtect covers the whole app by default -- exempt the mobile JSON
# API blueprints here rather than relying on per-route decorators, since
# every route in these two blueprints is JWT-header-authenticated, not
# cookie-authenticated (see extensions.py's csrf comment for why that
# means they aren't CSRF-vulnerable in the first place). Without this,
# every mobile login/dashboard/checkin request would start failing with a
# CSRF error the moment CSRFProtect went live, since the Flutter app has
# no csrf_token to send.
csrf.exempt(api_auth_bp)
csrf.exempt(api_student_bp)


# ── Helper functions (still using raw SQL for now — will migrate blueprint by blueprint) ──

def find_student_by_rfid(rfid_uid):
    from models import Student
    return Student.query.filter_by(rfid_uid=rfid_uid).first()

def record_attendance(student_id, session_id):
    from models import Attendance
    record = Attendance(student_id=student_id, session_id=session_id)
    db.session.add(record)
    db.session.commit()

def get_all_active_sessions():
    from models import Session
    return Session.query.filter_by(is_active=True).all()

def get_active_sesh():
    from models import Session
    return Session.query.filter_by(is_active=True).order_by(Session.id.desc()).first()

def did_student_register_course(student_id, course_id):
    from models import Enrollment
    return Enrollment.query.filter_by(
        student_id=student_id,
        course_id=course_id
    ).first() is not None

def attendance_already_recorded(session_id, student_id):
    from models import Attendance
    return Attendance.query.filter_by(
        session_id=session_id,
        student_id=student_id
    ).first() is not None


# ── Routes ──

@app.route('/')
def home():
    return redirect(url_for('auth.login'))

@app.route('/sessions/active', methods=['GET'])
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

@app.route('/sessions/active/<int:course_id>', methods=['GET'])
def get_active_sessions_by_course_id(course_id):
    from models import Session
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
# @csrf.exempt: this route lives directly on `app`, not inside a blueprint,
# so it isn't covered by the csrf.exempt(api_auth_bp)/(api_student_bp)
# calls above -- needs its own exemption. The ESP32 firmware posts here
# with no cookies and no JWT at all; without this, CSRFProtect would
# reject every attendance scan the moment it went live, breaking the
# physical hardware integration.
@app.route('/attendance', methods=['POST'])
@limiter.limit("30 per minute")
@csrf.exempt
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

    record_attendance(student.id, active_session.id)

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)