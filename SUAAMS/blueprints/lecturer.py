from flask import Blueprint, flash, render_template, redirect, request, session, url_for
from datetime import date, datetime, timezone
from utils import login_required
from models import db, Lecturer, Course, Session as SessionModel, Attendance, Student, Enrollment, Department, Semester
from extensions import log_exception

lecturer_bp = Blueprint('lecturer', __name__)


@lecturer_bp.context_processor
def inject_lecturer_context():
    """Makes the signed-in lecturer's course list (for the sidebar's dynamic
    'My Courses' section) and the active semester (sidebar pill, same pattern
    as admin's inject_active_semester) available to every lecturer template."""
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'lecturer':
        return {}
    lecturer = Lecturer.query.filter_by(user_id=user_id).first()
    if not lecturer:
        return {}
    return {
        'sidebar_courses': Course.query.filter_by(lecturer_id=lecturer.id).order_by(Course.course_code).all(),
        'active_semester': Semester.query.filter_by(is_active=True).first(),
    }


@lecturer_bp.route('/lecturer/dashboard')
@login_required('lecturer')
def dashboard():
    user_id = session.get('user_id')

    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        courses = Course.query.filter_by(lecturer_id=lecturer.id).order_by(Course.course_code).all()

        # Full active-session rows (not just a count) so the dashboard banner
        # can name the course(s) currently live and link straight into them.
        active_sessions = SessionModel.query.join(Course).filter(
            Course.lecturer_id == lecturer.id,
            SessionModel.is_active == True
        ).all()
        active_course_ids = {s.course_id for s in active_sessions}

        today = datetime.now(timezone.utc).date()
        today_checkins = Attendance.query.join(SessionModel).join(Course).filter(
            Course.lecturer_id == lecturer.id,
            db.func.date(Attendance.time_in) == today
        ).count()

        # Per-course stats for the course cards. enrolled_students is the
        # viewonly dynamic backref off Enrollment (models.py), so .count()
        # here doesn't pull every row into memory.
        course_cards = []
        for course in courses:
            course_cards.append({
                'course': course,
                'enrolled_count': course.enrolled_students.count(),
                'session_count': SessionModel.query.filter_by(course_id=course.id).count(),
                'is_live': course.id in active_course_ids,
            })

    except Exception:
        log_exception("Lecturer Dashboard Error")
        flash('An error occurred while fetching lecturer data.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'lecturer/dashboard.html',
        course_cards=course_cards,
        active_sessions=active_sessions,
        today_checkins=today_checkins,
        active_page='dashboard',
    )


@lecturer_bp.route('/lecturer/course/<int:course_id>')
@login_required('lecturer')
def course_workspace(course_id):
    user_id = session.get('user_id')
    
    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        course = Course.query.filter_by(id=course_id, lecturer_id=lecturer.id).first()
        if not course:
            flash('Course not found or access denied.', 'error')
            return redirect(url_for('lecturer.dashboard'))

        # Get active session if it exists
        active_session = SessionModel.query.filter_by(course_id=course_id, is_active=True).first()
        
        attendance_records = []
        if active_session:
            # BUG FIX: Student.department is a relationship, not a column --
            # selecting it directly here doesn't error, it silently returns
            # True (a meaningless boolean) for every row instead of the
            # actual department, since it can't resolve as a scalar column
            # without an explicit join. Confirmed by testing this exact
            # query shape against a real DB. Joining Department explicitly
            # and selecting Department.name instead -- same fix already
            # applied to api/lecturer.py's equivalent queries. Column order
            # unchanged, so template indices (record[0], [3], [4], [5])
            # relying on this tuple's position still line up correctly.
            attendance_records = db.session.query(
                Student.full_name, Student.level, Department.name,
                Student.matric_number, Attendance.status, Attendance.time_in
            ).join(Attendance, Attendance.student_id == Student.id)\
             .join(Department, Student.department_id == Department.id)\
             .filter(Attendance.session_id == active_session.id).all()
            
        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

        total_sessions_this_semester = SessionModel.query.filter_by(course_id=course_id).count()
        
        total_attendance = Attendance.query.join(SessionModel).filter(SessionModel.course_id == course_id).count()
        average_attendance = round(
            (total_attendance / (total_sessions_this_semester * enrolled_count) * 100) 
            if total_sessions_this_semester and enrolled_count else 0, 1
        )

        stats = {
            'total_enrolled_students': enrolled_count,
            'total_sessions_this_semester': total_sessions_this_semester,
            'average_attendance': average_attendance,
            'present_in_current_session': len(attendance_records),
        }
        
    except Exception:
        log_exception("Workspace Error")
        flash('An error occurred loading the workspace.', 'error')
        return redirect(url_for('lecturer.dashboard'))

    return render_template(
        'lecturer/course_workspace.html',
        course=course,
        active_session=active_session,
        attendance_records=attendance_records,
        stats=stats,
        active_page='course_workspace',
        active_course_id=course.id,
    )


@lecturer_bp.route('/lecturer/sessions/history')
@login_required('lecturer')
def session_history():
    """Cross-course session history: every ended session across all of this
    lecturer's courses, newest first. Distinct from course_workspace's old
    embedded history table (removed) -- this is the sidebar's global
    'Session History' page, so rows need a course column to stay legible."""
    user_id = session.get('user_id')

    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        courses = Course.query.filter_by(lecturer_id=lecturer.id).all()
        course_ids = [c.id for c in courses]
        courses_by_id = {c.id: c for c in courses}

        # Enrolled count per course, needed to derive absentees below --
        # cached here so the loop over sessions doesn't re-query it per row.
        enrolled_counts = {
            course_id: Enrollment.query.filter_by(course_id=course_id).count()
            for course_id in course_ids
        }

        sessions_data = db.session.query(
            SessionModel.id,
            SessionModel.course_id,
            SessionModel.session_date,
            SessionModel.planned_start,
            db.func.count(Attendance.id)
        ).outerjoin(Attendance, Attendance.session_id == SessionModel.id)\
         .filter(SessionModel.course_id.in_(course_ids), SessionModel.is_active == False)\
         .group_by(SessionModel.id)\
         .order_by(SessionModel.session_date.desc()).all()

        history_sessions = []
        for sess_id, course_id, sess_date, start_time, present_count in sessions_data:
            enrolled = enrolled_counts.get(course_id, 0)
            history_sessions.append({
                'session_id': sess_id,
                'course': courses_by_id.get(course_id),
                'date': sess_date,
                'start_time': start_time,
                'present_count': present_count,
                'absent_count': max(enrolled - present_count, 0),
            })

    except Exception:
        log_exception("Session History Error")
        flash('An error occurred loading session history.', 'error')
        return redirect(url_for('lecturer.dashboard'))

    return render_template(
        'lecturer/session_history.html',
        history_sessions=history_sessions,
        active_page='session_history',
    )


@lecturer_bp.route('/lecturer/course/<int:course_id>/start-session', methods=['POST'])
@login_required('lecturer')
def start_session(course_id):
    try:
        active_session = SessionModel.query.filter_by(course_id=course_id, is_active=True).first()
        if active_session:
            flash('A session is already active for this course.', 'error')
            return redirect(url_for('lecturer.course_workspace', course_id=course_id))
        
        # BUG FIX: request.form.get() returns "HH:MM" strings (from the
        # <input type="time"> in course_workspace.html), but
        # Session.planned_start/planned_end are db.Time columns expecting
        # actual datetime.time objects. Passing the raw string through (as
        # this used to) works on some DB drivers but not others -- confirmed
        # to raise a hard TypeError against SQLite; same bug existed in
        # api/lecturer.py's version of this endpoint, already fixed there.
        # A parse failure here falls through to the except block below
        # (flash + log), which is fine since <input type="time"> is
        # browser-validated -- only a forged request would hit it.
        planned_start_raw = request.form.get('planned_start') or None
        planned_end_raw = request.form.get('planned_end') or None
        planned_start = datetime.strptime(planned_start_raw, '%H:%M').time() if planned_start_raw else None
        planned_end = datetime.strptime(planned_end_raw, '%H:%M').time() if planned_end_raw else None

        new_session = SessionModel(
            course_id=course_id,
            session_date=datetime.now(timezone.utc).date(),
            is_active=True,
            planned_start=planned_start,
            planned_end=planned_end
        )
        
        db.session.add(new_session)
        db.session.commit()
        flash('Session started successfully.', 'success')
        
    except Exception:
        db.session.rollback()
        log_exception("Start Session Error")
        flash('Failed to start session.', 'error')

    return redirect(url_for('lecturer.course_workspace', course_id=course_id))
    

@lecturer_bp.route('/lecturer/course/<int:course_id>/end-session', methods=['POST'])
@login_required('lecturer')
def end_session_r(course_id):
    try:
        active_session = SessionModel.query.filter_by(course_id=course_id, is_active=True).first()
        if not active_session:
            flash('No active session found for this course.', 'error')
            return redirect(url_for('lecturer.course_workspace', course_id=course_id))
            
        active_session.is_active = False
        db.session.commit()
        
        flash('Session ended successfully.', 'success')
        
    except Exception:
        db.session.rollback()
        log_exception("End Session Error")
        flash('Failed to end session.', 'error')

    return redirect(url_for('lecturer.course_workspace', course_id=course_id))


@lecturer_bp.route('/lecturer/course/<int:course_id>/session/<int:session_id>')
@login_required('lecturer')
def session_detail(course_id, session_id):
    user_id = session.get('user_id')
    
    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        course = Course.query.filter_by(id=course_id, lecturer_id=lecturer.id).first()
        if not course:
            flash('Course not found or access denied.', 'error')
            return redirect(url_for('lecturer.dashboard'))

        session_info = SessionModel.query.filter_by(id=session_id, course_id=course_id).first()
        if not session_info:
            flash('Session not found.')
            return redirect(url_for('lecturer.course_workspace', course_id=course_id))

        # SCHEMA FIX: Student.department is a relationship (to the
        # Department object), not a plain column -- selecting it directly
        # in a tuple query silently produced a cartesian product against
        # the departments table (a boolean per department row, one output
        # row per department, instead of one row per student). Join
        # Department explicitly and select Department.name, matching the
        # pattern already used in api/student.py, blueprints/student.py,
        # api/lecturer.py, and api/hardware.py. Column position kept the
        # same (index 2) since session_detail.html indexes this tuple by
        # position (record[2]).
        attendance_records = db.session.query(
            Student.full_name, Student.level, Department.name,
            Student.matric_number, Attendance.status, Attendance.time_in
        ).join(Attendance, Attendance.student_id == Student.id)\
         .join(Department, Student.department_id == Department.id)\
         .filter(Attendance.session_id == session_id).all()
         
        enrolled_count = Enrollment.query.filter_by(course_id=course_id).count()

    except Exception:
        log_exception("Session Detail Error")
        flash('An error occurred loading session details.', 'error')
        return redirect(url_for('lecturer.course_workspace', course_id=course_id))

    return render_template(
        'lecturer/session_detail.html',
        course=course,
        session_info=session_info,
        attendance_records=attendance_records,
        enrolled_count=enrolled_count
    )