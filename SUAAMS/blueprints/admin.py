import csv
import os
import io
import json
import re
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
import bcrypt
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from models import (
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, HOD, Semester, Announcement, Timetable,
    AuditLog, DeviceToken, Terminal, course_lecturers,
)
from extensions import log_exception, logger, limiter
from campus_time import campus_now, campus_today
from utils import (
    resolve_current_course, session_status_for_course, notify_announcement,
    VALID_LEVELS, normalize_level, course_level, _csv_safe, course_attendance,
    current_courses,
)
from push_notifications import send_push_notification, notify_users
from audit import log_action, changes
# Aliased: the route below is also called timetable_import (its URL
# endpoint name), which would otherwise replace the module.
import timetable_import as tt_import
from timetable_pdf import KINDS
from timetable_publish import publish_drafts, published_schedules, notify_schedule_changes
import bulk_upload
import people_status
import promotion
import record_edits
import terminal_rooms
import dashboard_today
import analytics
from people_status import STUDENT_STATUSES, LECTURER_STATUSES

# Matches Timetable.day_of_week's documented convention (0=Monday..6=Sunday,
# same as Python's date.weekday()) -- shared by the create-form <select> and
# the list view below so they can't drift apart.
WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
def require_admin():
    """
    Protects every route in this blueprint. Replaces the old @admin_required
    decorator that used to be repeated on each view function individually --
    same check (session user_id + role == 'admin'), applied once instead of
    copy-pasted onto 8+ routes.
    """
    if not session.get('user_id'):
        flash('Session expired. Please log in.', 'error')
        return redirect(url_for('auth.login'))
    if session.get('role') != 'admin':
        flash('Access Denied. Administrative privileges required.', 'error')
        return redirect(url_for('auth.login'))


@admin_bp.context_processor
def inject_active_semester():
    """Makes active_semester available to every admin template (used by
    the sidebar pill in base_admin.html) without each route passing it
    individually. draft_slots is the Timetable nav badge: imported slots
    nobody has published yet, so students and lecturers can't see them."""
    return {
        'active_semester': Semester.query.filter_by(is_active=True).first(),
        'draft_slots': Timetable.query.filter_by(is_published=False).count(),
    }


def _relative_time(dt):
    """Formats a UTC datetime as a short 'N min/hr/day ago' string for the
    dashboard's recent-activity feed. dt is expected to be timezone-aware
    UTC, matching Attendance.time_in's default=lambda: datetime.now(timezone.utc)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 60:
        return 'just now'
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hr ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


# ==========================================
# DASHBOARD
# ==========================================
@admin_bp.route('/dashboard', methods=['GET'])
def dashboard():
    """Is today's teaching happening? Today's timetable with each class's
    status, late classes (with a reminder button), check-ins today by
    method, this semester's department rates and the latest check-ins.
    The work is in dashboard_today.py, in a fixed number of queries."""
    try:
        semester = Semester.query.filter_by(is_active=True).first()
        return render_template(
            'admin/dashboard.html',
            today=dashboard_today.today(semester),
            department_attendance=dashboard_today.department_rates(semester),
            recent_checkins=dashboard_today.recent_checkins(),
            relative_time=_relative_time,
            active_page='dashboard',
        )
    except Exception:
        # Render the page with an error panel rather than redirecting. The
        # old redirect went to the login page, which sends a signed-in admin
        # straight back here: an endless loop on any database hiccup.
        db.session.rollback()
        log_exception("Admin Dashboard Error")
        return render_template('admin/dashboard.html', load_error=True,
                               active_page='dashboard'), 500


@admin_bp.route('/timetable/<int:slot_id>/remind', methods=['POST'])
@limiter.limit("10 per minute")
def remind_lecturer(slot_id):
    """The dashboard's "Notify lecturer" on a late class: a notification
    (in-app + push) to every lecturer on the course. Logged, and the
    dashboard reads that entry back to show when it was sent."""
    slot = db.session.get(Timetable, slot_id)
    if slot is None or slot.course is None:
        flash('That class is no longer on the timetable.', 'error')
        return redirect(url_for('admin.dashboard'))
    course = slot.course
    lecturers = course.all_lecturers
    if not lecturers:
        flash(f"{course.course_code} has no lecturer to notify.", 'error')
        return redirect(url_for('admin.dashboard'))
    when = slot.start_time.strftime('%H:%M')
    where = f" in {slot.room}" if slot.room else ''
    try:
        log_action(dashboard_today.REMIND_ACTION,
                   f"Reminded {', '.join(l.full_name for l in lecturers)} that "
                   f"{course.course_code} ({when}{where}) hasn't started",
                   'timetable', slot.id, {'course_id': course.id})
        # Commits the notifications and, with them, the audit entry above.
        notify_users(
            [l.user_id for l in lecturers], 'class_reminder',
            f"{course.course_code} hasn't started",
            f"{course.course_code} was timetabled for {when}{where}, and no session "
            f"has been started yet. Open the class to let students check in.",
            {'course_id': course.id},
        )
        flash(f"Reminder sent to {', '.join(l.full_name for l in lecturers)}.", 'success')
    except Exception:
        db.session.rollback()
        log_exception("Lecturer Reminder Error")
        flash('Failed to send the reminder.', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/organization', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def organization_page():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'add_faculty':
            name = request.form.get('name')
            if not name or not name.strip():
                flash('Faculty name is required.', 'error')
            else:
                try:
                    faculty = Faculty(name=name.strip())
                    db.session.add(faculty)
                    db.session.flush()
                    log_action('faculty.create', f"Created faculty {faculty.name}",
                               'faculty', faculty.id)
                    db.session.commit()
                    flash(f"Faculty '{name}' added successfully.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Faculty name must be unique.', 'error')
                    log_exception("Faculty Create Error")

        elif action == 'add_department':
            name = request.form.get('name')
            faculty_id = request.form.get('faculty_id')
            years = request.form.get('programme_years', type=int)
            if not name or not faculty_id:
                flash('All fields are required to create a department.', 'error')
            elif years not in PROGRAMME_YEARS:
                flash('Choose how many years the programme runs.', 'error')
            else:
                try:
                    department = Department(name=name.strip(), faculty_id=int(faculty_id),
                                            programme_years=years)
                    db.session.add(department)
                    db.session.flush()
                    faculty = db.session.get(Faculty, department.faculty_id)
                    log_action('department.create',
                               f"Created department {department.name}"
                               + (f" under {faculty.name}" if faculty else ''),
                               'department', department.id)
                    db.session.commit()
                    flash(f"Department '{name}' added successfully.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Failed to create department. Verify connections.', 'error')
                    log_exception("Department Create Error")

        elif action == 'set_programme_years':
            # The one department field promotion depends on; departments
            # created before it existed need it set once.
            department = db.session.get(Department, request.form.get('department_id', type=int) or 0)
            years = request.form.get('programme_years', type=int)
            if not department or years not in PROGRAMME_YEARS:
                flash('Choose a department and a programme length.', 'error')
            elif department.programme_years != years:
                log_action('department.update',
                           f"Set {department.name}'s programme length to {years} years"
                           + (f" (was {department.programme_years})" if department.programme_years else ''),
                           'department', department.id,
                           {'programme_years': {'from': department.programme_years, 'to': years}})
                department.programme_years = years
                db.session.commit()
                flash(f"{department.name} is now a {years}-year programme.", 'success')

        return redirect(url_for('admin.organization_page'))

    faculties = Faculty.query.order_by(Faculty.name).all()
    departments = Department.query.order_by(Department.name).all()
    dept_counts, faculty_counts = _organization_counts(departments)
    return render_template(
        'admin/organization.html',
        faculties=faculties,
        departments=departments,
        dept_counts=dept_counts,
        faculty_counts=faculty_counts,
        programme_years=PROGRAMME_YEARS,
        active_page='organization',
    )


def _organization_counts(departments):
    """Students / lecturers / courses per department and per faculty, in
    three GROUP BY queries.

    PERF: the page used to count with dept.students|length in the
    template, which loads every student, lecturer and course row into
    memory just to count them -- several times over, since the faculty
    totals and both delete warnings repeated it. At 6,000+ students that
    is tens of thousands of objects per page view."""
    dept_counts = {d.id: {'students': 0, 'lecturers': 0, 'courses': 0, 'hods': 0} for d in departments}
    for model, key in ((Student, 'students'), (Lecturer, 'lecturers'), (Course, 'courses'), (HOD, 'hods')):
        for dept_id, n in (db.session.query(model.department_id, db.func.count(model.id))
                           .group_by(model.department_id)):
            if dept_id in dept_counts:
                dept_counts[dept_id][key] = n
    faculty_counts = {}
    for d in departments:
        totals = faculty_counts.setdefault(d.faculty_id, {'departments': 0, 'students': 0,
                                                          'lecturers': 0, 'courses': 0, 'hods': 0})
        totals['departments'] += 1
        for key, n in dept_counts[d.id].items():
            totals[key] += n
    return dept_counts, faculty_counts


# Programme lengths the school runs: levels stop at 500 (VALID_LEVELS).
PROGRAMME_YEARS = (4, 5)


def _cascade_counts(department_ids):
    """How many students, lecturers, courses and HODs sit under these
    departments -- what a cascade delete would remove. Any of them blocks
    the delete (_delete_blocker)."""
    if not department_ids:
        return {'students': 0, 'lecturers': 0, 'courses': 0, 'hods': 0}
    return {
        'students': Student.query.filter(Student.department_id.in_(department_ids)).count(),
        'lecturers': Lecturer.query.filter(Lecturer.department_id.in_(department_ids)).count(),
        'courses': Course.query.filter(Course.department_id.in_(department_ids)).count(),
        'hods': HOD.query.filter(HOD.department_id.in_(department_ids)).count(),
    }


def _delete_blocker(name, counts):
    """Why `name` can't be deleted, or None if nothing sits under it.

    Faculties and departments delete only when EMPTY (2026-10-18). The
    cascade used to remove every student, lecturer, course and HOD under
    them -- with all their attendance -- behind nothing but a typed name,
    while every other delete in the app refuses a record with history
    (record_edits.py)."""
    if not any(counts.values()):
        return None
    return (f"{name} still has {_describe_counts(counts)}. Move or remove them first; "
            f"only an empty one can be deleted.")


def _describe_counts(counts):
    """{'students': 3, 'courses': 0} -> '3 students'. 'nothing else' if all 0."""
    labels = {'hods': ('HOD', 'HODs')}
    parts = [f"{n} {labels[name][n != 1] if name in labels else (name if n != 1 else name[:-1])}"
             for name, n in counts.items() if n]
    return ', '.join(parts) if parts else 'nothing else'


@admin_bp.route('/faculties/<int:faculty_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_faculty(faculty_id):
    """
    Deletes a Faculty and its (empty) Departments. Refused while any
    student, lecturer, course or HOD sits under it (_delete_blocker): the
    models cascade, so a delete would take all of them and their records.
    The type-the-name modal in organization.html confirms an empty one.
    """
    faculty = Faculty.query.get_or_404(faculty_id)
    dept_ids = [d.id for d in faculty.departments]
    blocker = _delete_blocker(faculty.name, _cascade_counts(dept_ids))
    if blocker:
        flash(f"Can't delete: {blocker}", 'error')
        return redirect(url_for('admin.organization_page'))
    try:
        name = faculty.name
        removed = {'departments': len(dept_ids)}
        db.session.delete(faculty)
        log_action('faculty.delete',
                   f"Deleted faculty {name} ({_describe_counts(removed)})",
                   'faculty', faculty_id, {'removed': removed})
        db.session.commit()
        flash(f"Faculty '{name}' was deleted.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to delete faculty.', 'error')
        log_exception("Faculty Delete Error")
    return redirect(url_for('admin.organization_page'))


@admin_bp.route('/departments/<int:department_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_department(department_id):
    """Deletes an empty Department. Refused while anything sits under it,
    as for delete_faculty above."""
    department = Department.query.get_or_404(department_id)
    blocker = _delete_blocker(department.name, _cascade_counts([department.id]))
    if blocker:
        flash(f"Can't delete: {blocker}", 'error')
        return redirect(url_for('admin.organization_page'))
    try:
        name = department.name
        removed = {}
        db.session.delete(department)
        log_action('department.delete', f"Deleted department {name}",
                   'department', department_id, {'removed': removed})
        db.session.commit()
        flash(f"Department '{name}' was deleted.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to delete department.', 'error')
        log_exception("Department Delete Error")
    return redirect(url_for('admin.organization_page'))


# ==========================================
# LECTURERS
# ==========================================
@admin_bp.route('/lecturers', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def lecturers_page():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        staff_id = request.form.get('staff_id')
        department_id = request.form.get('department_id')

        if not all([full_name, staff_id, department_id]):
            flash('All fields are required to register a lecturer.', 'error')
            return redirect(url_for('admin.lecturers_page'))

        try:
            existing_user = User.query.filter_by(username=staff_id.strip()).first()
            if existing_user:
                flash('Staff ID is already registered as an active username.', 'error')
                return redirect(url_for('admin.lecturers_page'))

            hashed_password = bcrypt.hashpw(staff_id.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            user = User(
                username=staff_id.strip(),
                password_hash=hashed_password,
                role='lecturer',
                is_active=True,
                requires_password_change=True,
            )
            db.session.add(user)
            db.session.flush()

            lecturer = Lecturer(
                full_name=full_name.strip(),
                staff_id=staff_id.strip(),
                department_id=int(department_id),
                user_id=user.id,
            )
            db.session.add(lecturer)
            db.session.flush()
            log_action('lecturer.create',
                       f"Created lecturer {lecturer.full_name} ({lecturer.staff_id})",
                       'lecturer', lecturer.id,
                       {'department_id': lecturer.department_id, 'user_id': user.id})
            db.session.commit()
            flash(f"Lecturer account created successfully for {full_name}.", 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to create lecturer account. Verify values.', 'error')
            log_exception("Lecturer Account Error")

        return redirect(url_for('admin.lecturers_page'))

    # Search + department filter in the query, the same GET-form pattern as
    # the Students roster. It used to be Lecturer.query.all() in insertion
    # order, with Ctrl+F the only way to find anyone. No pagination: staff
    # number in the hundreds at most, and search finds one person.
    q = request.args.get('q', '').strip()
    dept_id = request.args.get('dept', type=int)

    query = Lecturer.query
    if q:
        pattern = f'%{_escape_like(q)}%'
        query = query.filter(or_(
            Lecturer.staff_id.ilike(pattern, escape='\\'),
            Lecturer.full_name.ilike(pattern, escape='\\'),
        ))
    if dept_id:
        query = query.filter(Lecturer.department_id == dept_id)
    # joinedload: every row reads lecturer.department, and the status cell
    # reads lecturer.user -- lazily, one query each per row.
    lecturers = (query.options(joinedload(Lecturer.department), joinedload(Lecturer.user))
                 .order_by(Lecturer.full_name, Lecturer.id).all())

    filter_args = {k: v for k, v in (('q', q), ('dept', dept_id)) if v}
    semester = Semester.query.filter_by(is_active=True).first()
    return render_template(
        'admin/lecturers.html',
        lecturers=lecturers,
        departments=Department.query.order_by(Department.name).all(),
        course_counts=_lecturer_course_counts([l.id for l in lecturers], semester),
        filters={'q': q, 'dept': dept_id},
        filter_args=filter_args,
        is_filtered=bool(filter_args),
        lecturer_statuses=LECTURER_STATUSES,
        # Which rows can't be deleted, and why (greys out the button).
        delete_blockers=record_edits.delete_blockers('lecturers', lecturers),
        active_page='lecturers',
    )


def _lecturer_course_counts(lecturer_ids, semester):
    """{lecturer id: courses they teach in the active semester}, counting
    coordinated and co-lectured courses once each.

    The directory used to show len(lecturer.courses): coordinated courses
    only (Course.lecturer_id), across every semester -- a co-lecturer on
    three running courses read 0. Two GROUP BY queries, not one per row."""
    if semester is None or not lecturer_ids:
        return {}
    pairs = set(db.session.query(Course.lecturer_id, Course.id)
                .filter(Course.semester_id == semester.id,
                        Course.lecturer_id.in_(lecturer_ids)))
    pairs |= set(db.session.query(course_lecturers.c.lecturer_id, Course.id)
                 .join(Course, Course.id == course_lecturers.c.course_id)
                 .filter(Course.semester_id == semester.id,
                         course_lecturers.c.lecturer_id.in_(lecturer_ids)))
    counts = {}
    for lecturer_id, _course_id in pairs:
        counts[lecturer_id] = counts.get(lecturer_id, 0) + 1
    return counts


# ==========================================
# BULK UPLOAD: LECTURERS AND COURSES
# ==========================================
# Upload -> preview -> confirm, like the timetable import. Nothing is saved
# by the upload itself; the preview's rows come back with the confirm form
# as JSON and are checked again from scratch there. See bulk_upload.py.

BULK_PAGES = {'students': 'admin.students_page', 'lecturers': 'admin.lecturers_page',
              'courses': 'admin.courses_page'}


@admin_bp.route('/bulk/<kind>/template.csv', methods=['GET'])
def bulk_template(kind):
    """An example CSV with the expected headers."""
    if kind not in BULK_PAGES:
        return redirect(url_for('admin.dashboard'))
    return Response(bulk_upload.template_csv(kind), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=suaams_{kind}_template.csv'})


@admin_bp.route('/bulk/<kind>', methods=['POST'])
@limiter.limit("10 per minute")
def bulk_upload_preview(kind):
    if kind not in BULK_PAGES:
        return redirect(url_for('admin.dashboard'))
    back = url_for(BULK_PAGES[kind])
    upload = request.files.get('file')
    if not upload or not upload.filename:
        flash('Choose a CSV file.', 'error')
        return redirect(back)
    semester = None
    if kind == 'courses':
        semester = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
        if not semester:
            flash('Choose the semester these courses belong to.', 'error')
            return redirect(back)

    try:
        # 2 MB is ~20,000 typical rows -- far past MAX_ROWS; anything bigger
        # isn't a lecturer or course list.
        data = upload.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise bulk_upload.BulkCsvError('The file is over 2 MB -- split it into smaller files.')
        # CSV or an Excel workbook (.xlsx): read_upload tells them apart.
        rows = bulk_upload.read_upload(data, upload.filename, kind)
        if kind == 'students':
            plan = bulk_upload.plan_students(rows, upload.filename)
        elif kind == 'lecturers':
            plan = bulk_upload.plan_lecturers(rows, upload.filename)
        else:
            plan = bulk_upload.plan_courses(rows, upload.filename, semester)
    except bulk_upload.BulkCsvError as e:
        flash(f"{e} Nothing was saved.", 'error')
        return redirect(back)
    except Exception:
        log_exception("Bulk Upload Read Error")
        flash('Something went wrong reading that file. Nothing was saved.', 'error')
        return redirect(back)
    return _render_bulk_preview(plan, semester)


@admin_bp.route('/bulk/confirm', methods=['POST'])
@limiter.limit("10 per minute")
def bulk_upload_confirm():
    try:
        payload = json.loads(request.form.get('plan') or '{}')
    except ValueError:
        payload = {}
    kind = payload.get('kind')
    if kind not in BULK_PAGES:
        flash('That preview is no longer valid. Upload the file again.', 'error')
        return redirect(url_for('admin.dashboard'))
    semester = db.session.get(Semester, payload.get('semester_id') or 0) if kind == 'courses' else None
    back = _bulk_back(kind, semester)

    try:
        plan = bulk_upload.plan_from_json(payload, semester)
        if not plan.ok:
            # Something changed since the preview (someone added the same
            # staff ID, a department was renamed). Show the fresh result.
            flash('Something changed since the preview -- see the errors below. Nothing was saved.', 'error')
            return _render_bulk_preview(plan, semester)

        if kind == 'students':
            created = bulk_upload.apply_students(plan)
            what = f"{created} students"
        elif kind == 'lecturers':
            created = bulk_upload.apply_lecturers(plan)
            what = f"{created} lecturers"
        else:
            created = bulk_upload.apply_courses(plan, semester)
            what = f"{created} courses for {semester.name}"
        skipped = plan.count('exists')
        # Rows with a problem: only a student upload saves around them
        # (bulk_upload.SKIPS_BAD_ROWS); the others never get this far.
        invalid = [r for r in plan.rows if r.errors]
        details = {'filename': plan.filename, 'created': created, 'skipped_existing': skipped,
                   'semester_id': semester.id if semester else None}
        if invalid:
            # The first few, so "why were 12 skipped?" can be answered from
            # the Activity page later.
            details['skipped_invalid'] = len(invalid)
            details['skipped_examples'] = [f"line {r.line}: {r.errors[0]}" for r in invalid[:20]]
        # One entry for the whole file, not one per row.
        # A copy's "filename" is "Copied from <semester>" (plan_course_copy).
        log_action(f"{kind[:-1]}.bulk_import",
                   f"{'' if plan.is_copy else 'Uploaded '}{plan.filename}: {what} created, {skipped} already existed"
                   + (f", {len(invalid)} skipped with problems" if invalid else ''),
                   kind[:-1], None, details)
        db.session.commit()
        first_password = {'students': 'matric number', 'lecturers': 'staff ID'}.get(kind)
        flash(f"Created {what}." + (f" {skipped} already existed and were left unchanged." if skipped else '')
              + (f" {len(invalid)} with problems were skipped." if invalid else '')
              + (f" Each signs in with their {first_password} as the first password."
                 if first_password and created else ''),
              'success')
    except bulk_upload.BulkCsvError as e:
        flash(f"{e} Nothing was saved.", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Bulk Upload Save Error")
        flash('Failed to save the upload. Nothing was saved.', 'error')
    return redirect(back)


def _bulk_back(kind, semester):
    """Where an upload or copy returns to: for courses, the semester they
    went into -- the Courses catalog shows one semester at a time."""
    if kind == 'courses' and semester is not None:
        return url_for(BULK_PAGES[kind], semester=semester.id)
    return url_for(BULK_PAGES[kind])


def _render_bulk_preview(plan, semester):
    return render_template(
        'admin/bulk_preview.html',
        plan=plan,
        semester=semester,
        plan_json=json.dumps(plan.to_json()),
        back_url=_bulk_back(plan.kind, semester),
        active_page=plan.kind,
    )


# ==========================================
# STATUS: ACTIVE, GRADUATED, LEFT, ...
# ==========================================
# Who is still part of the school. people_status.py holds the rules (login
# off, phone released, a departing lecturer's courses); these routes are the
# one-person form and the CSV form. Neither ever deletes anyone.

STATUS_KINDS = {
    'students': (Student, STUDENT_STATUSES, 'admin.students_page', 'matric_number'),
    'lecturers': (Lecturer, LECTURER_STATUSES, 'admin.lecturers_page', 'staff_id'),
}


def _person_label(kind, person):
    return f"{person.full_name} ({person.matric_number if kind == 'students' else person.staff_id})"


def _set_status(kind, person, status, reason):
    """Apply one change and its audit entry (not committed). Returns True
    if anything changed. Raises people_status.StatusError."""
    old = person.status
    setter = people_status.set_student_status if kind == 'students' else people_status.set_lecturer_status
    cleaned = setter(person, status, reason)
    if cleaned is None:
        return False
    names = STATUS_KINDS[kind][1]
    log_action(f"{kind[:-1]}.status",
               f"{_person_label(kind, person)}: {names.get(old, old)} -> {names[status]}. Reason: {cleaned}",
               kind[:-1], person.id, {'from': old, 'to': status, 'reason': cleaned})
    return True


@admin_bp.route('/<kind>/<int:person_id>/status', methods=['POST'])
@limiter.limit("30 per minute")
def change_status(kind, person_id):
    if kind not in STATUS_KINDS:
        return redirect(url_for('admin.dashboard'))
    model, _names, page, _id_col = STATUS_KINDS[kind]
    # Back to the same filtered roster page the form was on.
    back = url_for(page, **{k: v for k, v in request.args.items() if k in RETURN_ARGS})
    person = db.session.get(model, person_id)
    if not person:
        flash('That person no longer exists.', 'error')
        return redirect(back)
    try:
        if _set_status(kind, person, request.form.get('status', ''), request.form.get('reason', '')):
            db.session.commit()
            flash(f"{person.full_name} is now {STATUS_KINDS[kind][1][person.status]}."
                  + ('' if person.status == 'active' else ' Their sign-in is switched off.'), 'success')
        else:
            flash(f"{person.full_name} already has that status.", 'info')
    except people_status.StatusError as e:
        db.session.rollback()
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        log_exception("Status Change Error")
        flash('Failed to change the status. Nothing changed.', 'error')
    return redirect(back)


@admin_bp.route('/<kind>/status/bulk', methods=['POST'])
@limiter.limit("10 per minute")
def bulk_status(kind):
    """A CSV of matric numbers / staff IDs, one status and reason for all.
    First post shows who will change; posting again with confirm=1 applies.
    All or nothing: any problem changes nobody."""
    if kind not in STATUS_KINDS:
        return redirect(url_for('admin.dashboard'))
    _model, names, page, id_col = STATUS_KINDS[kind]
    back = url_for(page)
    status, reason = request.form.get('status', ''), request.form.get('reason', '')
    try:
        if request.form.get('confirm'):
            ids = json.loads(request.form.get('ids') or '[]')
        else:
            upload = request.files.get('file')
            if not upload or not upload.filename:
                raise people_status.StatusError('Choose a CSV file.')
            ids = people_status.read_ids(upload.read(1024 * 1024), id_col)
        # Validated here too, so the preview can't show a change that the
        # confirm would refuse.
        if status not in names:
            raise people_status.StatusError('Choose a valid status.')
        if not ' '.join(reason.split()):
            raise people_status.StatusError('Give a short reason -- it goes in the activity log.')
        found, missing = people_status.find_people(kind, ids)
    except (people_status.StatusError, ValueError) as e:
        flash(f"{e} Nothing changed.", 'error')
        return redirect(back)

    changing = [p for p in found if p.status != status]
    # Lecturers who can't be marked Left yet (they coordinate a running
    # course): shown on the preview, and they block the confirm.
    blocked = {}
    if kind == 'lecturers' and status == 'left':
        for p in changing:
            codes = [c.course_code for c in people_status.running_courses(p)]
            if codes:
                blocked[p.id] = ', '.join(codes)
    if not request.form.get('confirm') or missing or blocked:
        return render_template(
            'admin/status_preview.html', kind=kind, names=names, status=status, reason=reason,
            changing=changing, unchanged=len(found) - len(changing), missing=missing, blocked=blocked,
            ids_json=json.dumps(ids), back_url=back, active_page=kind,
        )
    try:
        changed = sum(1 for p in changing if _set_status(kind, p, status, reason))
        # The per-person entries above say who; this one says it was a file.
        log_action(f"{kind[:-1]}.bulk_status",
                   f"Set {changed} {kind} to {names[status]} from a CSV. Reason: {' '.join(reason.split())}",
                   kind[:-1], None, {'status': status, 'count': changed})
        db.session.commit()
        flash(f"{changed} {kind} set to {names[status]}.", 'success')
    except people_status.StatusError as e:
        db.session.rollback()
        flash(f"{e} Nobody was changed.", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Bulk Status Error")
        flash('Failed to change the statuses. Nobody was changed.', 'error')
    return redirect(back)


# ==========================================
# EDIT / DELETE: COURSES, LECTURERS, STUDENTS
# ==========================================
# Fixing a typo without deleting a whole department. Edit is always allowed;
# delete only for a record with no history. Rules in record_edits.py.

EDIT_KINDS = {
    'courses': (Course, 'admin.courses_page'),
    'lecturers': (Lecturer, 'admin.lecturers_page'),
    'students': (Student, 'admin.students_page'),
    # For HODs, "delete" means removing them as HOD (record_edits.remove_hod).
    'hods': (HOD, 'admin.hods_page'),
    # Name and dates; delete only when empty and not active (2026-10-19).
    'semesters': (Semester, 'admin.semesters_page'),
}

# What the flash says after remove_hod, by outcome.
HOD_REMOVED = {
    'lecturer': "{name} is no longer HOD and is back to being a lecturer.",
    'deleted': "{name} is no longer HOD. Their account was removed.",
    'switched_off': "{name} is no longer HOD. Their sign-in is switched off; "
                    "the account is kept because it has {history} on record.",
}


def _record_label(kind, record):
    if kind == 'courses':
        return f"{record.course_code} ({record.course_title})"
    if kind == 'semesters':
        return record.name
    return _person_label(kind, record)


def _edit_target(kind, record_id):
    """(record or None, URL back to the page the dialog was opened on)."""
    model, page = EDIT_KINDS[kind]
    back = url_for(page, **{k: v for k, v in request.args.items() if k in RETURN_ARGS})
    return db.session.get(model, record_id), back


@admin_bp.route('/<kind>/<int:record_id>/edit', methods=['POST'])
@limiter.limit("30 per minute")
def edit_record(kind, record_id):
    if kind not in EDIT_KINDS:
        return redirect(url_for('admin.dashboard'))
    record, back = _edit_target(kind, record_id)
    if not record:
        flash('That record no longer exists.', 'error')
        return redirect(back)
    before = _record_label(kind, record)
    try:
        diff = record_edits.EDITORS[kind](record, request.form)
        if not diff:
            flash('Nothing changed.', 'info')
            return redirect(back)
        log_action(f"{kind[:-1]}.edit", f"Edited {before}: {', '.join(diff)}",
                   kind[:-1], record.id, {'changes': diff})
        db.session.commit()
        message = f"Saved {_record_label(kind, record)}."
        # The ID is the login username: whoever signs in needs to know.
        if 'staff_id' in diff or 'matric_number' in diff:
            message += (f" They now sign in as {record.user.username if record.user else 'the new ID'}"
                        + (", and their first password is the new ID too."
                           if record.user and record.user.requires_password_change else "."))
        flash(message, 'success')
    except record_edits.EditError as e:
        db.session.rollback()
        flash(f"{e} Nothing changed.", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Record Edit Error")
        flash('Failed to save the changes. Nothing changed.', 'error')
    return redirect(back)


# Letters and digits nobody misreads when a temporary password is read out
# or copied from paper: no 0/o, 1/l/i.
_TEMP_PASSWORD_ALPHABET = 'abcdefghjkmnpqrstuvwxyz23456789'
_TEMP_PASSWORD_LENGTH = 10


@admin_bp.route('/<kind>/<int:record_id>/reset-password', methods=['POST'])
@limiter.limit("10 per minute")
def reset_password(kind, record_id):
    """Give a student or lecturer who forgot their password a new temporary
    one. There was no way back in before: only editing the database.

    The password is random, shown to the admin once (in the flash message,
    never stored readable) and must be replaced at the next sign-in. The
    app's refresh token is revoked, so a phone still signed in is signed out
    within one access-token lifetime. The device binding is untouched:
    unbinding stays its own action, done after checking the student's ID.
    Admins reset their own through create_admin.py, not here.
    """
    if kind not in ('students', 'lecturers'):
        return redirect(url_for('admin.dashboard'))
    record, back = _edit_target(kind, record_id)
    user = record.user if record else None
    if user is None:
        flash('That record no longer exists.', 'error')
        return redirect(back)

    label = _person_label(kind, record)
    temp = ''.join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(_TEMP_PASSWORD_LENGTH))
    try:
        user.password_hash = bcrypt.hashpw(temp.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user.requires_password_change = True
        user.current_refresh_jti = None
        log_action(f"{kind[:-1]}.password_reset", f"Reset the password of {label}",
                   kind[:-1], record.id)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log_exception("Password Reset Error")
        flash('Failed to reset the password. Nothing changed.', 'error')
        return redirect(back)

    flash(f"New temporary password for {label}: {temp} -- shown only now, so pass it on "
          "privately. They must choose their own at their next sign-in.", 'success')
    return redirect(back)


@admin_bp.route('/<kind>/<int:record_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_record(kind, record_id):
    if kind not in EDIT_KINDS:
        return redirect(url_for('admin.dashboard'))
    record, back = _edit_target(kind, record_id)
    if not record:
        flash('That record no longer exists.', 'error')
        return redirect(back)
    label = _record_label(kind, record)
    if kind == 'hods':
        return _remove_hod(record, label, back)
    try:
        removed = record_edits.delete_record(kind, record)
        # Counted before the delete, as with faculties: afterwards there's
        # nothing left to count.
        log_action(f"{kind[:-1]}.delete", f"Deleted {label}", kind[:-1], record_id,
                   {'removed': removed})
        db.session.commit()
        flash(f"Deleted {label}.", 'success')
    except record_edits.EditError as e:
        db.session.rollback()
        flash(f"Can't delete {label}: {e}", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Record Delete Error")
        flash('Failed to delete. Nothing changed.', 'error')
    return redirect(back)


def _remove_hod(hod, label, back):
    department = hod.department.name if hod.department else 'their department'
    user_id, hod_id = hod.user_id, hod.id
    try:
        outcome = record_edits.remove_hod(hod)
        history = record_edits.staff_history(user_id) if outcome == 'switched_off' else None
        log_action('hod.remove', f"Removed {label} as HOD of {department} ({outcome.replace('_', ' ')})",
                   'hod', hod_id, {'outcome': outcome, 'user_id': user_id})
        db.session.commit()
        flash(HOD_REMOVED[outcome].format(name=label, history=history), 'success')
    except Exception:
        db.session.rollback()
        log_exception("HOD Remove Error")
        flash('Failed to remove the HOD. Nothing changed.', 'error')
    return redirect(back)


# ==========================================
# PROMOTION: EVERY ACTIVE STUDENT UP ONE LEVEL
# ==========================================
# Once per academic year (promotion.py). The page shows the year and any
# blocker; "Preview" works out who moves (with optional repeaters CSV);
# "Promote" re-plans from the database and applies; "Undo" reverses the run.

def _promotion_page(plan=None, excluded=()):
    semester = Semester.query.filter_by(is_active=True).first()
    year = promotion.academic_year(semester)
    return render_template(
        'admin/promotion.html',
        semester=semester,
        year=year,
        run=promotion.current_run(year),
        missing_years=sorted(d.name for d in Department.query.filter(Department.programme_years.is_(None))
                             .filter(Department.students.any(Student.status == 'active'))),
        plan=plan,
        excluded_json=json.dumps(list(excluded)),
        active_page='students',
    )


@admin_bp.route('/students/promotion', methods=['GET'])
def promotion_page():
    return _promotion_page()


@admin_bp.route('/students/promotion/preview', methods=['POST'])
@limiter.limit("10 per minute")
def promotion_preview():
    semester = Semester.query.filter_by(is_active=True).first()
    excluded = []
    upload = request.files.get('file')
    try:
        if upload and upload.filename:
            excluded = people_status.read_ids(upload.read(1024 * 1024), 'matric_number')
        plan = promotion.plan_promotion(semester, excluded)
    except (people_status.StatusError, promotion.PromotionError) as e:
        flash(str(e), 'error')
        return redirect(url_for('admin.promotion_page'))
    return _promotion_page(plan, excluded)


@admin_bp.route('/students/promotion/confirm', methods=['POST'])
@limiter.limit("5 per minute")
def promotion_confirm():
    semester = Semester.query.filter_by(is_active=True).first()
    try:
        excluded = json.loads(request.form.get('excluded') or '[]')
        # Re-planned from the database now, not taken from the preview: a
        # student suspended in between must not be promoted.
        plan = promotion.plan_promotion(semester, excluded)
        if plan.year != request.form.get('year'):
            raise promotion.PromotionError('The active semester changed since the preview. Preview again.')
        moved = promotion.apply_promotion(plan, session['user_id'])
        log_action('student.promote',
                   f"Promoted {moved} students one level for {plan.year} "
                   f"({len(plan.excluded)} excluded as repeaters, {len(plan.due)} due to graduate)",
                   'student', None,
                   {'year': plan.year, 'promoted': moved, 'excluded': len(plan.excluded),
                    'due_to_graduate': len(plan.due)})
        db.session.commit()
        flash(f"Promoted {moved} students for {plan.year}. {len(plan.due)} are due to graduate: download "
              f"the list below and set them to Graduated with Change Status (CSV).", 'success')
    except promotion.PromotionError as e:
        db.session.rollback()
        flash(f"{e} Nobody was moved.", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Promotion Error")
        flash('Failed to promote. Nobody was moved.', 'error')
    return redirect(url_for('admin.promotion_page'))


@admin_bp.route('/students/promotion/undo', methods=['POST'])
@limiter.limit("5 per minute")
def promotion_undo():
    run = promotion.current_run(request.form.get('year'))
    if not run:
        flash('There is no promotion to undo for that year.', 'error')
        return redirect(url_for('admin.promotion_page'))
    try:
        year = run.academic_year
        moved_back = promotion.undo_promotion(run)
        log_action('student.promote_undo', f"Undid the {year} promotion: {moved_back} students moved back",
                   'student', None, {'year': year, 'moved_back': moved_back})
        db.session.commit()
        flash(f"Undone: {moved_back} students moved back a level.", 'success')
    except Exception:
        db.session.rollback()
        log_exception("Promotion Undo Error")
        flash('Failed to undo. Nothing changed.', 'error')
    return redirect(url_for('admin.promotion_page'))


@admin_bp.route('/students/promotion/due-to-graduate.csv', methods=['GET'])
def promotion_due_csv():
    """Final-year (and spill-over) active students, in the shape the
    Change Status (CSV) form reads -- matric_number first."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(['matric_number', 'full_name', 'department', 'level'])
    for matric, name, dept, level in promotion.due_to_graduate():
        # Same formula-injection guard as the other CSV exports.
        writer.writerow([_csv_safe(matric), _csv_safe(name), _csv_safe(dept), level])
    return Response(out.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=due_to_graduate.csv'})


# ==========================================
# STUDENTS
# ==========================================
STUDENTS_PER_PAGE = 50

# The roster's filter parameters. Carried through the unbind form and back
# on its redirect so the admin lands on the same filtered view instead of
# the unfiltered first page -- otherwise every unbind means searching again.
STUDENT_FILTER_ARGS = ('q', 'dept', 'level', 'device', 'status', 'page')

# What the edit and status dialogs carry back to the page they were opened
# on: the roster's filters plus the Courses catalog's semester.
RETURN_ARGS = STUDENT_FILTER_ARGS + ('semester',)


def _student_filter_args():
    """The current request's roster filters, non-empty ones only."""
    return {k: request.args[k] for k in STUDENT_FILTER_ARGS if request.args.get(k)}


def _escape_like(text):
    """Makes % and _ in a search term match literally rather than as LIKE wildcards."""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')


@admin_bp.route('/students', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def students_page():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        matric_number = request.form.get('matric_number')
        level = request.form.get('level')
        department_id = request.form.get('department_id')
        rfid_uid = request.form.get('rfid_uid') or None

        if not all([full_name, matric_number, level, department_id]):
            flash('Please fill in all required fields.', 'error')
            return redirect(url_for('admin.students_page'))

        # The form offers a dropdown, but a hand-built POST doesn't have to
        # use it -- this is the check that actually keeps "1000" out.
        level = normalize_level(level)
        if level is None:
            flash('Level must be one of 100, 200, 300, 400 or 500.', 'error')
            return redirect(url_for('admin.students_page'))

        try:
            existing_user = User.query.filter_by(username=matric_number.strip()).first()
            if existing_user:
                flash('Matric Number is already registered as a user username.', 'error')
                return redirect(url_for('admin.students_page'))

            hashed_password = bcrypt.hashpw(matric_number.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            new_user = User(
                username=matric_number.strip(),
                password_hash=hashed_password,
                role='student',
                is_active=True,
                requires_password_change=True,
            )
            db.session.add(new_user)
            db.session.flush()

            # level is already canonical ("400") from normalize_level above.
            new_student = Student(
                full_name=full_name.strip(),
                matric_number=matric_number.strip(),
                level=level,
                rfid_uid=rfid_uid,
                department_id=int(department_id),
                user_id=new_user.id,
            )
            db.session.add(new_student)
            db.session.flush()
            log_action('student.create',
                       f"Created student {new_student.full_name} ({new_student.matric_number})",
                       'student', new_student.id,
                       {'level': level, 'department_id': new_student.department_id})
            db.session.commit()
            flash(f"Student profile created successfully for {full_name}.", 'success')
        except Exception:
            db.session.rollback()
            flash('Database error occurred. Matric Number or RFID UID might already exist.', 'error')
            log_exception("Student Single Creation Error")

        return redirect(url_for('admin.students_page'))

    # Filtering and pagination happen in the query, not in the browser, so
    # the page stays the same size however many students are enrolled.
    # Previously every student was loaded and rendered (twice: card view +
    # table), leaving Ctrl+F as the only way to find one.
    q = request.args.get('q', '').strip()
    dept_id = request.args.get('dept', type=int)
    level = request.args.get('level', '').strip()
    device = request.args.get('device', '')
    status = request.args.get('status', '')
    page = request.args.get('page', 1, type=int)

    query = Student.query
    if q:
        # Partial, case-insensitive. Matric number first because that's what
        # the admin is usually holding -- the student presents their ID card.
        pattern = f'%{_escape_like(q)}%'
        query = query.filter(or_(
            Student.matric_number.ilike(pattern, escape='\\'),
            Student.full_name.ilike(pattern, escape='\\'),
        ))
    if dept_id:
        query = query.filter(Student.department_id == dept_id)
    if level:
        query = query.filter(Student.level == level)
    if device == 'bound':
        query = query.filter(Student.device_id.isnot(None))
    elif device == 'unbound':
        query = query.filter(Student.device_id.is_(None))
    if status in STUDENT_STATUSES:
        query = query.filter(Student.status == status)

    # joinedload: the template reads student.department and student.user on
    # every row, which would otherwise be two extra queries per student.
    # Order: a department or level list reads like a class register, so it
    # goes by matric number (MCT/20/0001, MCT/20/0002, ...). Unfiltered, the
    # newest students come first, so whoever just added or uploaded some
    # sees them at the top. Student.id breaks ties so pages never overlap.
    if dept_id or level:
        order = (Student.matric_number.asc(), Student.id.asc())
    else:
        order = (Student.id.desc(),)
    query = query.options(
        joinedload(Student.department), joinedload(Student.user),
    ).order_by(*order)

    pagination = query.paginate(page=page, per_page=STUDENTS_PER_PAGE, error_out=False)
    # Unbinding the last student on the last page of a "Bound" view leaves
    # that page empty; show the new last page rather than an empty roster.
    if pagination.pages and page > pagination.pages:
        pagination = query.paginate(page=pagination.pages, per_page=STUDENTS_PER_PAGE, error_out=False)

    # The valid levels, plus any other value still stored from before
    # levels were validated (e.g. "400L" ahead of the cleanup migration, or a
    # typo like "1000"). Listing those keeps the offending students findable
    # instead of hiding them; the template marks them as invalid.
    stored_levels = {
        row.level for row in db.session.query(Student.level).distinct()
    }
    levels = list(VALID_LEVELS) + sorted(stored_levels - set(VALID_LEVELS))

    filter_args = _student_filter_args()
    filter_args.pop('page', None)

    return render_template(
        'admin/students.html',
        students=pagination.items,
        pagination=pagination,
        departments=Department.query.order_by(Department.name).all(),
        levels=levels,
        valid_levels=VALID_LEVELS,
        filters={'q': q, 'dept': dept_id, 'level': level, 'device': device, 'status': status},
        student_statuses=STUDENT_STATUSES,
        delete_blockers=record_edits.delete_blockers('students', pagination.items),
        filter_args=filter_args,
        is_filtered=bool(filter_args),
        active_page='students',
    )


@admin_bp.route('/students/unbind/<int:student_id>', methods=['POST'])
@limiter.limit("10 per minute")
def reset_student_binding(student_id):
    """
    Resets the device binding of a student. Enables them to log in cleanly
    on a new physical device upon presenting valid identification.
    """
    try:
        student = Student.query.get_or_404(student_id)
        # Unbinding is the step that lets an account move to another phone,
        # so it's the one most worth being able to trace back to a person.
        log_action('student.unbind',
                   f"Unbound the phone of {student.full_name} ({student.matric_number})",
                   'student', student.id,
                   {'had_device': student.device_id is not None})
        student.device_id = None
        # Clearing current_refresh_jti too -- unbinding used to only clear
        # device_id, which blocks a *future* login from the old device but
        # does nothing to a refresh token that device already holds; it
        # could keep silently refreshing itself for up to
        # JWT_REFRESH_TOKEN_EXPIRES (14 days) after being "unbound".
        if student.user:
            student.user.current_refresh_jti = None
            # And stop pushing to the old phone: after a student reports it
            # stolen, it used to keep receiving all their notifications. The
            # new phone registers its own token when it logs in.
            DeviceToken.query.filter_by(user_id=student.user.id).delete()
        db.session.commit()

        if student.user:
            send_push_notification(
                student.user,
                'device_unlocked',
                'Device Binding Reset',
                'Your account is no longer locked to your previous device. You can now log in from a new one.',
            )

        flash(f"Successfully cleared hardware device binding for {student.full_name}.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to unbind device. System database exception.', 'error')
        log_exception("Device Unbind Critical Exception")

    # Back to the view the admin unbound from (filters ride along on the
    # form's action URL), not the unfiltered first page.
    return redirect(url_for('admin.students_page', **_student_filter_args()))


# ==========================================
# COURSES
# ==========================================
def _manage_course_lecturer(course_id, staff_id, change):
    """Add or remove one of a course's lecturers, or make them coordinator.
    Flashes the outcome; logs every real change to the Activity page.

    Rules: a course always has exactly one coordinator (courses.lecturer_id).
    The coordinator can't be removed -- make someone else coordinator first.
    Making a new coordinator keeps the old one on the course as a co-lecturer,
    so no one silently loses access to classes they teach.
    """
    if not course_id or not staff_id or change not in ('add', 'remove', 'coordinator'):
        flash('Choose a course, enter a staff ID and pick a change.', 'error')
        return
    try:
        course = db.session.get(Course, int(course_id))
        lecturer = Lecturer.query.filter(
            db.func.lower(Lecturer.staff_id) == staff_id.lower()
        ).first()
        if not course:
            flash('That course no longer exists.', 'error')
            return
        if not lecturer:
            flash(f"No lecturer with staff ID '{staff_id}'.", 'error')
            return

        name, code = lecturer.full_name, course.course_code
        is_coordinator = course.lecturer_id == lecturer.id
        is_co = lecturer in course.co_lecturers

        if change == 'add':
            if is_coordinator or is_co:
                flash(f"{name} already teaches {code}.", 'info')
                return
            course.co_lecturers.append(lecturer)
            log_action('course.lecturer_add', f"Added {name} as a lecturer on {code}",
                       'course', course.id, {'lecturer_id': lecturer.id})
            message = f"{name} now teaches {code}."

        elif change == 'remove':
            if is_coordinator:
                flash(f"{name} is the coordinator of {code}. Make someone else "
                      f"coordinator first, then remove them.", 'error')
                return
            if not is_co:
                flash(f"{name} doesn't teach {code}.", 'info')
                return
            course.co_lecturers.remove(lecturer)
            log_action('course.lecturer_remove', f"Removed {name} from {code}",
                       'course', course.id, {'lecturer_id': lecturer.id})
            message = f"{name} no longer teaches {code}."

        else:  # coordinator
            if is_coordinator:
                flash(f"{name} is already the coordinator of {code}.", 'info')
                return
            previous = course.lecturer
            if is_co:
                course.co_lecturers.remove(lecturer)
            course.lecturer_id = lecturer.id
            if previous and previous not in course.co_lecturers:
                course.co_lecturers.append(previous)
            log_action('course.coordinator_change',
                       f"Made {name} coordinator of {code}"
                       + (f" (was {previous.full_name}, who stays on as a lecturer)" if previous else ''),
                       'course', course.id,
                       {'lecturer_id': lecturer.id,
                        'previous_lecturer_id': previous.id if previous else None})
            message = f"{name} is now the coordinator of {code}."

        db.session.commit()
        flash(message, 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to update the course lecturers.', 'error')
        log_exception("Course Lecturer Update Error")


@admin_bp.route('/courses', methods=['GET', 'POST'])
# 20/min not 10 -- this route double-duties as both course creation AND
# the enroll_student action (see action == 'enroll_student' below), which
# an admin may legitimately submit several times in a row to enroll a
# batch of students one at a time.
@limiter.limit("20 per minute", methods=['POST'])
def courses_page():
    if request.method == 'POST':
        # Same dual-action-on-one-route pattern organization_page() already
        # uses (add_faculty/add_department) -- create_course was the only
        # action this route handled before enroll_student existed, so it
        # defaults to that for anything posted without the field, but the
        # real create-course form now sets it explicitly too.
        action = request.form.get('action', 'create_course')

        if action == 'enroll_student':
            # Looked up by matric number: the form used to be a dropdown of
            # every student in the school (see courses.html).
            matric = (request.form.get('matric_number') or '').strip()
            course_id = request.form.get('course_id')

            if not matric or not course_id:
                flash('Enter a matric number and select a course.', 'error')
                return redirect(_courses_back())

            try:
                student = Student.query.filter(
                    db.func.lower(Student.matric_number) == matric.lower()
                ).first()
                course = db.session.get(Course, int(course_id))
                if not student:
                    flash(f"No student with matric number '{matric}'.", 'error')
                elif not course:
                    flash('That course no longer exists.', 'error')
                elif Enrollment.query.filter_by(student_id=student.id, course_id=course.id).first():
                    flash('That student is already enrolled in this course.', 'error')
                else:
                    db.session.add(Enrollment(student_id=student.id, course_id=course.id))
                    log_action('enrollment.create',
                               f"Enrolled {student.full_name} ({student.matric_number}) in {course.course_code}",
                               'enrollment', None,
                               {'student_id': student.id, 'course_id': course.id})
                    db.session.commit()
                    flash(f"{student.full_name} enrolled in {course.course_code}.", 'success')
            except Exception:
                db.session.rollback()
                flash('Failed to enroll student.', 'error')
                log_exception("Enrollment Create Error")

            return redirect(_courses_back())

        if action == 'manage_lecturer':
            _manage_course_lecturer(
                request.form.get('course_id'),
                (request.form.get('staff_id') or '').strip(),
                request.form.get('change'),
            )
            return redirect(_courses_back())

        title = request.form.get('title')
        code = request.form.get('code')
        department_id = request.form.get('department_id')
        lecturer_id = request.form.get('lecturer_id')
        semester_id = request.form.get('semester_id') or None
        credit_units = request.form.get('credit_units') or None

        if not all([title, code, department_id, lecturer_id]):
            flash('All academic course parameters must be specified.', 'error')
            return redirect(_courses_back())

        try:
            course = Course(
                course_title=title.strip(),
                course_code=code.strip().upper(),
                department_id=int(department_id),
                lecturer_id=int(lecturer_id),
                semester_id=int(semester_id) if semester_id else None,
                credit_units=int(credit_units) if credit_units else None,
            )
            db.session.add(course)
            db.session.flush()
            log_action('course.create',
                       f"Created course {course.course_code}: {course.course_title}",
                       'course', course.id,
                       {'department_id': course.department_id, 'lecturer_id': course.lecturer_id,
                        'semester_id': course.semester_id, 'credit_units': course.credit_units})
            db.session.commit()
            flash(f"Course '{code}' assigned and registered successfully.", 'success')
        except Exception:
            db.session.rollback()
            flash('Course Code must be unique within its semester.', 'error')
            log_exception("Course Registration Error")

        return redirect(_courses_back())

    # One semester at a time (2026-10-17). It used to be Course.query.all():
    # every semester's courses together, unordered, so MCT401 appeared once
    # per semester -- identically in the table and in the Enroll Student and
    # Course Lecturers dropdowns, where last year's copy could be picked by
    # mistake. Courses with no semester belong to every semester (the
    # timetable's rule), so they are listed too.
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    semester = db.session.get(Semester, request.args.get('semester', type=int) or 0)
    if semester is None:
        semester = next((s for s in semesters if s.is_active), semesters[0] if semesters else None)
    q = request.args.get('q', '').strip()
    dept_id = request.args.get('dept', type=int)

    query = Course.query
    if semester is not None:
        query = query.filter(or_(Course.semester_id == semester.id, Course.semester_id.is_(None)))
    # joinedload: every row reads department and the coordinator; the
    # co-lecturers are selectin on Course already.
    semester_courses = (query.options(joinedload(Course.department),
                                      joinedload(Course.lecturer))
                        .order_by(Course.course_code, Course.id).all())
    # Search and department narrow the catalog only. The Enroll Student and
    # Course Lecturers dropdowns keep the whole semester, so a search
    # doesn't hide the course you meant to pick.
    needle = q.lower()
    courses = [c for c in semester_courses
               if (not needle or needle in c.course_code.lower() or needle in c.course_title.lower())
               and (not dept_id or c.department_id == dept_id)]
    # One GROUP BY instead of loading every enrolment row to count them.
    enrolled = dict(db.session.query(Enrollment.course_id, db.func.count())
                    .filter(Enrollment.course_id.in_([c.id for c in courses]))
                    .group_by(Enrollment.course_id)) if courses else {}

    filter_args = {k: v for k, v in (('semester', semester.id if semester else None),
                                     ('q', q), ('dept', dept_id)) if v}
    return render_template(
        'admin/courses.html',
        courses=courses,
        semester_courses=semester_courses,
        enrolled=enrolled,
        view_semester=semester,
        departments=Department.query.order_by(Department.name).all(),
        # Only active lecturers can be given a course; on leave or left can't.
        lecturers=Lecturer.query.filter_by(status='active').order_by(Lecturer.full_name).all(),
        semesters=semesters,
        # "Copy courses from another semester": the same semester last year
        # by default -- first- and second-semester courses differ.
        copy_source=tt_import.default_copy_source(semester, semesters) if semester else None,
        filters={'q': q, 'dept': dept_id},
        filter_args=filter_args,
        # Search or department narrowing; the semester alone isn't a filter.
        is_filtered=bool(q or dept_id),
        delete_blockers=record_edits.delete_blockers('courses', courses),
        active_page='courses',
    )


@admin_bp.route('/courses/copy', methods=['POST'])
@limiter.limit("10 per minute")
def courses_copy():
    """Preview copying another semester's courses into this one (by default
    the same semester last year). Same preview, checks and save as a course
    CSV upload -- see bulk_upload.plan_course_copy."""
    source = db.session.get(Semester, request.form.get('source_id', type=int) or 0)
    target = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
    back = url_for('admin.courses_page', **({'semester': target.id} if target else {}))
    if not source or not target or source.id == target.id:
        flash('Choose a different semester to copy from.', 'error')
        return redirect(back)
    try:
        plan = bulk_upload.plan_course_copy(source, target)
    except Exception:
        log_exception("Course Copy Error")
        flash('Something went wrong preparing the copy. Nothing was saved.', 'error')
        return redirect(back)
    if plan is None:
        flash(f"{source.name} has no courses to copy.", 'info')
        return redirect(back)
    return _render_bulk_preview(plan, target)


def _courses_back():
    """The Courses page as the form was posted from (semester, search, dept)."""
    return url_for('admin.courses_page',
                   **{k: request.args[k] for k in ('semester', 'q', 'dept') if request.args.get(k)})


# ==========================================
# TIMETABLE
# ==========================================
GRID_UNIT_MINUTES = 30
_UNITS_PER_HOUR = 60 // GRID_UNIT_MINUTES


def _assign_lanes(day_entries):
    """
    Side-by-side sub-column layout for entries that overlap in time on the
    same day -- e.g. two different courses in two different rooms at the
    same hour, which _validate_timetable_slot() deliberately allows (a
    whole-school timetable has many classes running concurrently). Without
    this, two overlapping entries both get the full day-column width and
    render stacked exactly on top of each other.

    Classic greedy interval-lane assignment: sort by start time, place each
    entry in the first lane whose previous occupant has already ended.
    Entries are first grouped into connected overlap clusters (a sweep that
    starts a new cluster whenever the next entry begins at or after
    everything placed so far in the current one has ended) so that every
    entry in the same visual cluster agrees on how many lanes wide to
    render -- otherwise two entries that don't overlap each other, but both
    overlap a third, could end up with inconsistent widths.

    Mutates each dict in day_entries in place, adding 'lane' (0-indexed)
    and 'lane_count' (how many lanes its cluster needs).
    """
    ordered = sorted(day_entries, key=lambda e: (e['start_units'], e['end_units']))

    clusters = []
    cluster = []
    cluster_max_end = None
    for e in ordered:
        if cluster and e['start_units'] >= cluster_max_end:
            clusters.append(cluster)
            cluster = []
            cluster_max_end = None
        cluster.append(e)
        cluster_max_end = e['end_units'] if cluster_max_end is None else max(cluster_max_end, e['end_units'])
    if cluster:
        clusters.append(cluster)

    for cluster in clusters:
        lane_ends = []  # end_units of the most recent entry placed in each lane
        for e in cluster:
            lane = next((i for i, end in enumerate(lane_ends) if e['start_units'] >= end), None)
            if lane is None:
                lane_ends.append(e['end_units'])
                lane = len(lane_ends) - 1
            else:
                lane_ends[lane] = e['end_units']
            e['lane'] = lane
        for e in cluster:
            e['lane_count'] = len(lane_ends)


def _build_timetable_grid(entries):
    """
    CSS-grid placement for the weekly calendar: half-hour-unit row-start/
    row-span per entry (so 09:30-11:00-style times still land correctly,
    not just on-the-hour slots) plus a day column, and the dynamic hour
    range the grid needs to cover. Defaults to 07:00-19:00 with no data yet;
    widens automatically to fit anything outside that window.
    """
    start_hour, end_hour = 7, 19
    for e in entries:
        start_hour = min(start_hour, e.start_time.hour)
        end_hour = max(end_hour, e.end_time.hour + (1 if e.end_time.minute > 0 else 0))

    hour_labels = [f"{h:02d}:00" for h in range(start_hour, end_hour)]

    today = campus_now()  # campus weekday/date, not the server's UTC one
    today_weekday = today.weekday()

    placed = []
    by_day = defaultdict(list)
    for e in entries:
        start_units = (e.start_time.hour - start_hour) * _UNITS_PER_HOUR + (1 if e.start_time.minute >= 30 else 0)
        end_units = (e.end_time.hour - start_hour) * _UNITS_PER_HOUR + (1 if e.end_time.minute >= 30 else 0)

        # Session/attendance status only means something for TODAY's
        # occurrence of a recurring slot -- every other day in the grid is
        # just a schedule entry, nothing "live" to report.
        today_status = None
        if e.day_of_week == today_weekday:
            status, present_count = session_status_for_course(e.course_id, today.date())
            today_status = {'status': status, 'present_count': present_count}

        p = {
            'entry': e,
            'row_start': start_units + 1,  # CSS grid rows are 1-indexed
            'row_span': max(1, end_units - start_units),
            'day_col': e.day_of_week + 2,  # column 1 is the time-label gutter
            'today_status': today_status,
            'start_units': start_units,
            'end_units': end_units,
        }
        placed.append(p)
        by_day[e.day_of_week].append(p)

    for day_entries in by_day.values():
        _assign_lanes(day_entries)
    for p in placed:
        p['width_pct'] = round(100 / p['lane_count'], 3)
        p['left_pct'] = round(100 / p['lane_count'] * p['lane'], 3)

    return {
        'placed': placed,
        'hour_labels': hour_labels,
        'total_rows': (end_hour - start_hour) * _UNITS_PER_HOUR,
        # Exposed for the mobile agenda view's default day-tab selection
        # (templates/admin/timetable.html) -- the desktop grid doesn't need
        # it since every day column is visible at once.
        'today_weekday': today_weekday,
    }


def _validate_timetable_slot(course, semester_id, day_of_week, start_time, end_time, room, exclude_id=None):
    """
    Shared by create and update. Returns an error string, or None if the
    slot is valid. Two checks:
    - start must be before end.
    - "obvious" conflicts: another slot the same day+semester with an
      overlapping time range that either shares the exact room, or shares
      the same lecturer (two different courses, same teacher, can't both be
      live at once). Two different lecturers in different rooms teaching at
      the same hour is legitimate and NOT flagged.
    """
    if start_time >= end_time:
        return 'Start time must be before end time.'

    query = Timetable.query.filter(
        Timetable.day_of_week == day_of_week,
        Timetable.semester_id == semester_id,
        Timetable.start_time < end_time,
        Timetable.end_time > start_time,
    )
    if exclude_id is not None:
        query = query.filter(Timetable.id != exclude_id)

    # Every lecturer on this course, co-lecturers included: any of them being
    # booked elsewhere at the same time is a clash, not just the coordinator.
    this_lecturers = {l.id: l for l in course.all_lecturers} if course else {}
    for other in query.all():
        if room and other.room and other.room.strip().lower() == room.strip().lower():
            other_code = other.course.course_code if other.course else 'another course'
            return f'Room {room} is already booked by {other_code} at that time.'
        if other.course:
            shared = this_lecturers.keys() & {l.id for l in other.course.all_lecturers}
            if shared:
                lecturer_name = this_lecturers[next(iter(shared))].full_name
                return f'{lecturer_name} already has {other.course.course_code} scheduled at an overlapping time.'
    return None


def _slot_fields(entry):
    """A timetable slot's editable fields, for before/after audit entries."""
    return {
        'course_id': entry.course_id,
        'semester_id': entry.semester_id,
        'day': WEEKDAY_NAMES[entry.day_of_week] if entry.day_of_week is not None else None,
        'start': entry.start_time.strftime('%H:%M') if entry.start_time else None,
        'end': entry.end_time.strftime('%H:%M') if entry.end_time else None,
        'room': entry.room,
        'type': entry.type,
    }


def _slot_label(entry):
    """'MCT 401, Monday 10:00-12:00' -- readable without looking anything up."""
    course = db.session.get(Course, entry.course_id) if entry.course_id else None
    f = _slot_fields(entry)
    return f"{course.course_code if course else '?'}, {f['day']} {f['start']}-{f['end']}"


def _timetable_snapshot(keys):
    """{(semester_id, course_id): published schedule} before a hand edit."""
    return {(sem_id, cid): published_schedules(sem_id, [cid])[cid] for sem_id, cid in keys}


def _notify_timetable_edit(before):
    """After a hand edit is committed: tell the students and lecturers of any
    course whose PUBLISHED schedule changed (editing a draft tells no one).
    Best-effort -- a notification failure never undoes the edit."""
    try:
        for sem_id in {s for s, _ in before}:
            semester = db.session.get(Semester, sem_id)
            old = {cid: sched for (s, cid), sched in before.items() if s == sem_id}
            notify_schedule_changes(semester, old, published_schedules(sem_id, list(old)))
    except Exception:
        log_exception("Timetable Change Notification Error")


@admin_bp.route('/timetable', methods=['GET', 'POST'])
# 20/min -- an admin setting up a semester's schedule adds many slots in
# quick succession, same reasoning as courses_page's enroll_student burst.
@limiter.limit("20 per minute", methods=['POST'])
def timetable_page():
    if request.method == 'POST':
        action = request.form.get('action', 'create')

        if action == 'delete':
            timetable_id = request.form.get('timetable_id')
            try:
                entry = Timetable.query.get_or_404(int(timetable_id))
                before = _timetable_snapshot({(entry.semester_id, entry.course_id)})
                log_action('timetable.delete', f"Removed timetable slot {_slot_label(entry)}",
                           'timetable', entry.id, _slot_fields(entry))
                db.session.delete(entry)
                db.session.commit()
                _notify_timetable_edit(before)
                flash('Timetable slot removed.', 'success')
            except Exception:
                db.session.rollback()
                # Session.timetable_id deliberately isn't cascaded (models.py) --
                # a FK-RESTRICT failure here means real session history already
                # exists under this slot.
                flash('Could not delete: sessions already exist for this slot.', 'error')
                log_exception("Timetable Delete Error")
            return redirect(_timetable_back())

        timetable_id = request.form.get('timetable_id')  # set only for action == 'update'
        course_id = request.form.get('course_id')
        semester_id = request.form.get('semester_id')
        day_of_week = request.form.get('day_of_week')
        start_time_raw = request.form.get('start_time')
        end_time_raw = request.form.get('end_time')
        room = request.form.get('room') or None
        slot_type = request.form.get('type', 'scheduled')

        if not all([course_id, semester_id, day_of_week, start_time_raw, end_time_raw]):
            flash('Course, semester, day, start time, and end time are all required.', 'error')
            return redirect(_timetable_back())

        try:
            semester_id_int = int(semester_id)
            day_of_week_int = int(day_of_week)
            start_time = datetime.strptime(start_time_raw, '%H:%M').time()
            end_time = datetime.strptime(end_time_raw, '%H:%M').time()
            course = Course.query.get(int(course_id))
        except (ValueError, TypeError):
            flash('Invalid timetable slot data.', 'error')
            return redirect(_timetable_back())

        # Sidebar's active semester is the intended default -- picking a
        # different one requires an explicit confirmation checkbox so a
        # stray click can't silently create a slot under the wrong academic
        # session. Only enforced when there IS an active semester to compare
        # against.
        active_semester = Semester.query.filter_by(is_active=True).first()
        if active_semester and semester_id_int != active_semester.id \
                and request.form.get('confirm_other_semester') != 'on':
            chosen = Semester.query.get(semester_id_int)
            flash(
                f'"{chosen.name if chosen else "Selected semester"}" isn\'t the active semester '
                f'({active_semester.name}). Check "Use a different semester" below and resubmit to proceed.',
                'error',
            )
            return redirect(_timetable_back())

        error = _validate_timetable_slot(
            course, semester_id_int, day_of_week_int, start_time, end_time, room,
            exclude_id=int(timetable_id) if timetable_id else None,
        )
        if error:
            flash(error, 'error')
            return redirect(_timetable_back())

        try:
            if action == 'update' and timetable_id:
                entry = Timetable.query.get_or_404(int(timetable_id))
                before = _slot_fields(entry)
                entry_key = (entry.course_id, entry.semester_id, entry.day_of_week,
                             entry.start_time, entry.end_time)
                # Old and new course/semester: moving a class between courses
                # changes both courses' schedules.
                published_before = _timetable_snapshot({(entry.semester_id, entry.course_id),
                                                        (semester_id_int, course.id)})
                entry.course_id = course.id
                entry.semester_id = semester_id_int
                entry.day_of_week = day_of_week_int
                entry.start_time = start_time
                entry.end_time = end_time
                entry.room = room.strip() if room else None
                entry.type = slot_type
                # A different course, day or time is a new class from today
                # for Analytics; a room or type correction isn't.
                # (A draft gets its date when it's published.)
                if entry.is_published and (entry.course_id, entry.semester_id, entry.day_of_week,
                                           entry.start_time, entry.end_time) != entry_key:
                    entry.effective_from = campus_today()
                diff = changes(before, _slot_fields(entry))
                # Saving the form unchanged isn't worth an entry.
                if diff:
                    log_action('timetable.update', f"Changed timetable slot {_slot_label(entry)}",
                               'timetable', entry.id, {'changes': diff})
                db.session.commit()
                _notify_timetable_edit(published_before)
                flash('Timetable slot updated.', 'success')
            else:
                published_before = _timetable_snapshot({(semester_id_int, course.id)})
                entry = Timetable(
                    course_id=course.id,
                    semester_id=semester_id_int,
                    day_of_week=day_of_week_int,
                    start_time=start_time,
                    end_time=end_time,
                    room=room.strip() if room else None,
                    type=slot_type,
                    created_by=session['user_id'],
                    # Published straight away, so it runs from today.
                    effective_from=campus_today(),
                )
                db.session.add(entry)
                db.session.flush()
                log_action('timetable.create', f"Added timetable slot {_slot_label(entry)}",
                           'timetable', entry.id, _slot_fields(entry))
                db.session.commit()
                _notify_timetable_edit(published_before)
                flash('Timetable slot added.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to save timetable slot.', 'error')
            log_exception("Timetable Save Error")

        return redirect(_timetable_back())

    view = _timetable_view()
    # Drafts and Publish are deliberately NOT filtered: narrowing to one
    # department must never hide a semester's drafts waiting to go out.
    drafts = Timetable.query.filter_by(is_published=False).all()
    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    common = dict(
        view=view,
        semesters=semesters,
        copy_source=tt_import.default_copy_source(view['semester'], semesters) if view['semester'] else None,
        departments=Department.query.order_by(Department.name).all(),
        levels=VALID_LEVELS,
        weekday_names=WEEKDAY_NAMES,
        draft_count=len(drafts),
        draft_semesters=_draft_semesters(drafts),
        import_max_files=tt_import.MAX_FILES,
        active_page='timetable',
    )
    if not view['is_grid']:
        return render_template('admin/timetable.html', coverage=_timetable_coverage(view), **common)

    # One department + level: the week those students see in the app.
    courses = view['courses']
    timetable_entries = (Timetable.query
                         .filter(Timetable.semester_id == view['semester_id'],
                                 Timetable.course_id.in_([c.id for c in courses]))
                         .order_by(Timetable.day_of_week.asc(), Timetable.start_time.asc())
                         .all()) if courses else []
    return render_template(
        'admin/timetable.html',
        timetable_entries=timetable_entries,
        courses=sorted(courses, key=lambda c: c.course_code),
        grid=_build_timetable_grid(timetable_entries),
        **common,
    )


# ---- department / level view ---------------------------------------------------
# With ~20 departments x 5 levels one grid of every class is unreadable, so the
# page has two views over one semester (GET ?semester=&dept=&level=):
#   * coverage (default): a row per department+level -- has it got a
#     timetable, is a draft waiting -- each row linking into...
#   * the grid, once a department AND a level are chosen: exactly the week
#     those students see in the app; where single classes are added/fixed.
# A course's level comes from its code (utils.course_level); "other" catches
# codes without one, "general" courses without a department.

def _timetable_view():
    """The page's filters from the query string, plus the courses they match."""
    semester = db.session.get(Semester, request.args.get('semester', type=int) or 0)
    if semester is None:
        semester = (Semester.query.filter_by(is_active=True).first()
                    or Semester.query.order_by(Semester.start_date.desc()).first())
    dept = request.args.get('dept', '')
    level = request.args.get('level', '')
    department = db.session.get(Department, int(dept)) if dept.isdigit() else None
    if dept != 'general' and department is None:     # junk or a deleted department
        dept = ''
    if level != 'other' and level not in VALID_LEVELS:
        level = ''

    # A semester's courses: those tied to it, plus older ones with no semester
    # (the same rule the PDF import matches course codes by).
    courses = Course.query.filter(or_(Course.semester_id == semester.id,
                                      Course.semester_id.is_(None))).all() if semester else []
    matching = [c for c in courses
                if (not dept or _dept_key(c) == dept)
                and (not level or _level_key(c) == level)]
    return {
        'semester': semester,
        'semester_id': semester.id if semester else None,
        'dept': dept, 'level': level,
        'dept_name': department.name if department else ('General (no department)' if dept == 'general' else None),
        'is_grid': bool(dept and level),
        'courses': matching,
        # Passed back on every link and form so the page comes back as it was.
        'args': {k: v for k, v in (('semester', semester.id if semester else None),
                                   ('dept', dept), ('level', level)) if v},
    }


def _dept_key(course):
    return str(course.department_id) if course.department_id else 'general'


def _level_key(course):
    return course_level(course.course_code) or 'other'


def _timetable_back():
    """The timetable page with the filters the form was posted from."""
    return url_for('admin.timetable_page',
                   **{k: request.args[k] for k in ('semester', 'dept', 'level') if request.args.get(k)})


def _timetable_coverage(view):
    """A row per department+level with courses this semester: how many of its
    courses have published classes, and how many draft classes wait. Two
    narrow queries, no per-row lookups."""
    if not view['semester_id']:
        return []
    classes = defaultdict(lambda: [0, 0])          # course_id -> [published, drafts]
    for course_id, published in (db.session.query(Timetable.course_id, Timetable.is_published)
                                 .filter(Timetable.semester_id == view['semester_id'])):
        classes[course_id][0 if published else 1] += 1
    dept_names = dict(db.session.query(Department.id, Department.name).all())

    rows = {}
    for c in view['courses']:      # already narrowed by a lone dept or level filter
        key = (_dept_key(c), _level_key(c))
        row = rows.setdefault(key, {
            'dept': key[0], 'level': key[1],
            'dept_name': dept_names.get(c.department_id, 'General (no department)'),
            'courses': 0, 'scheduled': 0, 'published': 0, 'drafts': 0,
        })
        published, drafts = classes.get(c.id, (0, 0))
        row['courses'] += 1
        row['scheduled'] += 1 if published else 0
        row['published'] += published
        row['drafts'] += drafts
    for row in rows.values():
        row['status'] = 'draft' if row['drafts'] else 'published' if row['published'] else 'none'
    # General last; "other" level last within a department.
    return sorted(rows.values(), key=lambda r: (r['dept'] == 'general', r['dept_name'].lower(),
                                                 r['level'] == 'other', r['level']))


# ==========================================
# TIMETABLE IMPORT (Student Affairs PDFs)
# ==========================================
# Two steps so nothing is saved unseen: "Read sheets" shows a preview,
# "Save as draft" saves it. The preview travels back with the confirm form as
# JSON and is re-checked from scratch there (timetable_import.plan_slots), so
# a stale or edited preview can't save anything the checks would reject.

def _draft_semesters(entries):
    """[(semester, draft classes, courses)] for semesters with drafts to publish."""
    out = {}
    for e in entries:
        if not e.is_published:
            sem, count, courses = out.get(e.semester_id, (e.semester, 0, set()))
            courses.add(e.course_id)
            out[e.semester_id] = (sem, count + 1, courses)
    return [(sem, count, len(courses)) for sem, count, courses in out.values()]


@admin_bp.route('/timetable/publish', methods=['POST'])
@limiter.limit("5 per minute")
def timetable_publish():
    """Publish a semester's draft timetable: students and lecturers see it,
    and everyone whose classes changed is told once (timetable_publish.py)."""
    semester = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
    if not semester:
        flash('Choose a semester to publish.', 'error')
        return redirect(url_for('admin.timetable_page'))
    drafts = Timetable.query.filter_by(semester_id=semester.id, is_published=False).all()
    if not drafts:
        flash(f"{semester.name} has no draft classes to publish.", 'info')
        return redirect(url_for('admin.timetable_page'))
    try:
        # Logged before publishing so the entry commits together with the swap.
        log_action('timetable.publish',
                   f"Published the {semester.name} timetable: {len(drafts)} classes for "
                   f"{len({d.course_id for d in drafts})} courses",
                   'semester', semester.id, {'classes': len(drafts)})
        result = publish_drafts(semester, session['user_id'])
        flash(f"Published {result['slots']} classes for {result['courses']} courses. "
              f"{result['notified']} student(s) and lecturer(s) were notified.", 'success')
    except Exception:
        db.session.rollback()
        log_exception("Timetable Publish Error")
        flash('Failed to publish the timetable. Nothing changed.', 'error')
    return redirect(url_for('admin.timetable_page'))


@admin_bp.route('/timetable/import', methods=['POST'])
@limiter.limit("10 per minute")
def timetable_import():
    semester = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
    if not semester:
        flash('Choose the semester to import into.', 'error')
        return redirect(url_for('admin.timetable_page'))

    uploads = [f for f in request.files.getlist('files') if f and f.filename]
    if not uploads:
        flash('Choose at least one PDF.', 'error')
        return redirect(url_for('admin.timetable_page'))
    if len(uploads) > tt_import.MAX_FILES:
        flash(f"Upload at most {tt_import.MAX_FILES} sheets at a time "
              f"(you chose {len(uploads)}). Reading each takes a few seconds.", 'error')
        return redirect(url_for('admin.timetable_page'))

    files = []
    for f in uploads:
        data = f.read(tt_import.MAX_FILE_BYTES + 1)
        if len(data) > tt_import.MAX_FILE_BYTES:
            flash(f"{f.filename} is over 5 MB -- that isn't a timetable sheet.", 'error')
            return redirect(url_for('admin.timetable_page'))
        files.append((f.filename, data))

    try:
        plan = tt_import.plan_sheets(files, semester)
    except Exception:
        log_exception("Timetable Import Read Error")
        flash('Something went wrong reading those sheets. Nothing was saved.', 'error')
        return redirect(url_for('admin.timetable_page'))
    return _render_import_preview(plan, semester)


@admin_bp.route('/timetable/import/confirm', methods=['POST'])
@limiter.limit("10 per minute")
def timetable_import_confirm():
    semester = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
    try:
        payload = json.loads(request.form.get('plan') or '{}')
    except ValueError:
        payload = None
    if not semester or not payload or payload.get('semester_id') != semester.id:
        flash('That preview is no longer valid. Upload the sheets again.', 'error')
        return redirect(url_for('admin.timetable_page'))

    try:
        plan = tt_import.plan_slots(payload, semester)
        if not plan.ok:
            # Something changed since the preview (a course deleted, a slot
            # added by hand that now clashes). Show the fresh result.
            flash('Something changed since the preview -- see the errors below. Nothing was saved.', 'error')
            return _render_import_preview(plan, semester)

        counts = tt_import.apply_plan(plan, semester, session['user_id'])
        sheets = ', '.join(sheet.title for sheet in plan.sheets)
        if plan.copied_from:
            log_action('timetable.copy',
                       f"Copied {counts['saved']} classes from {plan.copied_from} as draft "
                       f"for {semester.name} ({sheets})",
                       'semester', semester.id, {'copied_from': plan.copied_from, **counts})
        else:
            log_action('timetable.import',
                       f"Imported {counts['saved']} classes as draft for {semester.name} ({sheets})",
                       'semester', semester.id,
                       {'sheets': [sheet.filename for sheet in plan.sheets], **counts})
        db.session.commit()
        flash(f"Saved {counts['saved']} classes for {counts['courses']} courses as a draft. "
              "Students and lecturers won't see them until the timetable is published.", 'success')
    except Exception:
        db.session.rollback()
        log_exception("Timetable Import Save Error")
        flash('Failed to save the timetable. Nothing was saved.', 'error')
    return redirect(url_for('admin.timetable_page'))


@admin_bp.route('/timetable/copy', methods=['POST'])
@limiter.limit("10 per minute")
def timetable_copy():
    """Preview copying another semester's published classes into this one
    as drafts (by default the same semester last year). Same preview,
    checks and "Save as draft" as a PDF import -- see plan_copy()."""
    source = db.session.get(Semester, request.form.get('source_id', type=int) or 0)
    target = db.session.get(Semester, request.form.get('semester_id', type=int) or 0)
    dept, level = request.form.get('dept', ''), request.form.get('level', '')
    back = url_for('admin.timetable_page', **{k: v for k, v in (
        ('semester', target.id if target else None), ('dept', dept), ('level', level)) if v})
    if not source or not target or source.id == target.id:
        flash('Choose a different semester to copy from.', 'error')
        return redirect(back)

    # The page's department/level filter, applied to last year's courses.
    def keep(course):
        return (not dept or _dept_key(course) == dept) and (not level or _level_key(course) == level)

    try:
        plan = tt_import.plan_copy(source, target, keep)
    except Exception:
        log_exception("Timetable Copy Error")
        flash('Something went wrong preparing the copy. Nothing was saved.', 'error')
        return redirect(back)
    if plan is None:
        flash(f"{source.name} has no published classes to copy"
              + (' for this department and level.' if dept or level else '.'), 'info')
        return redirect(back)
    return _render_import_preview(plan, target)


def _render_import_preview(plan, semester):
    return render_template(
        'admin/timetable_import.html',
        plan=plan,
        semester=semester,
        plan_json=json.dumps(plan.to_json()),
        day_names=tt_import.DAY_NAMES,
        kind_names=KINDS,
        active_page='timetable',
    )


@admin_bp.route('/timetable/current', methods=['GET'])
def timetable_current():
    """
    JSON version of the same "what's happening right now" resolution the
    page renders server-side on load -- polled client-side (see
    timetable.html's extra_scripts) so the "Happening Now" banner updates
    live without a full page reload. The computation itself still runs
    entirely in resolve_current_course() on the backend; the frontend only
    displays whatever this endpoint returns.
    """
    # Scoped to the department/level being viewed (same query string as the
    # page); the all-departments view has no banner -- dozens of classes can
    # be on at once there.
    view = _timetable_view()
    return jsonify(resolve_current_course(
        semester=view['semester'],
        course_ids=[c.id for c in view['courses']] if view['is_grid'] else None))


# ==========================================
# SEMESTERS
# ==========================================
# ==========================================
# TERMINALS (READERS)
# ==========================================
# Each reader's code, room and Bluetooth number, and its own secret. See
# models.Terminal and terminal_rooms.py.

# A reader that has sent nothing for this long shows as offline. Readers
# ping /healthz about every 10 minutes and authenticate on every tap and
# offline upload, but last_seen_at only counts authenticated requests, so
# an idle reader between classes reads as offline -- "last seen" says when.
TERMINAL_ONLINE_WITHIN = timedelta(minutes=15)


def _terminal_form():
    """(code, name, room, ble_number) from the form, or raises ValueError
    with a message for the admin."""
    code = (request.form.get('code') or '').strip()
    name = (request.form.get('name') or '').strip()
    room = (request.form.get('room') or '').strip() or None
    ble = (request.form.get('ble_number') or '').strip()
    if not code or not name:
        raise ValueError('A reader needs a code and a name.')
    if len(code) > 32 or len(name) > 100 or (room and len(room) > 50):
        raise ValueError('Code up to 32 characters, name up to 100, room up to 50.')
    ble_number = None
    if ble:
        if not ble.isdigit() or not 1 <= int(ble) <= 65535:
            raise ValueError('The Bluetooth number must be 1 to 65535 (BLE_TERMINAL_NUMBER).')
        ble_number = int(ble)
    return code, name, room, ble_number


def _secret_fingerprint(terminal):
    """A short tag for a reader's CURRENT secret, put in its "New secret"
    form. Derived from the stored hash (never the secret), so it says
    nothing about the secret itself; it only changes when the secret does.

    The new secret is shown on the page the POST returns. Refreshing that
    page re-sent the form and issued a SECOND secret, silently killing the
    one just copied into the reader's secrets.h. A re-sent form carries the
    old fingerprint, so terminals_page can recognise it and refuse."""
    import hashlib
    return hashlib.sha256(f"fingerprint:{terminal.secret_hash}".encode()).hexdigest()[:16]


def _terminals_page(new_secret=None, for_terminal=None):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    terminals = Terminal.query.order_by(Terminal.code).all()
    return render_template(
        'admin/terminals.html',
        terminals=terminals,
        fingerprints={t.id: _secret_fingerprint(t) for t in terminals},
        online={t.id for t in terminals if t.last_seen_at and now - t.last_seen_at <= TERMINAL_ONLINE_WITHIN},
        rooms=sorted({r for (r,) in db.session.query(Timetable.room).distinct() if r}),
        room_check_mode=terminal_rooms.room_check_mode(),
        shared_secret_set=bool(os.environ.get('TERMINAL_SECRET', '').strip()),
        # Shown on this one page only, never stored or flashed: flash
        # messages ride in the session cookie, which is signed, not encrypted.
        new_secret=new_secret,
        new_secret_for=for_terminal,
        relative_time=_relative_time,
        active_page='terminals',
    )


@admin_bp.route('/terminals', methods=['GET', 'POST'])
@limiter.limit("20 per minute", methods=['POST'])
def terminals_page():
    # != 'POST', not == 'GET': Flask answers HEAD (uptime monitors, browser
    # prefetch) by running this view with method 'HEAD', which matched
    # neither branch, returned None and logged a 500 on Render.
    if request.method != 'POST':
        return _terminals_page()
    action = request.form.get('action')
    try:
        if action == 'create':
            code, name, room, ble_number = _terminal_form()
            if Terminal.query.filter_by(code=code).first():
                raise ValueError(f"A reader with code {code} already exists.")
            if ble_number and Terminal.query.filter_by(ble_number=ble_number).first():
                raise ValueError(f"Bluetooth number {ble_number} is already used by another reader.")
            secret = terminal_rooms.new_secret()
            terminal = Terminal(code=code, name=name, room=room, ble_number=ble_number,
                                secret_hash=terminal_rooms.hash_secret(secret))
            db.session.add(terminal)
            db.session.flush()
            log_action('terminal.create', f"Registered reader {code} ({name}, room {room or 'none'})",
                       'terminal', terminal.id, {'room': room, 'ble_number': ble_number})
            db.session.commit()
            return _terminals_page(new_secret=secret, for_terminal=terminal)

        terminal = db.session.get(Terminal, request.form.get('terminal_id', type=int) or 0)
        if terminal is None:
            raise ValueError('That reader no longer exists.')

        if action == 'update':
            code, name, room, ble_number = _terminal_form()
            if Terminal.query.filter(Terminal.code == code, Terminal.id != terminal.id).first():
                raise ValueError(f"A reader with code {code} already exists.")
            if ble_number and Terminal.query.filter(Terminal.ble_number == ble_number,
                                                    Terminal.id != terminal.id).first():
                raise ValueError(f"Bluetooth number {ble_number} is already used by another reader.")
            before = {'code': terminal.code, 'name': terminal.name, 'room': terminal.room,
                      'ble_number': terminal.ble_number}
            terminal.code, terminal.name, terminal.room, terminal.ble_number = code, name, room, ble_number
            diff = changes(before, {'code': code, 'name': name, 'room': room, 'ble_number': ble_number})
            if diff:
                log_action('terminal.update', f"Changed reader {terminal.code}", 'terminal', terminal.id,
                           {'changes': diff})
            db.session.commit()
            flash(f"Saved reader {terminal.code}.", 'success')

        elif action == 'regenerate':
            # A re-sent form (refresh after issuing one) carries the
            # fingerprint of a secret that's already been replaced: issuing
            # again would kill the secret just copied into the reader.
            if request.form.get('current') != _secret_fingerprint(terminal):
                flash(f"{terminal.code}'s secret was already replaced, so no new one was issued. "
                      f"If you've lost the one you were shown, click New secret again.", 'warning')
                return redirect(url_for('admin.terminals_page'))
            # For a lost or dumped reader: the old secret stops working now.
            secret = terminal_rooms.new_secret()
            terminal.secret_hash = terminal_rooms.hash_secret(secret)
            log_action('terminal.secret', f"Issued a new secret for reader {terminal.code}",
                       'terminal', terminal.id)
            db.session.commit()
            return _terminals_page(new_secret=secret, for_terminal=terminal)

        elif action == 'toggle':
            terminal.is_active = not terminal.is_active
            log_action('terminal.enable' if terminal.is_active else 'terminal.disable',
                       f"{'Enabled' if terminal.is_active else 'Disabled'} reader {terminal.code}",
                       'terminal', terminal.id)
            db.session.commit()
            flash(f"Reader {terminal.code} is now {'enabled' if terminal.is_active else 'disabled'}.",
                  'success')
        else:
            raise ValueError('Unknown action.')
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'error')
    except Exception:
        db.session.rollback()
        log_exception("Terminal Save Error")
        flash('Failed to save the reader. Nothing changed.', 'error')
    return redirect(url_for('admin.terminals_page'))


@admin_bp.route('/semesters', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def semesters_page():
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'activate':
            semester_id = request.form.get('semester_id')
            try:
                semester = Semester.query.get_or_404(int(semester_id))
                previous = Semester.query.filter_by(is_active=True).first()
                # Switching the active semester changes what every student
                # can register for, so the entry names what it replaced.
                log_action('semester.activate',
                           f"Made {semester.name} the active semester"
                           + (f" (was {previous.name})" if previous and previous.id != semester.id else ''),
                           'semester', semester.id,
                           {'previous_semester_id': previous.id if previous else None})
                # Deactivate every other semester in the SAME transaction --
                # is_active has no DB-level "only one true" constraint
                # (models.py's own comment on Semester.is_active flags this
                # exact requirement), so it's enforced here instead.
                Semester.query.update({Semester.is_active: False})
                semester.is_active = True
                db.session.commit()
                flash(f"'{semester.name}' is now the active semester.", 'success')
            except Exception:
                db.session.rollback()
                flash('Failed to activate semester.', 'error')
                log_exception("Semester Activation Error")
        else:
            # Each failure says what it is. Every exception here used to be
            # reported as "Semester name must be unique", a bad date included,
            # and an end date before the start was accepted.
            name = (request.form.get('name') or '').strip()
            try:
                start = datetime.strptime(request.form.get('start_date') or '', '%Y-%m-%d').date()
                end = datetime.strptime(request.form.get('end_date') or '', '%Y-%m-%d').date()
            except ValueError:
                start = end = None
            # End after start, a unique name, no overlap: the same rule as
            # Edit (record_edits.semester_problem).
            problem = (None if not name or start is None
                       else record_edits.semester_problem(name, start, end))
            if not name or start is None:
                flash('Name, start date and end date are all required.', 'error')
            elif problem:
                flash(problem, 'error')
            else:
                try:
                    semester = Semester(name=name, start_date=start, end_date=end)
                    db.session.add(semester)
                    db.session.flush()
                    log_action('semester.create', f"Created semester {semester.name}",
                               'semester', semester.id,
                               {'start_date': semester.start_date, 'end_date': semester.end_date})
                    db.session.commit()
                    flash(f"Semester '{name}' created.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Failed to create the semester. Nothing was saved.', 'error')
                    log_exception("Semester Create Error")

        return redirect(url_for('admin.semesters_page'))

    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    # What each semester holds, so "Set Active" can warn before switching
    # to an empty one: since the "now" screens follow the active semester
    # (utils.current_courses), activating one with no courses or no
    # published timetable empties every student's and lecturer's app.
    courses = dict(db.session.query(Course.semester_id, db.func.count(Course.id))
                   .filter(Course.semester_id.isnot(None)).group_by(Course.semester_id))
    slots = dict(db.session.query(Timetable.semester_id, db.func.count(Timetable.id))
                 .filter(Timetable.is_published.is_(True)).group_by(Timetable.semester_id))
    return render_template(
        'admin/semesters.html',
        semesters=semesters,
        delete_blockers=record_edits.delete_blockers('semesters', semesters),
        course_counts=courses,
        slot_counts=slots,
        active_page='semesters',
    )


# ==========================================
# HODS
# ==========================================
@admin_bp.route('/hods', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def hods_page():
    if request.method == 'POST':
        action = request.form.get('action', 'create_new')
        department_id = request.form.get('department_id')

        if not department_id:
            flash('A department is required to assign an HOD.', 'error')
            return redirect(url_for('admin.hods_page'))

        try:
            # GAP (also flagged in hods.html's own comment): nothing stops
            # a department getting a second HOD at the schema level --
            # HOD.department_id has no unique constraint in models.py.
            # Rejecting a duplicate assignment here since the schema
            # doesn't enforce it. Shared by both actions below.
            existing_hod = HOD.query.filter_by(department_id=int(department_id)).first()
            if existing_hod:
                flash(f"{existing_hod.department.name} already has an HOD assigned ({existing_hod.full_name}).", 'error')
                return redirect(url_for('admin.hods_page'))

            if action == 'promote_lecturer':
                lecturer_id = request.form.get('lecturer_id')
                if not lecturer_id:
                    flash('Select a lecturer to promote.', 'error')
                    return redirect(url_for('admin.hods_page'))

                lecturer = Lecturer.query.get(int(lecturer_id))
                if not lecturer:
                    flash('Lecturer not found.', 'error')
                    return redirect(url_for('admin.hods_page'))
                # On leave or left means their login is off (people_status):
                # they'd be an HOD who can't sign in. The form only lists
                # active lecturers; this catches a stale page.
                if lecturer.status != 'active':
                    flash(f"{lecturer.full_name} is marked {LECTURER_STATUSES.get(lecturer.status, lecturer.status)} "
                          f"and can't be made HOD.", 'error')
                    return redirect(url_for('admin.hods_page'))

                if HOD.query.filter_by(user_id=lecturer.user_id).first():
                    flash(f"{lecturer.full_name} is already an HOD.", 'error')
                    return redirect(url_for('admin.hods_page'))

                # Reuses the lecturer's existing User row (and therefore
                # their existing login credentials) instead of creating a
                # second account -- HOD becomes their primary role (what
                # they land on after login, matching login_required('hod')
                # gating admin_bp/hod_bp routes), but the Lecturer row is
                # deliberately left in place so login_required(('lecturer',
                # 'hod')) on blueprints/lecturer.py still lets them into
                # their own courses (see hod_bp's has_lecturer_profile
                # context flag, which is exactly this: an HOD account that
                # also still holds a Lecturer profile).
                user = User.query.get(lecturer.user_id)
                user.role = 'hod'

                hod = HOD(
                    full_name=lecturer.full_name,
                    staff_id=lecturer.staff_id,
                    department_id=int(department_id),
                    user_id=lecturer.user_id,
                )
                db.session.add(hod)
                db.session.flush()
                log_action('hod.promote',
                           f"Made lecturer {lecturer.full_name} HOD of {hod.department.name}",
                           'hod', hod.id,
                           {'lecturer_id': lecturer.id, 'department_id': hod.department_id})
                db.session.commit()
                flash(f"{lecturer.full_name} promoted to HOD.", 'success')

            else:
                full_name = request.form.get('full_name')
                staff_id = request.form.get('staff_id')

                if not all([full_name, staff_id]):
                    flash('Full name and staff ID are required to assign an HOD.', 'error')
                    return redirect(url_for('admin.hods_page'))

                existing_user = User.query.filter_by(username=staff_id.strip()).first()
                if existing_user:
                    flash('Staff ID is already registered as an active username.', 'error')
                    return redirect(url_for('admin.hods_page'))

                hashed_password = bcrypt.hashpw(staff_id.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                user = User(
                    username=staff_id.strip(),
                    password_hash=hashed_password,
                    role='hod',
                    is_active=True,
                    requires_password_change=True,
                )
                db.session.add(user)
                db.session.flush()

                hod = HOD(
                    full_name=full_name.strip(),
                    staff_id=staff_id.strip(),
                    department_id=int(department_id),
                    user_id=user.id,
                )
                db.session.add(hod)
                db.session.flush()
                log_action('hod.create',
                           f"Created HOD {hod.full_name} ({hod.staff_id}) for {hod.department.name}",
                           'hod', hod.id, {'department_id': hod.department_id})
                db.session.commit()
                flash(f"HOD account created successfully for {full_name}.", 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to assign HOD. Verify values.', 'error')
            log_exception("HOD Assignment Error")

        return redirect(url_for('admin.hods_page'))

    hods = HOD.query.options(joinedload(HOD.department), joinedload(HOD.user)).all()
    departments = Department.query.order_by(Department.name).all()
    by_department = {h.department_id: h for h in hods}
    # Only active lecturers not already promoted. Promoting flips User.role
    # to 'hod', so the role filter excludes anyone already promoted; the
    # status filter excludes lecturers on leave or gone, whose login is off.
    promotable_lecturers = (
        Lecturer.query.join(User, Lecturer.user_id == User.id)
        .filter(User.role == 'lecturer', Lecturer.status == 'active')
        .options(joinedload(Lecturer.department))
        .order_by(Lecturer.full_name)
        .all()
    )
    return render_template(
        'admin/hods.html',
        # One row per department, with its HOD or None (2026-10-18): the
        # page used to list only the HODs that exist, so finding the
        # departments WITHOUT one meant checking against Organization.
        rows=[{'department': d, 'hod': by_department.get(d.id)} for d in departments],
        hod_count=len(hods),
        # The assign forms offer only these: picking a department that
        # already had an HOD used to be refused after submitting, losing
        # the typed name and staff ID.
        free_departments=[d for d in departments if d.id not in by_department],
        departments=departments,
        # Promoted HODs' lecturer records, by user id: removing one sends
        # them back to teaching (the dialog says so), and a lecturer marked
        # on leave or left explains why the shared login is off.
        hod_lecturers={l.user_id: l for l in Lecturer.query.filter(
            Lecturer.user_id.in_([h.user_id for h in hods]))} if hods else {},
        lecturer_statuses=LECTURER_STATUSES,
        promotable_lecturers=promotable_lecturers,
        active_page='hods',
    )


# ==========================================
# ANNOUNCEMENTS
# ==========================================
@admin_bp.route('/announcements', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=['POST'])
def announcements_page():
    if request.method == 'POST':
        title = request.form.get('title')
        body = request.form.get('body')
        scope = request.form.get('scope')
        department_id = request.form.get('department_id') or None
        course_id = request.form.get('course_id') or None

        if not all([title, body, scope]):
            flash('Title, body, and scope are all required.', 'error')
            return redirect(url_for('admin.announcements_page'))
        # A department or course announcement needs its department or course.
        # Without this check one was saved with neither -- and reached nobody
        # (utils.announcement_user_ids returns [] for it).
        if scope not in ('university', 'department', 'course'):
            flash('Choose who the announcement is for.', 'error')
            return redirect(url_for('admin.announcements_page'))
        if scope == 'department' and not db.session.get(Department, request.form.get('department_id', type=int) or 0):
            flash('Choose the department this announcement is for.', 'error')
            return redirect(url_for('admin.announcements_page'))
        if scope == 'course' and not db.session.get(Course, request.form.get('course_id', type=int) or 0):
            flash('Choose the course this announcement is for.', 'error')
            return redirect(url_for('admin.announcements_page'))

        try:
            announcement = Announcement(
                title=title.strip(),
                body=body.strip(),
                sender_id=session['user_id'],
                scope=scope,
                department_id=int(department_id) if scope == 'department' and department_id else None,
                course_id=int(course_id) if scope == 'course' and course_id else None,
            )
            db.session.add(announcement)
            db.session.flush()
            log_action('announcement.create',
                       f"Posted {scope} announcement \"{announcement.title}\"",
                       'announcement', announcement.id,
                       {'scope': scope, 'department_id': announcement.department_id,
                        'course_id': announcement.course_id})
            db.session.commit()

            # Notify every student it reaches, in bulk -- after the commit,
            # and a push failure never fails the request (see notify_users).
            notify_announcement(announcement)

            flash(f"Announcement '{title}' posted successfully.", 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to post announcement.', 'error')
            log_exception("Announcement Create Error")

        return redirect(url_for('admin.announcements_page'))

    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    departments = Department.query.order_by(Department.name).all()
    # This semester's courses (utils.current_courses): it listed every
    # semester's, so MCT401 appeared once per semester, identically.
    courses = current_courses(Course.query).order_by(Course.course_code).all()
    # How many students each choice notifies -- the same rule as
    # utils.announcement_user_ids -- so posting can say "notify 6,240
    # students?" before a push goes to every phone it reaches.
    audience = {
        'university': Student.query.count(),
        'departments': dict(db.session.query(Student.department_id, db.func.count(Student.id))
                            .group_by(Student.department_id)),
        'courses': dict(db.session.query(Enrollment.course_id, db.func.count(Enrollment.student_id))
                        .filter(Enrollment.course_id.in_([c.id for c in courses]))
                        .group_by(Enrollment.course_id)) if courses else {},
    }
    return render_template(
        'admin/announcements.html',
        announcements=announcements,
        departments=departments,
        courses=courses,
        audience=audience,
        active_page='announcements',
    )


@admin_bp.route('/announcements/<int:announcement_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_announcement(announcement_id):
    """Soft-delete: flips is_active rather than removing the row, so the
    announcement disappears from lecturer/mobile audience views immediately
    but stays visible here (grayed out, see the 'Inactive' badge in
    admin/announcements.html) as an audit trail. Admin can delete any
    announcement regardless of who posted it -- no ownership check, unlike
    the lecturer-side equivalent in blueprints/lecturer.py."""
    announcement = Announcement.query.get(announcement_id)
    if not announcement:
        flash('Announcement not found.', 'error')
        return redirect(url_for('admin.announcements_page'))

    try:
        announcement.is_active = False
        log_action('announcement.delete', f"Deleted announcement \"{announcement.title}\"",
                   'announcement', announcement.id)
        db.session.commit()
        flash(f"Announcement '{announcement.title}' deleted.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to delete announcement.', 'error')
        log_exception("Announcement Delete Error")

    return redirect(url_for('admin.announcements_page'))


# ==========================================
# REPORTS
# ==========================================
def _all_course_attendance_reports(semester=None):
    """
    System-wide per-course attendance percentage, shared by reports_page()
    and export_reports() so the on-screen table and the exported CSV can't
    drift apart. The shared attendance rule (utils.course_attendance):
    finished classes, present or late.

    PERF: this ran three counting queries per course -- 1,500 round trips
    to the database for 500 courses, on every page load and every export.
    Now a fixed handful, with each course's lecturers and department loaded
    up front.
    """
    # One semester's courses plus those with no semester (utils.current_courses,
    # with the semester given rather than assumed).
    courses = (current_courses(Course.query, semester)
               .options(joinedload(Course.department), joinedload(Course.lecturer))
               .order_by(Course.course_code).all())
    stats = course_attendance([c.id for c in courses])
    rows = []
    for course in courses:
        s = stats[course.id]
        rows.append({
            'course': course,
            'lecturer_name': course.lecturer_summary or 'Unassigned',
            'department_name': course.department.name if course.department else 'Unassigned',
            'enrolled_count': s['enrolled'],
            'session_count': s['held'],
            'average_attendance': s['pct'],
        })
    return rows


# ==========================================
# ACTIVITY (audit trail)
# ==========================================
ACTIVITY_PER_PAGE = 50

# The Activity page's "What" filter: the part of an action name before the
# dot ("student.create" -> "student"), with a readable label. Order is the
# dropdown order.
ACTIVITY_CATEGORIES = {
    'auth': 'Sign-ins & passwords',
    'admin': 'Admin accounts',
    'student': 'Students',
    'enrollment': 'Enrolments',
    'lecturer': 'Lecturers',
    'hod': 'HODs',
    'course': 'Courses',
    'timetable': 'Timetable',
    'semester': 'Semesters',
    'faculty': 'Faculties',
    'department': 'Departments',
    'announcement': 'Announcements',
    'report': 'Reports',
}


def _activity_tone(action):
    """Pill colour for an action: deletions and failed sign-ins stand out."""
    if action.endswith('.delete') or action == 'admin.disable':
        return 'error'
    if action in ('auth.login_failed', 'student.unbind', 'semester.activate') \
            or action.endswith('.status') or action.endswith('.bulk_status') \
            or action.endswith('.password_reset'):
        return 'warning'
    if action.endswith('.create') or action.endswith('.bulk_import') or action == 'hod.promote':
        return 'success'
    return 'neutral'


@admin_bp.route('/activity', methods=['GET'])
def activity_page():
    """Who changed what, newest first. Read-only: nothing here edits or
    deletes an entry, which is what makes the trail worth trusting."""
    who = request.args.get('who', '').strip()
    what = request.args.get('what', '').strip()
    page = request.args.get('page', 1, type=int)

    query = AuditLog.query
    if who:
        query = query.filter(AuditLog.actor_label == who)
    if what in ACTIVITY_CATEGORIES:
        query = query.filter(AuditLog.action.like(f'{what}.%'))
    pagination = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).paginate(
        page=page, per_page=ACTIVITY_PER_PAGE, error_out=False,
    )

    # Everyone who appears in the log, including people whose accounts have
    # since been disabled -- their past changes still need to be findable.
    people = [row.actor_label for row in
              db.session.query(AuditLog.actor_label).distinct().order_by(AuditLog.actor_label)]

    filter_args = {k: v for k, v in (('who', who), ('what', what)) if v}
    return render_template(
        'admin/activity.html',
        entries=[(e, _activity_tone(e.action)) for e in pagination.items],
        pagination=pagination,
        people=people,
        categories=ACTIVITY_CATEGORIES,
        filters={'who': who, 'what': what},
        filter_args=filter_args,
        is_filtered=bool(filter_args),
        active_page='activity',
    )


# ==========================================
# ANALYTICS
# ==========================================
# Semester-wide patterns: who is below exam eligibility, and which
# timetabled classes never ran. Rules in analytics.py.

def _analytics_filters():
    """(semester, department id or None, level or '') from the query string.

    The semester is chosen on the page (?semester=<id>), defaulting to the
    active one. Looking at last semester used to mean making it the ACTIVE
    semester, which also changes what every student and lecturer sees
    (timetable, course registration, today's classes)."""
    level = (request.args.get('level') or '').strip()
    semester = db.session.get(Semester, request.args.get('semester', type=int) or 0)
    if semester is None:
        semester = Semester.query.filter_by(is_active=True).first()
    return semester, request.args.get('dept', type=int), level if level in VALID_LEVELS else ''


@admin_bp.route('/analytics', methods=['GET'])
def analytics_page():
    semester, dept_id, level = _analytics_filters()
    return render_template(
        'admin/analytics.html',
        semester=semester,
        semesters=Semester.query.order_by(Semester.start_date.desc(), Semester.id.desc()).all(),
        eligibility=analytics.eligibility(semester, dept_id, level),
        # Delivery is by course department; a student's level doesn't apply.
        delivery=analytics.delivery(semester, dept_id),
        departments=Department.query.order_by(Department.name).all(),
        valid_levels=VALID_LEVELS,
        filters={'dept': dept_id, 'level': level},
        # Only the first rows on screen; the CSV has everyone.
        list_limit=ANALYTICS_LIST_LIMIT,
        active_page='analytics',
    )


ANALYTICS_LIST_LIMIT = 100


@admin_bp.route('/analytics/eligibility.csv', methods=['GET'])
def analytics_eligibility_csv():
    """Every student below the threshold, one row per course they're below
    in, for the same filters (semester included) as the page."""
    semester, dept_id, level = _analytics_filters()
    data = analytics.eligibility(semester, dept_id, level)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f"Below {data['threshold']}% attendance -- "
                     f"{semester.name if semester else 'no semester'}"])
    writer.writerow(['Matric Number', 'Full Name', 'Level', 'Department', 'Course',
                     'Attended', 'Classes Held', 'Attendance (%)'])
    for row in data['students']:
        st = row['student']
        for c in row['courses']:
            writer.writerow([_csv_safe(st.matric_number), _csv_safe(st.full_name), _csv_safe(st.level),
                             _csv_safe(st.department.name if st.department else ''),
                             _csv_safe(c['course'].course_code), c['attended'], c['held'], c['pct']])
    log_action('analytics.export', f"Exported the below-{data['threshold']}% list "
               f"({len(data['students'])} students)", 'report', None,
               {'semester_id': semester.id if semester else None,
                'department_id': dept_id, 'level': level or None})
    db.session.commit()
    return Response(
        output.getvalue(), mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=below_eligibility.csv'},
    )


@admin_bp.route('/reports', methods=['GET'])
def reports_page():
    semester = _reports_semester()
    try:
        course_reports = _all_course_attendance_reports(semester)
    except Exception:
        log_exception("Admin Reports Error")
        flash('An error occurred loading reports.', 'error')
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/reports.html',
        course_reports=course_reports,
        semester=semester,
        semesters=Semester.query.order_by(Semester.start_date.desc()).all(),
        active_page='reports',
    )


def _reports_semester():
    """The semester a report is for: ?semester=, else the active one, else
    the latest. Reports used to cover every course ever, so each code
    appeared once per semester and the CSV mixed years together."""
    semester = db.session.get(Semester, request.args.get('semester', type=int) or 0)
    return (semester or Semester.query.filter_by(is_active=True).first()
            or Semester.query.order_by(Semester.start_date.desc()).first())


@admin_bp.route('/reports/export', methods=['GET'])
def export_reports():
    semester = _reports_semester()
    try:
        course_reports = _all_course_attendance_reports(semester)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Course Code', 'Course Title', 'Department', 'Lecturer',
                          'Enrolled', 'Sessions Run', 'Average Attendance (%)'])
        for row in course_reports:
            writer.writerow([
                row['course'].course_code,
                row['course'].course_title,
                row['department_name'],
                row['lecturer_name'],
                row['enrolled_count'],
                row['session_count'],
                row['average_attendance'],
            ])
        # Changes nothing, but it's data leaving the system -- worth knowing
        # who took a copy and when.
        log_action('report.export',
                   f"Downloaded the attendance report for {semester.name if semester else 'all semesters'} "
                   f"({len(course_reports)} courses)",
                   'report', None, {'semester_id': semester.id if semester else None})
        db.session.commit()
    except Exception:
        db.session.rollback()
        log_exception("Admin Reports Export Error")
        flash('Failed to export attendance report.', 'error')
        return redirect(url_for('admin.reports_page', **({'semester': semester.id} if semester else {})))

    # Named after the semester, so two downloads can't be confused.
    label = re.sub(r'[^A-Za-z0-9]+', '_', semester.name).strip('_') if semester else 'all'
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=attendance_report_{label}.csv'},
    )
