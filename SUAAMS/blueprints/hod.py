from flask import Blueprint, flash, render_template, redirect, session, url_for
from datetime import datetime, timezone
from utils import login_required
from models import db, HOD, Department, Lecturer, Course, Student, Session as SessionModel, Attendance
from extensions import log_exception

hod_bp = Blueprint('hod', __name__)


@hod_bp.context_processor
def inject_hod_context():
    """Makes the signed-in HOD's department name available to every HOD
    template, same pattern as lecturer's inject_lecturer_context().

    has_lecturer_profile flags an HOD who also holds a Lecturer profile
    under the same account (see login_required(('lecturer', 'hod')) on
    blueprints/lecturer.py's routes) -- lets base_hod.html show a "My
    Courses" link into the lecturer portal instead of them needing a
    second login just to manage their own courses."""
    user_id = session.get('user_id')
    if not user_id or session.get('role') != 'hod':
        return {}
    hod = HOD.query.filter_by(user_id=user_id).first()
    if not hod:
        return {}
    has_lecturer_profile = Lecturer.query.filter_by(user_id=user_id).first() is not None
    return {
        'hod_department': hod.department,
        'has_lecturer_profile': has_lecturer_profile,
    }


@hod_bp.route('/hod/dashboard')
@login_required('hod')
def dashboard():
    """
    Read-only department-wide oversight -- an HOD isn't a Lecturer, so this
    deliberately doesn't reuse lecturer.dashboard's course_workspace links
    (starting/ending sessions is scoped to Course.lecturer_id, not
    something an HOD is authorized to do here). Same query shape as
    lecturer.dashboard, just scoped to department_id across every lecturer
    in the department instead of lecturer_id for a single lecturer.
    """
    user_id = session.get('user_id')

    try:
        hod = HOD.query.filter_by(user_id=user_id).first()
        if not hod:
            flash('HOD profile not found.', 'error')
            return redirect(url_for('auth.login'))

        department = hod.department

        courses = Course.query.filter_by(department_id=hod.department_id).order_by(Course.course_code).all()
        course_ids = [c.id for c in courses]

        active_sessions = SessionModel.query.filter(
            SessionModel.course_id.in_(course_ids),
            SessionModel.is_active == True
        ).all() if course_ids else []
        active_course_ids = {s.course_id for s in active_sessions}

        today = datetime.now(timezone.utc).date()
        today_checkins = Attendance.query.join(SessionModel).filter(
            SessionModel.course_id.in_(course_ids),
            db.func.date(Attendance.time_in) == today
        ).count() if course_ids else 0

        course_cards = []
        for course in courses:
            course_cards.append({
                'course': course,
                'lecturer_name': course.lecturer.full_name if course.lecturer else 'Unassigned',
                'enrolled_count': course.enrolled_students.count(),
                'session_count': SessionModel.query.filter_by(course_id=course.id).count(),
                'is_live': course.id in active_course_ids,
            })

        lecturer_count = Lecturer.query.filter_by(department_id=hod.department_id).count()
        student_count = Student.query.filter_by(department_id=hod.department_id).count()

    except Exception:
        log_exception("HOD Dashboard Error")
        flash('An error occurred while fetching department data.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'hod/dashboard.html',
        department=department,
        course_cards=course_cards,
        active_sessions=active_sessions,
        today_checkins=today_checkins,
        lecturer_count=lecturer_count,
        student_count=student_count,
        active_page='dashboard',
    )
