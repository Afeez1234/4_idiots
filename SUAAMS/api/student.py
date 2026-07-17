from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    jwt_required, get_jwt_identity, get_jwt,
    create_access_token, decode_token,
)
from datetime import timedelta

# Import db and our elegant SQLAlchemy models
# (added Enrollment here -- needed by the new check-in endpoints below)
from models import db, Student, Course, Session as SessionModel, Attendance, Enrollment

# Create the API blueprint for student mobile endpoints
api_student_bp = Blueprint('api_student', __name__, url_prefix='/api/v1/student')

# How long a minted HCE "beacon" token stays valid. Deliberately short --
# this is NOT the student's login session JWT, which lives for the whole
# session. CLAUDE.md's threat model requires HCE/BLE proximity tokens to
# carry short-lived signed timestamps so a relayed/captured broadcast can't
# be replayed outside a ~3-second window; reusing the long-lived session
# token here would defeat that anti-relay requirement entirely.
BEACON_TOKEN_TTL_SECONDS = 5

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
                'name': course.title, # FIX: Swapped to .title
                'code': course.code,  # FIX: Swapped to .code
                'pct': pct,
                'attended': attended_sessions,
                'total': total_sessions,
            })

        # 5) Calculate overall stats
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        # 6) Get the recent attendance history elegantly via ORM
        recent_records = db.session.query(
            Course.code, SessionModel.session_date, SessionModel.planned_start, Attendance.status # FIX: code and planned_start
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
        for course_code, session_date, start_time, status in recent_records:
            recent_attendance.append({
                'course': course_code,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if start_time else '--:--', # FIX: Safe null fallback
                'present': status == 'present', # Map DB status to boolean
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

    except Exception as e:
        print(f"Mobile API Error: {e}")
        return jsonify({"error": "Database error occurred", "details": str(e)}), 500


@api_student_bp.route('/checkin/beacon', methods=['POST'])
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


@api_student_bp.route('/checkin', methods=['POST'])
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

    record = Attendance(student_id=student.id, session_id=active_session.id)
    db.session.add(record)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully.",
        "student": {
            "id": student.id,
            "full_name": student.full_name,
        }
    }), 200