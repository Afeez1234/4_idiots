from flask import Blueprint, flash, render_template, redirect, session, url_for
from utils import login_required
from models import db, Student, Course, Session as SessionModel, Attendance, Announcement, Semester
from extensions import log_exception

student_bp = Blueprint('student', __name__)


@student_bp.context_processor
def inject_student_context():
    """Makes active_semester available to every student template (used by
    the sidebar pill in base_student.html), same pattern as
    admin.inject_active_semester / lecturer.inject_lecturer_context."""
    return {'active_semester': Semester.query.filter_by(is_active=True).first()}


def _get_student_or_redirect():
    """Shared lookup used by every route below -- a session can carry
    role='student' without a matching Student profile row (e.g. account
    provisioned but never linked), so each route needs the same guard
    admin/lecturer routes already apply to their own profile lookups."""
    user_id = session.get('user_id')
    student = Student.query.filter_by(user_id=user_id).first()
    if not student:
        flash('Student profile not found.', 'error')
        return None
    return student


def _course_breakdown(student):
    """Per-course attendance stats for this student. Shared by dashboard()
    (top-4 preview) and my_courses() (full list) so the two pages can't
    drift apart on the percentage formula."""
    breakdown = []
    for course in student.courses:
        total_sessions = SessionModel.query.filter_by(course_id=course.id).count()
        attended_sessions = Attendance.query.join(SessionModel).filter(
            SessionModel.course_id == course.id,
            Attendance.student_id == student.id
        ).count()
        pct = round((attended_sessions / total_sessions * 100) if total_sessions else 0, 1)
        breakdown.append({
            'id': course.id,
            'name': course.course_title,
            'code': course.course_code,
            'lecturer_name': course.lecturer.full_name if course.lecturer else None,
            'credit_units': course.credit_units,
            'pct': pct,
            'attended': attended_sessions,
            'total': total_sessions,
        })
    return breakdown


@student_bp.route('/student/dashboard')
@login_required('student')
def dashboard():
    student = _get_student_or_redirect()
    if not student:
        return redirect(url_for('auth.login'))

    try:
        enrollment_count = len(student.courses)
        course_breakdown = _course_breakdown(student)
        attended_sessions_count = sum(c['attended'] for c in course_breakdown)
        total_sessions_count = sum(c['total'] for c in course_breakdown)
        overall_rate = round((attended_sessions_count / total_sessions_count * 100) if total_sessions_count else 0, 1)
        at_risk_count = sum(1 for course in course_breakdown if course['pct'] < 75)

        recent_records = db.session.query(
            Course.course_code, Course.course_title, SessionModel.session_date, SessionModel.planned_start, Attendance.status
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
        for course_code, course_title, session_date, start_time, status in recent_records:
            recent_attendance.append({
                'course': course_code,
                'course_title': course_title,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else str(start_time),
                'status': status,
            })

        student_profile = {
            'full_name': student.full_name or session.get('username'),
            'department': student.department.name if student.department else None,
            'level': student.level,
            'rfid_uid': student.rfid_uid,
            'matric_number': student.matric_number,
        }

    except Exception:
        log_exception("Student Dashboard Error")
        flash('An error occurred loading the dashboard.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'student/dashboard.html',
        enrollment_count=enrollment_count,
        attendance_count=attended_sessions_count,
        overall_rate=overall_rate,
        at_risk_count=at_risk_count,
        courses=course_breakdown,
        student_profile=student_profile,
        recent_attendance=recent_attendance,
        active_page='dashboard',
    )


@student_bp.route('/student/courses')
@login_required('student')
def my_courses():
    student = _get_student_or_redirect()
    if not student:
        return redirect(url_for('auth.login'))

    try:
        course_breakdown = _course_breakdown(student)
    except Exception:
        log_exception("Student My Courses Error")
        flash('An error occurred loading your courses.', 'error')
        return redirect(url_for('student.dashboard'))

    return render_template(
        'student/my_courses.html',
        courses=course_breakdown,
        active_page='my_courses',
    )


@student_bp.route('/student/attendance')
@login_required('student')
def attendance_history():
    student = _get_student_or_redirect()
    if not student:
        return redirect(url_for('auth.login'))

    try:
        records = db.session.query(
            Course.course_code, Course.course_title, SessionModel.session_date, SessionModel.planned_start, Attendance.status
        ).select_from(Attendance).join(
            SessionModel, Attendance.session_id == SessionModel.id
        ).join(
            Course, SessionModel.course_id == Course.id
        ).filter(
            Attendance.student_id == student.id
        ).order_by(
            SessionModel.session_date.desc(), SessionModel.planned_start.desc()
        ).all()

        attendance_log = []
        for course_code, course_title, session_date, start_time, status in records:
            attendance_log.append({
                'course_code': course_code,
                'course_title': course_title,
                'date': session_date.strftime('%d %b %Y') if hasattr(session_date, 'strftime') else str(session_date),
                'time': start_time.strftime('%H:%M') if hasattr(start_time, 'strftime') else str(start_time),
                'status': status,
            })
    except Exception:
        log_exception("Student Attendance History Error")
        flash('An error occurred loading your attendance history.', 'error')
        return redirect(url_for('student.dashboard'))

    return render_template(
        'student/attendance_history.html',
        attendance_log=attendance_log,
        active_page='attendance_history',
    )


@student_bp.route('/student/announcements')
@login_required('student')
def announcements():
    student = _get_student_or_redirect()
    if not student:
        return redirect(url_for('auth.login'))

    try:
        enrolled_course_ids = [c.id for c in student.courses]

        # Read-only feed, scoped to what this student can actually see:
        # university-wide notices, notices for their own department, or
        # notices for a course they're enrolled in. Mirrors the same
        # scope enum lecturer/admin already write against (Announcement.scope).
        scope_filter = db.or_(
            Announcement.scope == 'university',
            db.and_(Announcement.scope == 'department', Announcement.department_id == student.department_id),
            db.and_(Announcement.scope == 'course', Announcement.course_id.in_(enrolled_course_ids)),
        )
        student_announcements = Announcement.query.filter(
            Announcement.is_active,
            scope_filter,
        ).order_by(Announcement.created_at.desc()).all()
    except Exception:
        log_exception("Student Announcements Error")
        flash('An error occurred loading announcements.', 'error')
        return redirect(url_for('student.dashboard'))

    return render_template(
        'student/announcements.html',
        announcements=student_announcements,
        active_page='announcements',
    )
