import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
import bcrypt
from sqlalchemy import or_, insert as sa_insert
from sqlalchemy.orm import joinedload
from models import (
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, HOD, Semester, Announcement, Timetable,
    AuditLog,
)
from extensions import log_exception, logger, limiter
from campus_time import campus_now
from utils import (
    resolve_current_course, session_status_for_course, notify_announcement,
    VALID_LEVELS, normalize_level, course_level, _csv_safe,
)
from push_notifications import send_push_notification
from audit import log_action, changes
# Aliased: the route below is also called timetable_import (its URL
# endpoint name), which would otherwise replace the module.
import timetable_import as tt_import
from timetable_pdf import KINDS
from timetable_publish import publish_drafts, published_schedules, notify_schedule_changes
import bulk_upload
import people_status
import promotion
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
    individually."""
    return {'active_semester': Semester.query.filter_by(is_active=True).first()}


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
    """
    Renders the administrative dashboard: system-wide counts, live session
    count, per-department attendance rates, and a recent-activity feed.
    """
    try:
        total_students = Student.query.count()
        total_lecturers = Lecturer.query.count()
        total_courses = Course.query.count()
        total_departments = Department.query.count()
        total_faculties = Faculty.query.count()
        live_sessions = SessionModel.query.filter_by(is_active=True).count()

        # Per-department attendance rate, using the same "% of theoretically
        # possible attendance" formula already used in api/lecturer.py's
        # avg_attendance (total_attendance / (total_sessions * enrolled_count)),
        # just scoped to every course in a department instead of one course.
        # Departments with no courses yet are skipped rather than shown as
        # 0% -- there's nothing to measure yet, that's not the same as poor
        # attendance.
        department_attendance = []
        for dept in Department.query.all():
            course_ids = [c.id for c in Course.query.filter_by(department_id=dept.id).all()]
            if not course_ids:
                continue
            total_sessions = SessionModel.query.filter(SessionModel.course_id.in_(course_ids)).count()
            enrolled_count = Enrollment.query.filter(Enrollment.course_id.in_(course_ids)).count()
            total_attendance = (
                Attendance.query
                .join(SessionModel, Attendance.session_id == SessionModel.id)
                .filter(SessionModel.course_id.in_(course_ids))
                .count()
            )
            pct = round(
                (total_attendance / (total_sessions * enrolled_count) * 100)
                if total_sessions and enrolled_count else 0,
                1,
            )
            department_attendance.append({'name': dept.name, 'percentage': pct})

        # Recent activity: most recent check-ins. Session start/end events
        # aren't merged in here -- Session only stores session_date/
        # start_time as separate Date/Time columns (no single datetime),
        # so sorting them against Attendance.time_in would need combining
        # those first. Deferred rather than guessed at.
        recent_activity = []
        recent_attendance = (
            Attendance.query
            .join(SessionModel, Attendance.session_id == SessionModel.id)
            .join(Course, SessionModel.course_id == Course.id)
            .order_by(Attendance.time_in.desc())
            .limit(8)
            .all()
        )
        for att in recent_attendance:
            recent_activity.append({
                'icon': 'check_circle',
                'color': 'success',
                'message': f"{att.student.full_name} checked into {att.session.course.course_code}",
                'time': _relative_time(att.time_in),
            })

        return render_template(
            'admin/dashboard.html',
            total_students=total_students,
            total_lecturers=total_lecturers,
            total_courses=total_courses,
            total_departments=total_departments,
            total_faculties=total_faculties,
            live_sessions=live_sessions,
            department_attendance=department_attendance,
            recent_activity=recent_activity,
            active_page='dashboard',
        )
    except Exception:
        log_exception("Admin Dashboard Error")
        flash("An error occurred while loading administrative dashboard metrics.", "error")
        return redirect(url_for('auth.login'))


# ==========================================
# ORGANIZATION (Faculties + Departments)
# ==========================================
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

    faculties = Faculty.query.all()
    departments = Department.query.all()
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
    dept_counts = {d.id: {'students': 0, 'lecturers': 0, 'courses': 0} for d in departments}
    for model, key in ((Student, 'students'), (Lecturer, 'lecturers'), (Course, 'courses')):
        for dept_id, n in (db.session.query(model.department_id, db.func.count(model.id))
                           .group_by(model.department_id)):
            if dept_id in dept_counts:
                dept_counts[dept_id][key] = n
    faculty_counts = {}
    for d in departments:
        totals = faculty_counts.setdefault(d.faculty_id, {'departments': 0, 'students': 0,
                                                          'lecturers': 0, 'courses': 0})
        totals['departments'] += 1
        for key, n in dept_counts[d.id].items():
            totals[key] += n
    return dept_counts, faculty_counts


# Programme lengths the school runs: levels stop at 500 (VALID_LEVELS).
PROGRAMME_YEARS = (4, 5)


def _cascade_counts(department_ids):
    """How many students, lecturers and courses sit under these departments
    -- what a cascade delete is about to remove. Recorded in the audit log."""
    if not department_ids:
        return {'students': 0, 'lecturers': 0, 'courses': 0}
    return {
        'students': Student.query.filter(Student.department_id.in_(department_ids)).count(),
        'lecturers': Lecturer.query.filter(Lecturer.department_id.in_(department_ids)).count(),
        'courses': Course.query.filter(Course.department_id.in_(department_ids)).count(),
    }


def _describe_counts(counts):
    """{'students': 3, 'courses': 0} -> '3 students'. 'nothing else' if all 0."""
    parts = [f"{n} {name if n != 1 else name[:-1]}" for name, n in counts.items() if n]
    return ', '.join(parts) if parts else 'nothing else'


@admin_bp.route('/faculties/<int:faculty_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_faculty(faculty_id):
    """
    Deletes a Faculty and cascades to every Department beneath it (and
    everything under those -- Students, Lecturers, Courses, etc.), per the
    cascade="all, delete-orphan" relationships in models.py. The
    type-the-name-to-confirm modal in organization.html is the only
    safeguard before this fires -- there's no "are you sure" here.
    """
    faculty = Faculty.query.get_or_404(faculty_id)
    try:
        name = faculty.name
        # Counted BEFORE the delete: afterwards there is nothing left to
        # count. This is the entry you'd look for after an accident, and
        # "deleted faculty X" alone wouldn't say how much went with it.
        dept_ids = [d.id for d in faculty.departments]
        removed = _cascade_counts(dept_ids)
        removed['departments'] = len(dept_ids)
        db.session.delete(faculty)
        log_action('faculty.delete',
                   f"Deleted faculty {name} and everything under it "
                   f"({_describe_counts(removed)})",
                   'faculty', faculty_id, {'removed': removed})
        db.session.commit()
        flash(f"Faculty '{name}' and everything under it was deleted.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to delete faculty.', 'error')
        log_exception("Faculty Delete Error")
    return redirect(url_for('admin.organization_page'))


@admin_bp.route('/departments/<int:department_id>/delete', methods=['POST'])
@limiter.limit("10 per minute")
def delete_department(department_id):
    """Deletes a Department, cascading to its Students, Lecturers, and
    Courses. Same caveat as delete_faculty above."""
    department = Department.query.get_or_404(department_id)
    try:
        name = department.name
        removed = _cascade_counts([department.id])  # before the delete; see delete_faculty
        db.session.delete(department)
        log_action('department.delete',
                   f"Deleted department {name} and everything under it "
                   f"({_describe_counts(removed)})",
                   'department', department_id, {'removed': removed})
        db.session.commit()
        flash(f"Department '{name}' and everything under it was deleted.", 'success')
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

    lecturers = Lecturer.query.all()
    departments = Department.query.all()
    return render_template(
        'admin/lecturers.html',
        lecturers=lecturers,
        departments=departments,
        lecturer_statuses=LECTURER_STATUSES,
        active_page='lecturers',
    )


# ==========================================
# BULK UPLOAD: LECTURERS AND COURSES
# ==========================================
# Upload -> preview -> confirm, like the timetable import. Nothing is saved
# by the upload itself; the preview's rows come back with the confirm form
# as JSON and are checked again from scratch there. See bulk_upload.py.

BULK_PAGES = {'lecturers': 'admin.lecturers_page', 'courses': 'admin.courses_page'}


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
        rows = bulk_upload.read_csv(data, kind)
        plan = (bulk_upload.plan_lecturers(rows, upload.filename) if kind == 'lecturers'
                else bulk_upload.plan_courses(rows, upload.filename, semester))
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
    back = url_for(BULK_PAGES[kind])
    semester = db.session.get(Semester, payload.get('semester_id') or 0) if kind == 'courses' else None

    try:
        plan = bulk_upload.plan_from_json(payload, semester)
        if not plan.ok:
            # Something changed since the preview (someone added the same
            # staff ID, a department was renamed). Show the fresh result.
            flash('Something changed since the preview -- see the errors below. Nothing was saved.', 'error')
            return _render_bulk_preview(plan, semester)

        if kind == 'lecturers':
            created = bulk_upload.apply_lecturers(plan)
            what = f"{created} lecturers"
        else:
            created = bulk_upload.apply_courses(plan, semester)
            what = f"{created} courses for {semester.name}"
        skipped = plan.count('exists')
        # One entry for the whole file, like the student upload.
        log_action(f"{kind[:-1]}.bulk_import",
                   f"Uploaded {plan.filename}: {what} created, {skipped} already existed",
                   kind[:-1], None,
                   {'filename': plan.filename, 'created': created, 'skipped_existing': skipped,
                    'semester_id': semester.id if semester else None})
        db.session.commit()
        flash(f"Created {what}." + (f" {skipped} already existed and were left unchanged." if skipped else '')
              + (" Each signs in with their staff ID as the first password." if kind == 'lecturers' and created else ''),
              'success')
    except bulk_upload.BulkCsvError as e:
        flash(f"{e} Nothing was saved.", 'error')
    except Exception:
        db.session.rollback()
        log_exception("Bulk Upload Save Error")
        flash('Failed to save the upload. Nothing was saved.', 'error')
    return redirect(back)


def _render_bulk_preview(plan, semester):
    return render_template(
        'admin/bulk_preview.html',
        plan=plan,
        semester=semester,
        plan_json=json.dumps(plan.to_json()),
        back_url=url_for(BULK_PAGES[plan.kind]),
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
    back = url_for(page, **{k: v for k, v in request.args.items() if k in STUDENT_FILTER_ARGS})
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
    query = query.options(
        joinedload(Student.department), joinedload(Student.user),
    ).order_by(Student.id.desc())

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
        filter_args=filter_args,
        is_filtered=bool(filter_args),
        active_page='students',
    )


# Largest CSV accepted in one upload. With the batched inserts below, 1,000
# rows is a few seconds even on Render's free tier -- well inside the
# request timeout. Bigger files are refused outright rather than half-run.
BULK_UPLOAD_MAX_ROWS = 1000

# Rows per IN (...) lookup and per INSERT batch. Keeps each statement well
# under MySQL's max_allowed_packet however big the file is.
_BULK_CHUNK = 500

# bcrypt cost for DEFAULT passwords created by a bulk upload. Every other
# password in the app uses bcrypt's default (12).
#
# Why lower here: the default password IS the student's matric number --
# printed on their ID card and present in the uploaded CSV. A slow hash
# protects a password an attacker can't guess; it adds nothing to one they
# already know. What protects these accounts is the forced change at first
# sign-in, and the new password is hashed at full cost (12) by the
# change-password routes. Meanwhile cost 12 is ~0.3s per hash on a fast PC
# and roughly 3s on Render's free tier, which is what made uploads time out.
# Cost 4 (bcrypt's minimum) is ~1ms.
BULK_DEFAULT_PASSWORD_ROUNDS = 4


def _existing_values(column, values):
    """Which of `values` already exist in `column`, in a few IN queries."""
    found = set()
    unique = list(dict.fromkeys(values))
    for i in range(0, len(unique), _BULK_CHUNK):
        chunk = unique[i:i + _BULK_CHUNK]
        found.update(v for (v,) in db.session.query(column).filter(column.in_(chunk)))
    return found


def _bulk_create_students(valid):
    """Insert users + student profiles for pre-validated rows.

    Bulk INSERTs (one multi-row statement per chunk) instead of one ORM
    object and flush per student. Users go in first; their ids are read
    back by username in one query, since MySQL can't return generated ids
    from a multi-row INSERT. Not committed here -- the caller commits
    together with its audit entry.
    """
    for i in range(0, len(valid), _BULK_CHUNK):
        chunk = valid[i:i + _BULK_CHUNK]
        db.session.execute(sa_insert(User), [
            {
                'username': matric,
                # Default password = the student's own matric number.
                'password_hash': bcrypt.hashpw(
                    matric.encode('utf-8'),
                    bcrypt.gensalt(BULK_DEFAULT_PASSWORD_ROUNDS),
                ).decode('utf-8'),
                'role': 'student',
                'is_active': True,
                'requires_password_change': True,
            }
            for matric, _name, _level, _dept, _rfid in chunk
        ])
        user_ids = dict(
            db.session.query(User.username, User.id)
            .filter(User.username.in_([row[0] for row in chunk]))
        )
        db.session.execute(sa_insert(Student), [
            {
                'full_name': name,
                'matric_number': matric,
                'level': level,
                'rfid_uid': rfid,
                'department_id': dept_id,
                'user_id': user_ids[matric],
            }
            for matric, name, level, dept_id, rfid in chunk
        ])


@admin_bp.route('/students/bulk-enroll', methods=['POST'])
@limiter.limit("10 per minute")
def bulk_enroll_students():
    """
    Processes university-scale bulk enrollments from an uploaded CSV file.
    Expects columns: matric_number, full_name, level, department_name, rfid_uid
    """
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.students_page'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin.students_page'))

    if not file.filename.endswith('.csv'):
        flash('Invalid file format. Please upload a structured .csv file.', 'error')
        return redirect(url_for('admin.students_page'))

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        required_cols = {'matric_number', 'full_name', 'level', 'department_name'}
        if not required_cols.issubset(set(csv_reader.fieldnames or [])):
            flash('CSV missing required headers: matric_number, full_name, level, department_name', 'error')
            return redirect(url_for('admin.students_page'))

        rows = list(csv_reader)
        if len(rows) > BULK_UPLOAD_MAX_ROWS:
            flash(f"This file has {len(rows)} rows. Upload at most {BULK_UPLOAD_MAX_ROWS} at a time: "
                  f"split it into smaller files. Nothing was saved.", 'error')
            return redirect(url_for('admin.students_page'))

        # PERF: this used to do everything per row -- two lookup queries, a
        # savepoint, two flushed INSERTs and a full-strength bcrypt hash --
        # so about 6 database round trips and ~3s of CPU per student on
        # Render's free tier. Gunicorn kills a request after 30s, so any
        # upload past ~10 students died with a 502, freezing the site for
        # everyone while it ran. Now: validate every row in memory against
        # three up-front lookups, then insert all valid rows in bulk. The
        # round trips no longer grow with the file size.
        departments = {d.name.strip().lower(): d for d in Department.query.all()}
        matrics = [r['matric_number'].strip() for r in rows if (r.get('matric_number') or '').strip()]
        rfids = [r['rfid_uid'].strip() for r in rows if (r.get('rfid_uid') or '').strip()]
        # Lower-cased: MySQL's default collation compares case-insensitively,
        # so "mct/19/0001" would collide with "MCT/19/0001" at INSERT time.
        taken_matrics = {m.lower() for m in _existing_values(User.username, matrics)}
        taken_matrics |= {m.lower() for m in _existing_values(Student.matric_number, matrics)}
        taken_rfids = {r.lower() for r in _existing_values(Student.rfid_uid, rfids)}

        error_count = 0
        skipped_records = []
        valid = []  # (matric, name, level, department_id, rfid)

        for row in rows:
            matric_no = (row.get('matric_number') or '').strip()
            name = (row.get('full_name') or '').strip()
            level_str = (row.get('level') or '').strip()
            dept_name = (row.get('department_name') or '').strip()
            rfid = (row.get('rfid_uid') or '').strip() or None

            if not matric_no or not name or not level_str or not dept_name:
                error_count += 1
                skipped_records.append(f"{name or 'Unknown'} (Incomplete Row fields)")
                continue

            # Same rule as the Add Student form. A bad level skips just this
            # row (reported below like every other skipped row) rather than
            # failing the whole upload.
            level = normalize_level(level_str)
            if level is None:
                error_count += 1
                skipped_records.append(f"{name} (Invalid level '{level_str}': use 100-500)")
                continue

            department = departments.get(dept_name.lower())
            if not department:
                error_count += 1
                skipped_records.append(f"{name} (Department '{dept_name}' not found)")
                continue

            # Checked against the database AND earlier rows of this same
            # file: a matric number or RFID that appears twice in one upload
            # would otherwise fail the whole batch at INSERT time.
            if matric_no.lower() in taken_matrics:
                error_count += 1
                skipped_records.append(f"{name} (Matric number already registered)")
                continue
            if rfid and rfid.lower() in taken_rfids:
                error_count += 1
                skipped_records.append(f"{name} (RFID UID '{rfid}' already in use)")
                continue

            taken_matrics.add(matric_no.lower())
            if rfid:
                taken_rfids.add(rfid.lower())
            valid.append((matric_no, name, level, department.id, rfid))

        success_count = len(valid)
        if valid:
            _bulk_create_students(valid)

        # One entry for the whole file, not one per row -- a 2,000-row
        # upload would otherwise bury every other entry on the Activity
        # page. The first skipped rows are kept so "why were 12 skipped?"
        # can be answered from the log.
        if success_count or error_count:
            log_action(
                'student.bulk_import',
                f"Uploaded {file.filename}: {success_count} students created, "
                f"{error_count} skipped",
                'student', None,
                {
                    'filename': file.filename,
                    'created': success_count,
                    'skipped': error_count,
                    'skipped_examples': skipped_records[:20],
                },
            )
        db.session.commit()

        if success_count > 0:
            flash(f"Successfully enrolled {success_count} students in bulk. Default credentials set.", 'success')
        if error_count > 0:
            flash(f"Skipped {error_count} records due to validation issues. View logs.", 'warning')
            logger.warning(f"Skipped rows: {skipped_records}")

    except Exception:
        db.session.rollback()
        # All-or-nothing: rows are validated first and saved in one
        # transaction, so a failure here (bad encoding, or a matric number
        # someone else registered a moment ago) saves none of the file.
        flash('Failed to process the CSV. Nothing was saved -- check the file and try again.', 'error')
        log_exception("Bulk CSV Execution Error")

    return redirect(url_for('admin.students_page'))


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
                return redirect(url_for('admin.courses_page'))

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

            return redirect(url_for('admin.courses_page'))

            try:
                existing = Enrollment.query.filter_by(
                    student_id=int(student_id), course_id=int(course_id)
                ).first()
                if existing:
                    flash('That student is already enrolled in this course.', 'error')
                else:
                    enrollment = Enrollment(student_id=int(student_id), course_id=int(course_id))
                    db.session.add(enrollment)
                    student = db.session.get(Student, int(student_id))
                    course = db.session.get(Course, int(course_id))
                    log_action('enrollment.create',
                               f"Enrolled {student.full_name if student else f'student #{student_id}'}"
                               f" in {course.course_code if course else f'course #{course_id}'}",
                               'enrollment', None,
                               {'student_id': int(student_id), 'course_id': int(course_id)})
                    db.session.commit()
                    flash('Student enrolled successfully.', 'success')
            except Exception:
                db.session.rollback()
                flash('Failed to enroll student.', 'error')
                log_exception("Enrollment Create Error")

            return redirect(url_for('admin.courses_page'))

        if action == 'manage_lecturer':
            _manage_course_lecturer(
                request.form.get('course_id'),
                (request.form.get('staff_id') or '').strip(),
                request.form.get('change'),
            )
            return redirect(url_for('admin.courses_page'))

        title = request.form.get('title')
        code = request.form.get('code')
        department_id = request.form.get('department_id')
        lecturer_id = request.form.get('lecturer_id')
        semester_id = request.form.get('semester_id') or None
        credit_units = request.form.get('credit_units') or None

        if not all([title, code, department_id, lecturer_id]):
            flash('All academic course parameters must be specified.', 'error')
            return redirect(url_for('admin.courses_page'))

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

        return redirect(url_for('admin.courses_page'))

    courses = Course.query.all()
    departments = Department.query.all()
    # Only active lecturers can be given a course; on leave or left can't.
    lecturers = Lecturer.query.filter_by(status='active').order_by(Lecturer.full_name).all()
    semesters = Semester.query.all()
    return render_template(
        'admin/courses.html',
        courses=courses,
        departments=departments,
        lecturers=lecturers,
        semesters=semesters,
        active_page='courses',
    )


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
            name = request.form.get('name')
            start_date = request.form.get('start_date')
            end_date = request.form.get('end_date')
            if not all([name, start_date, end_date]):
                flash('Name, start date, and end date are all required.', 'error')
            else:
                try:
                    semester = Semester(
                        name=name.strip(),
                        start_date=datetime.strptime(start_date, '%Y-%m-%d').date(),
                        end_date=datetime.strptime(end_date, '%Y-%m-%d').date(),
                    )
                    db.session.add(semester)
                    db.session.flush()
                    log_action('semester.create', f"Created semester {semester.name}",
                               'semester', semester.id,
                               {'start_date': semester.start_date, 'end_date': semester.end_date})
                    db.session.commit()
                    flash(f"Semester '{name}' created successfully.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Semester name must be unique.', 'error')
                    log_exception("Semester Create Error")

        return redirect(url_for('admin.semesters_page'))

    semesters = Semester.query.order_by(Semester.start_date.desc()).all()
    return render_template(
        'admin/semesters.html',
        semesters=semesters,
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

    hods = HOD.query.all()
    departments = Department.query.all()
    # Only lecturers not already promoted -- promoting flips User.role to
    # 'hod', so this filter naturally excludes anyone already promoted
    # without needing separate bookkeeping.
    promotable_lecturers = (
        Lecturer.query.join(User, Lecturer.user_id == User.id)
        .filter(User.role == 'lecturer')
        .order_by(Lecturer.full_name)
        .all()
    )
    return render_template(
        'admin/hods.html',
        hods=hods,
        departments=departments,
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
    departments = Department.query.all()
    courses = Course.query.all()
    return render_template(
        'admin/announcements.html',
        announcements=announcements,
        departments=departments,
        courses=courses,
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
def _all_course_attendance_reports():
    """
    System-wide per-course attendance percentage, shared by reports_page()
    and export_reports() so the on-screen table and the exported CSV can't
    drift apart. Same 'actual / (sessions * enrolled)' formula already used
    by the dashboard's department_attendance and lecturer.py's own
    _course_attendance_reports, just scoped to every course instead of one
    lecturer's or one department's.
    """
    courses = Course.query.order_by(Course.course_code).all()
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
            'lecturer_name': course.lecturer_summary or 'Unassigned',
            'department_name': course.department.name if course.department else 'Unassigned',
            'enrolled_count': enrolled_count,
            'session_count': session_count,
            'average_attendance': average_attendance,
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
            or action.endswith('.status') or action.endswith('.bulk_status'):
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


@admin_bp.route('/reports', methods=['GET'])
def reports_page():
    try:
        course_reports = _all_course_attendance_reports()
    except Exception:
        log_exception("Admin Reports Error")
        flash('An error occurred loading reports.', 'error')
        return redirect(url_for('admin.dashboard'))

    return render_template(
        'admin/reports.html',
        course_reports=course_reports,
        active_page='reports',
    )


@admin_bp.route('/reports/export', methods=['GET'])
def export_reports():
    try:
        course_reports = _all_course_attendance_reports()

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
                   f"Downloaded the attendance report ({len(course_reports)} courses)",
                   'report', None)
        db.session.commit()
    except Exception:
        db.session.rollback()
        log_exception("Admin Reports Export Error")
        flash('Failed to export attendance report.', 'error')
        return redirect(url_for('admin.reports_page'))

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=admin_attendance_report.csv'},
    )
