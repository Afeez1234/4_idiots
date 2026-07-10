from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from utils import connect_to_database

# Create the API blueprint for student mobile endpoints
api_student_bp = Blueprint('api_student', __name__, url_prefix='/api/v1/student')

@api_student_bp.route('/dashboard', methods=['GET'])
@jwt_required()
def get_student_dashboard():
    # 1) Get the user ID and claims from the JWT token 
    current_user_id = int(get_jwt_identity())
    claims = get_jwt()
    
    # Security Check: Ensure only students can access this endpoint
    if claims.get("role") != "student":
        return jsonify({"error": "Unauthorized access. Students only."}), 403

    connection = connect_to_database()
    cursor = connection.cursor(buffered=True)  # Use buffered cursor to allow multiple queries

    try:
        # 2) Fetch the student record from the database
        cursor.execute(
            'SELECT id, FULL_NAME, LEVEL, DEPARTMENT, RFID_UID, MATRIC_NUMBER FROM students WHERE user_id = %s',
            (current_user_id,)
        )
        student = cursor.fetchone()
        
        if not student:
            return jsonify({"error": "Student profile not found."}), 404

        # Unpack the student fields
        student_id, full_name, level, department, rfid_uid, matric_number = student

        # 3) Get the list of courses the student is enrolled in
        cursor.execute(
            'SELECT c.id, c.course_title, c.course_code FROM courses c JOIN enrollments e ON c.id = e.course_id WHERE e.student_id = %s',
            (student_id,)
        )
        enrolled_courses = cursor.fetchall()
        enrollment_count = len(enrolled_courses)

        course_breakdown = []
        attended_sessions_count = 0
        total_sessions_count = 0

        # 4) Build the course breakdown data
        for course_id, course_title, course_code in enrolled_courses:
            # Count all sessions for this course
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE course_id = %s', (course_id,))
            total_sessions = cursor.fetchone()[0]

            # Count attended sessions
            cursor.execute(
                'SELECT COUNT(*) FROM attendance a JOIN sessions s ON a.session_id = s.id WHERE s.course_id = %s AND a.student_id = %s',
                (course_id, student_id)
            )
            attended_sessions = cursor.fetchone()[0]

            total_sessions_count += total_sessions
            attended_sessions_count += attended_sessions

            # Calculate the percentage safely
            pct = round((attended_sessions / total_sessions * 100) if total_sessions else 0, 1)
            course_breakdown.append({
                'id': course_id,
                'name': course_title,
                'code': course_code,
                'pct': pct,
                'attended': attended_sessions,
                'total': total_sessions,
            })

        # 5) Calculate overall stats
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        # 6) Get the recent attendance history
        cursor.execute(
            '''
            SELECT c.course_code, s.session_date, s.start_time
            FROM attendance a
            JOIN sessions s ON a.session_id = s.id
            JOIN courses c ON s.course_id = c.id
            WHERE a.student_id = %s
            ORDER BY s.session_date DESC, s.start_time DESC
            LIMIT 10
            ''',
            (student_id,)
        )
        attendance_rows = cursor.fetchall()

        recent_attendance = []
        for course_code, session_date, start_time in attendance_rows:
            recent_attendance.append({
                'course': course_code,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': str(start_time),
                'present': True,
            })

        # 7) Bundle everything into a clean JSON object for Flutter
        return jsonify({
            "success": True,
            "data": {
                "student": {
                    "full_name": full_name or claims.get("username"),
                    "department": department,
                    "level": level,
                    "rfid_uid": rfid_uid,
                    "matric_number": matric_number
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
        return jsonify({"error": "Database error occurred", "details": str(e)}), 500
    finally:
        cursor.close()
        connection.close()