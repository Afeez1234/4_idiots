import re
from flask import Blueprint, flash, render_template, redirect, request, session, url_for
from datetime import datetime, timezone
from utils import login_required
from models import db, HOD, Department, Lecturer, Course, Student, Session as SessionModel, Attendance
from extensions import log_exception

hod_bp = Blueprint('hod', __name__)


def _normalize_level(raw):
    """Student.level is a free-text String(20) (admins may enter '400' or
    '400L'), so pull the leading digits out rather than trusting the whole
    string to be a clean int. Returns None if nothing numeric is found."""
    if not raw:
        return None
    match = re.match(r'\d+', raw.strip())
    return int(match.group()) if match else None


def _course_level(course_code):
    """Course has no level column -- level is conventionally encoded in the
    course code's leading digit (e.g. MCT301 -> 300L, MEE211 -> 200L), same
    convention the seed/mock data in the HOD design uses. Returns None for
    codes with no numeric part to bucket under."""
    match = re.search(r'\d+', course_code or '')
    if not match:
        return None
    return int(match.group()[0]) * 100


def _student_attendance(student, course_ids):
    """Overall attendance % and a per-course breakdown for one student,
    scoped to the given course ids (the HOD's department). Courses with no
    sessions yet are excluded rather than counted as 0% -- there's been no
    attendance opportunity yet, so 0% would misrepresent an absence that
    hasn't happened. Returns (overall_pct_or_None, [{'code','title','pct'}]).
    """
    enrolled_ids = {c.id for c in student.courses} & set(course_ids)
    per_course = []
    total_sessions = 0
    total_attended = 0
    for course_id in enrolled_ids:
        course = Course.query.get(course_id)
        session_count = SessionModel.query.filter_by(course_id=course_id).count()
        if session_count == 0:
            continue
        attended = Attendance.query.join(SessionModel).filter(
            Attendance.student_id == student.id,
            SessionModel.course_id == course_id,
            Attendance.status.in_(['present', 'late']),
        ).count()
        pct = round(attended / session_count * 100)
        per_course.append({'code': course.course_code, 'title': course.course_title, 'pct': pct})
        total_sessions += session_count
        total_attended += attended
    overall = round(total_attended / total_sessions * 100) if total_sessions else None
    per_course.sort(key=lambda c: c['code'])
    return overall, per_course


def _require_hod():
    """Shared lookup used by every HOD route below. Returns the HOD profile,
    or None after already flashing + redirecting the caller should return."""
    hod = HOD.query.filter_by(user_id=session.get('user_id')).first()
    if not hod:
        flash('HOD profile not found.', 'error')
        return None
    return hod


@hod_bp.route('/hod/dashboard')
@login_required('hod')
def dashboard():
    """
    Read-only department-wide oversight -- an HOD isn't a Lecturer, so this
    deliberately doesn't reuse lecturer.dashboard's course_workspace links
    (starting/ending sessions is scoped to Course.lecturer_id, not
    something an HOD is authorized to do here).

    Stat cards + Quick Access match the HOD Screen Dashboard design pulled
    into the project: Lecturers / Students / Courses / Flagged Attendance,
    then cards into the Levels and Students & Attendance pages. The old
    per-course grid is dropped here -- the new Levels page (course +
    lecturer per level) is a strict superset of what it showed.
    """
    try:
        hod = _require_hod()
        if not hod:
            return redirect(url_for('auth.login'))

        department = hod.department

        courses = Course.query.filter_by(department_id=hod.department_id).all()
        course_ids = [c.id for c in courses]

        active_sessions = SessionModel.query.filter(
            SessionModel.course_id.in_(course_ids),
            SessionModel.is_active == True
        ).all() if course_ids else []

        students = Student.query.filter_by(department_id=hod.department_id).all()
        flagged_count = 0
        for student in students:
            overall, _ = _student_attendance(student, course_ids)
            if overall is not None and overall < 75:
                flagged_count += 1

        lecturer_count = Lecturer.query.filter_by(department_id=hod.department_id).count()

    except Exception:
        log_exception("HOD Dashboard Error")
        flash('An error occurred while fetching department data.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'hod/dashboard.html',
        department=department,
        active_sessions=active_sessions,
        lecturer_count=lecturer_count,
        student_count=len(students),
        course_count=len(courses),
        flagged_count=flagged_count,
        active_page='dashboard',
    )


@hod_bp.route('/hod/levels')
@login_required('hod')
def levels():
    """Lecturers and the courses they teach, grouped by level (100-500),
    matching the Levels tab in the HOD design. Level is derived from each
    course code's leading digit (see _course_level) since Course has no
    level column of its own."""
    try:
        hod = _require_hod()
        if not hod:
            return redirect(url_for('auth.login'))

        courses = Course.query.filter_by(department_id=hod.department_id).order_by(Course.course_code).all()
        students = Student.query.filter_by(department_id=hod.department_id).all()

        by_level = {}
        for course in courses:
            level = _course_level(course.course_code)
            if level is None:
                continue
            by_level.setdefault(level, []).append(course)

        student_counts = {}
        for student in students:
            level = _normalize_level(student.level)
            if level is not None:
                student_counts[level] = student_counts.get(level, 0) + 1

        level_sections = []
        for level in sorted(set(by_level) | set(student_counts)):
            level_courses = by_level.get(level, [])
            level_sections.append({
                'level': level,
                'lecturer_count': len({c.lecturer_id for c in level_courses if c.lecturer_id}),
                'course_count': len(level_courses),
                'student_count': student_counts.get(level, 0),
                'courses': [
                    {
                        'code': c.course_code,
                        'title': c.course_title,
                        'units': c.credit_units,
                        'lecturer': c.lecturer.full_name if c.lecturer else 'Unassigned',
                    }
                    for c in level_courses
                ],
            })

    except Exception:
        log_exception("HOD Levels Error")
        flash('An error occurred while fetching department data.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'hod/levels.html',
        department=hod.department,
        level_sections=level_sections,
        active_page='levels',
    )


@hod_bp.route('/hod/students')
@login_required('hod')
def students():
    """Student roster + attendance for one level at a time, matching the
    Students & Attendance tab. ?level=<n> selects which level's roster to
    show; defaults to the lowest level with students in the department."""
    try:
        hod = _require_hod()
        if not hod:
            return redirect(url_for('auth.login'))

        course_ids = [c.id for c in Course.query.filter_by(department_id=hod.department_id).all()]

        all_students = Student.query.filter_by(department_id=hod.department_id).all()
        levels_present = sorted({lvl for lvl in (_normalize_level(s.level) for s in all_students) if lvl is not None})

        requested_level = request.args.get('level', type=int)
        selected_level = requested_level if requested_level in levels_present else (levels_present[0] if levels_present else None)

        roster = []
        flagged_count = 0
        for student in all_students:
            if _normalize_level(student.level) != selected_level:
                continue
            overall, per_course = _student_attendance(student, course_ids)
            if overall is not None and overall < 75:
                flagged_count += 1
            roster.append({
                'name': student.full_name,
                'matric': student.matric_number,
                'initial': student.full_name[0].upper() if student.full_name else '?',
                'overall': overall,
                'courses': per_course,
            })
        roster.sort(key=lambda s: s['name'])

    except Exception:
        log_exception("HOD Students Error")
        flash('An error occurred while fetching department data.', 'error')
        return redirect(url_for('auth.login'))

    return render_template(
        'hod/students.html',
        department=hod.department,
        levels_present=levels_present,
        selected_level=selected_level,
        roster=roster,
        flagged_count=flagged_count,
        active_page='students',
    )


@hod_bp.route('/hod/signoffs')
@login_required('hod')
def signoffs():
    """Stub: the design's Sign-offs tab (digital signature + course
    registration vs. exam card verification) needs registration/exam-card
    records that don't exist yet -- self-service course registration is
    still on the roadmap (see CLAUDE.md), so there's nothing real to
    cross-check against. Placeholder page instead of a half-built feature
    checking data that doesn't exist."""
    hod = _require_hod()
    if not hod:
        return redirect(url_for('auth.login'))

    return render_template(
        'hod/signoffs.html',
        department=hod.department,
        active_page='signoffs',
    )
