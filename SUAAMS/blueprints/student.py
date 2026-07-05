from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required,connect_to_database

student_bp = Blueprint('student', __name__)


@student_bp.route('/student/dashboard')
@login_required('student')
def dashboard():
    # 1) Get the logged-in student from the session.
    user_id = session.get('user_id')
    connection = connect_to_database()
    cursor = connection.cursor()

    try:
        # 2) Fetch the student record from the database.
        cursor.execute(
            'SELECT id, FULL_NAME, LEVEL, DEPARTMENT, RFID_UID, MATRIC_NUMBER FROM students WHERE user_id = %s',
            (user_id,)
        )
        student = cursor.fetchone()
        if not student:
            flash('Student profile not found.', 'error')
            return redirect(url_for('auth.login'))

        # 3) Unpack the student fields for easy use below.
        student_id, full_name, level, department, rfid_uid, matric_number = student

        # 4) Count how many courses the student is enrolled in.
        cursor.execute('SELECT COUNT(*) FROM enrollments WHERE student_id = %s', (student_id,))
        enrollment_count = cursor.fetchone()[0]

        # 5) Get the list of courses the student is enrolled in.
        cursor.execute(
            'SELECT c.id, c.course_title, c.course_code FROM courses c JOIN enrollments e ON c.id = e.course_id WHERE e.student_id = %s',
            (student_id,)
        )
        enrolled_courses = cursor.fetchall()

        # 6) Build the course breakdown data for the UI.
        #    Each course gets its attendance percentage, which the template/JS can display.
        course_breakdown = []
        attended_sessions_count = 0
        total_sessions_count = 0

        for course_id, course_title, course_code in enrolled_courses:
            # Count all sessions for this course.
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE course_id = %s', (course_id,))
            total_sessions = cursor.fetchone()[0]

            # Count how many sessions the student attended for this course.
            cursor.execute(
                'SELECT COUNT(*) FROM attendance a JOIN sessions s ON a.session_id = s.id WHERE s.course_id = %s AND a.student_id = %s',
                (course_id, student_id)
            )
            attended_sessions = cursor.fetchone()[0]

            total_sessions_count += total_sessions
            attended_sessions_count += attended_sessions

            # Calculate the percentage safely. If there are no sessions, show 0 instead of dividing by zero.
            pct = round((attended_sessions / total_sessions * 100) if total_sessions else 0, 1)
            course_breakdown.append({
                'id': course_id,
                'name': course_title,
                'code': course_code,
                'pct': pct,
                'attended': attended_sessions,
                'total': total_sessions,
            })

        # 7) Calculate the overall attendance rate across all courses.
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        # 8) Get the recent attendance history for the table.
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
                'time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else str(start_time),
                'present': True,
            })

        # 9) Prepare a student profile dictionary for the template.
        student_profile = {
            'full_name': full_name or session.get('username'),
            'department': department,
            'level': level,
            'rfid_uid': rfid_uid,
            'matric_number': matric_number,
        }

        # 10) Bundle everything into one object to pass to the HTML and JavaScript.
        dashboard_data = {
            'student': student_profile,
            'overall_rate': overall_rate,
            'attendance_count': attended_sessions_count,
            'at_risk_count': at_risk_count,
            'courses': course_breakdown,
            'recent_attendance': recent_attendance,
        }

        # 11) Render the template and pass both simple values and the full dashboard data object.
        return render_template(
            'student/dashboard.html',
            enrollment_count=enrollment_count,
            attendance_count=attended_sessions_count,
            overall_rate=overall_rate,
            at_risk_count=at_risk_count,
            courses=course_breakdown,
            student_profile=student_profile,
            dashboard_data=dashboard_data,
        )
    finally:
        # Always close the DB resources, even if something goes wrong.
        cursor.close()
        connection.close()