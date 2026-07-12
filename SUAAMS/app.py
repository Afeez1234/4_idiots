from flask import Flask, request, jsonify, redirect, url_for
from datetime import date
import os
from flask_jwt_extended import JWTManager
from models import db
from blueprints.auth import auth_bp
from blueprints.admin import admin_bp
from blueprints.lecturer import lecturer_bp
from blueprints.student import student_bp
from api.auth import api_auth_bp
from api.student import api_student_bp

SECRET_KEY = os.environ.get('SECRET_KEY', 'suaams_secret_key_2025')
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'super_secret_jwt_key_for_mobile_2026')

# Database connection string for SQLAlchemy
DB_HOST = os.environ.get('DB_HOST', 'bikxczmqtd1kynudsfrp-mysql.services.clever-cloud.com')
DB_USER = os.environ.get('DB_USER', 'uo5woagbfvcducyy')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'edVtI3biNQmhQrfJwRe8')
DB_NAME = os.environ.get('DB_NAME', 'bikxczmqtd1kynudsfrp')
DB_PORT = os.environ.get('DB_PORT', '3306')

app = Flask(__name__)

# Core config
app.secret_key = SECRET_KEY
app.config['JWT_SECRET_KEY'] = JWT_SECRET

# SQLAlchemy config
app.config['SQLALCHEMY_DATABASE_URI'] = (
    f'mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_POOL_SIZE'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 280  # Recycle connections before MySQL times them out
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 20

# Initialize extensions
db.init_app(app)
jwt = JWTManager(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(lecturer_bp)
app.register_blueprint(student_bp)
app.register_blueprint(api_auth_bp)
app.register_blueprint(api_student_bp)


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

@app.route('/sessions/start', methods=['POST'])
def start_session():
    data = request.get_json()
    course_id = data.get('course_id')
    if not course_id:
        return jsonify({"error": "course_id is required"}), 400
    return jsonify({"success": True, "message": "Session started successfully."}), 201

@app.route('/sessions/active', methods=['GET'])
def get_active_sessions():
    sessions = get_all_active_sessions()
    active_sessions = []
    for s in sessions:
        active_sessions.append({
            "id": s.id,
            "course_id": s.course_id,
            "start_time": str(s.start_time),
            "stop_time": str(s.stop_time),
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
            "start_time": str(session.start_time),
            "stop_time": str(session.stop_time),
            "session_date": str(session.session_date)
        }
    }), 200

@app.route('/attendance', methods=['POST'])
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
            "department": student.department
        }
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)