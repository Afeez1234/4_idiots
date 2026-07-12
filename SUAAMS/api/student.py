from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

# Import db and our elegant SQLAlchemy models
from models import db, Student, Course, Session as SessionModel, Attendance

# Create the API blueprint for student mobile endpoints
api_student_bp = Blueprint('api_student', __name__, url_prefix='/api/v1/student')

@api_student_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_student_dashboard():
    # 1) Get the user ID and claims from the JWT token
    current_user_id = get_jwt_identity()
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
        recent_records = db.session.query(
            Course.course_code, SessionModel.session_date, SessionModel.start_time, Attendance.status
        ).select_from(Attendance).join(
            SessionModel, Attendance.session_id == SessionModel.id
        ).join(
            Course, SessionModel.course_id == Course.id
        ).filter(
            Attendance.student_id == student.id
        ).order_by(
            SessionModel.session_date.desc(), SessionModel.start_time.desc()
        ).limit(10).all()

        recent_attendance = []
        for course_code, session_date, start_time, status in recent_records:
            recent_attendance.append({
                'course': course_code,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else str(start_time),
                'present': status == 'present', # Map DB status to boolean
            })

        # 7) Bundle everything into a clean JSON object for Flutter
        return jsonify({
            "success": True,
            "data": {
                "student": {
                    "full_name": student.full_name or claims.get("username"),
                    "department": student.department,
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