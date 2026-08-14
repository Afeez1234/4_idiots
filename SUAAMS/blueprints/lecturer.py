import csv
import io
from flask import Blueprint, flash, render_template, redirect, request, session, url_for, Response
from datetime import date, datetime, timezone
from utils import login_required
from models import db, Lecturer, Course, Session as SessionModel, Attendance, Student, Enrollment, Department, Semester, Announcement
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


@lecturer_bp.route('/lecturer/announcements', methods=['GET', 'POST'])
@login_required('lecturer')
def announcements():
    """Lecturer-scoped announcements: unlike admin's version (which can post
    university/department/course-wide), a lecturer can only post to a course
    they actually teach, and only ever sees their own sent announcements --
    no scope selector needed since 'course' is the only option."""
    user_id = session.get('user_id')

    lecturer = Lecturer.query.filter_by(user_id=user_id).first()
    if not lecturer:
        flash('Lecturer profile not found.', 'error')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        title = request.form.get('title')
        body = request.form.get('body')
        course_id = request.form.get('course_id')

        if not all([title, body, course_id]):
            flash('Title, body, and course are all required.', 'error')
            return redirect(url_for('lecturer.announcements'))

        # Ownership check -- a lecturer must not be able to post an
        # announcement against a course they don't actually teach, even if
        # course_id is forged in the request.
        course = Course.query.filter_by(id=course_id, lecturer_id=lecturer.id).first()
        if not course:
            flash('You can only post announcements to courses you teach.', 'error')
            return redirect(url_for('lecturer.announcements'))

        try:
            announcement = Announcement(
                title=title.strip(),
                body=body.strip(),
                sender_id=user_id,
                scope='course',
                course_id=course.id,
            )
            db.session.add(announcement)
            db.session.commit()
            flash(f"Announcement '{title}' posted successfully.", 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to post announcement.', 'error')
            log_exception("Lecturer Announcement Create Error")

        return redirect(url_for('lecturer.announcements'))

    sent_announcements = Announcement.query.filter_by(sender_id=user_id).order_by(Announcement.created_at.desc()).all()
    return render_template(
        'lecturer/announcements.html',
        announcements=sent_announcements,
        active_page='announcements',
    )


# Validated categorical palette (see dataviz skill) for course identity in
# the Analytics charts -- slot 1 is the app's own accent color, the rest are
# the dataviz reference palette's dark-mode hues re-ordered so no adjacent
# pair fails the CVD/normal-vision floors against this app's #0F1117
# surface (validated via validate_palette.js, not eyeballed). Capped at 5:
# past that, courses fold into "Other" rather than reusing a color.
ANALYTICS_PALETTE = ['#4F6BED', '#d95926', '#9085e9', '#d55181', '#c98500']


def _course_attendance_reports(lecturer):
    """Per-course attendance percentage, shared by reports() and
    export_reports() so the on-screen table and the exported CSV can't
    drift apart. Same 'actual / (sessions * enrolled)' formula already used
    by course_workspace()'s stats.average_attendance and admin's
    department_attendance."""
    courses = Course.query.filter_by(lecturer_id=lecturer.id).order_by(Course.course_code).all()
    rows = []
    for course in courses:
        enrolled_count = Enrollment.query.filter_by(course_id=course.id).count()
        session_count = SessionModel.query.filter_by(course_id=course.id).count()
        total_attendance = Attendance.query.join(SessionModel).filter(SessionModel.course_id == course.id).count()
        average_attendance = round(
            (total_attendance / (session_count * enrolled_count) * 100)
            if session_count and enrolled_count else 0, 1
        )
        rows.append({
            'course': course,
            'enrolled_count': enrolled_count,
            'session_count': session_count,
            'average_attendance': average_attendance,
        })
    return rows


@lecturer_bp.route('/lecturer/analytics')
@login_required('lecturer')
def analytics():
    user_id = session.get('user_id')

    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        # Reuses the exact Reports numbers so the comparison chart can't
        # disagree with the Reports page for the same course.
        course_reports = _course_attendance_reports(lecturer)

        comparison_data = [
            {
                'course_id': row['course'].id,
                'code': row['course'].course_code,
                'title': row['course'].course_title,
                'pct': row['average_attendance'],
                'color': ANALYTICS_PALETTE[i % len(ANALYTICS_PALETTE)],
            }
            for i, row in enumerate(course_reports)
        ]

        # Per-session attendance %, per course, for the trend line chart --
        # capped at 5 courses (the validated palette's slot count) and only
        # courses with at least one completed session (an all-zero flat
        # line for a brand-new course isn't a trend, it's noise).
        trend_series = []
        for i, row in enumerate(course_reports[:len(ANALYTICS_PALETTE)]):
            course = row['course']
            enrolled = row['enrolled_count']

            sessions_data = db.session.query(
                SessionModel.session_date,
                db.func.count(Attendance.id)
            ).outerjoin(Attendance, Attendance.session_id == SessionModel.id)\
             .filter(SessionModel.course_id == course.id, SessionModel.is_active == False)\
             .group_by(SessionModel.id)\
             .order_by(SessionModel.session_date.asc()).all()

            if not sessions_data:
                continue

            points = [
                {
                    'date': sess_date.strftime('%Y-%m-%d'),
                    'pct': round((present_count / enrolled * 100) if enrolled else 0, 1),
                }
                for sess_date, present_count in sessions_data
            ]
            trend_series.append({
                'course_id': course.id,
                'code': course.course_code,
                'title': course.course_title,
                'color': ANALYTICS_PALETTE[i % len(ANALYTICS_PALETTE)],
                'points': points,
            })

        # KPI tiles, scoped to courses that have actually run a session --
        # an unstarted course's 0% would otherwise drag the average down
        # and falsely win "Needs Attention".
        rated = [r for r in course_reports if r['session_count'] > 0]
        overall_avg = round(sum(r['average_attendance'] for r in rated) / len(rated), 1) if rated else None
        best_course = max(rated, key=lambda r: r['average_attendance']) if rated else None
        worst_course = min(rated, key=lambda r: r['average_attendance']) if len(rated) > 1 else None

    except Exception:
        log_exception("Lecturer Analytics Error")
        flash('An error occurred loading analytics.', 'error')
        return redirect(url_for('lecturer.dashboard'))

    return render_template(
        'lecturer/analytics.html',
        trend_series=trend_series,
        comparison_data=comparison_data,
        overall_avg=overall_avg,
        best_course=best_course,
        worst_course=worst_course,
        active_page='analytics',
    )


@lecturer_bp.route('/lecturer/reports')
@login_required('lecturer')
def reports():
    user_id = session.get('user_id')

    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        course_reports = _course_attendance_reports(lecturer)

    except Exception:
        log_exception("Lecturer Reports Error")
        flash('An error occurred loading reports.', 'error')
        return redirect(url_for('lecturer.dashboard'))

    return render_template(
        'lecturer/reports.html',
        course_reports=course_reports,
        active_page='reports',
    )


@lecturer_bp.route('/lecturer/reports/export')
@login_required('lecturer')
def export_reports():
    user_id = session.get('user_id')

    try:
        lecturer = Lecturer.query.filter_by(user_id=user_id).first()
        if not lecturer:
            flash('Lecturer profile not found.', 'error')
            return redirect(url_for('auth.login'))

        course_reports = _course_attendance_reports(lecturer)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Course Code', 'Course Title', 'Enrolled', 'Sessions Run', 'Average Attendance (%)'])
        for row in course_reports:
            writer.writerow([
                row['course'].course_code,
                row['course'].course_title,
                row['enrolled_count'],
                row['session_count'],
                row['average_attendance'],
            ])

    except Exception:
        log_exception("Lecturer Reports Export Error")
        flash('Failed to export attendance report.', 'error')
        return redirect(url_for('lecturer.reports'))

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=attendance_report.csv'},
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
        enrolled_count=enrolled_count,
        active_page='session_history',
        active_course_id=course.id,
    )