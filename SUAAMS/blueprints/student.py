from flask import Blueprint, flash, render_template, redirect, session, url_for
from utils import login_required
from models import db, Student, Course, Session as SessionModel, Attendance

student_bp = Blueprint('student', __name__)

@student_bp.route('/student/dashboard')
@login_required('student')
def dashboard():
    # 1) Get the logged-in student from the session
    user_id = session.get('user_id')

    try:
        # 2) Fetch the student record using ORM
        student = Student.query.filter_by(user_id=user_id).first()
        if not student:
            flash('Student profile not found.', 'error')
            return redirect(url_for('auth.login'))

        # 3) Use the new Many-to-Many relationship to effortlessly count enrollments
        enrollment_count = len(student.courses)

        course_breakdown = []
        attended_sessions_count = 0
        total_sessions_count = 0

        # 4) Iterate through the enrolled courses using the direct relationship
        for course in student.courses:
            # Count all sessions for this course
            total_sessions = SessionModel.query.filter_by(course_id=course.id).count()

            # Count attended sessions using a simple ORM join
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
                'name': course.title,
                'code': course.code,
                'pct': pct,
                'attended': attended_sessions,
                'total': total_sessions,
            })

        # 5) Calculate overall stats
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        # 6) Get the recent attendance history elegantly sorting via ORM
        recent_records = db.session.query(
            Course.code, SessionModel.session_date, SessionModel.planned_start
        ).select_from(Attendance).join(
            SessionModel, Attendance.session_id == SessionModel.id
        ).join(
            Course, SessionModel.course_id == Course.id
        ).filter(
            Attendance.student_id == student.id
        ).order_by(
            SessionModel.session_date.desc(), SessionModel.planned_start.desc()
        ).limit(10).all()

        recent_attendance = []
        for course_code, session_date, start_time in recent_records:
            recent_attendance.append({
                'course': course_code,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else str(start_time),
                'present': True,
            })

        # 7) Prepare the student profile dictionary
        student_profile = {
            'full_name': student.full_name or session.get('username'),
            'department': student.department.name if student.department else None,
            'level': student.level,
            'rfid_uid': student.rfid_uid,
            'matric_number': student.matric_number,
        }

        # 8) Bundle everything into one object
        dashboard_data = {
            'student': student_profile,
            'overall_rate': overall_rate,
            'attendance_count': attended_sessions_count,
            'at_risk_count': at_risk_count,
            'courses': course_breakdown,
            'recent_attendance': recent_attendance,
        }

    except Exception as e:
        print(f"Student Dashboard Error: {e}")
        flash('An error occurred loading the dashboard.', 'error')
        return redirect(url_for('auth.login'))

    # 9) Render the template exactly as before
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