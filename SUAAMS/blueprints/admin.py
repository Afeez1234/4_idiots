import csv
import io
from collections import defaultdict
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response
import bcrypt
from models import (
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, HOD, Semester, Announcement, Timetable,
)
from extensions import log_exception, logger, limiter
from utils import resolve_current_course, session_status_for_course, students_for_announcement
from push_notifications import send_push_notification

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
                    db.session.add(Faculty(name=name.strip()))
                    db.session.commit()
                    flash(f"Faculty '{name}' added successfully.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Faculty name must be unique.', 'error')
                    log_exception("Faculty Create Error")

        elif action == 'add_department':
            name = request.form.get('name')
            faculty_id = request.form.get('faculty_id')
            if not name or not faculty_id:
                flash('All fields are required to create a department.', 'error')
            else:
                try:
                    db.session.add(Department(name=name.strip(), faculty_id=int(faculty_id)))
                    db.session.commit()
                    flash(f"Department '{name}' added successfully.", 'success')
                except Exception:
                    db.session.rollback()
                    flash('Failed to create department. Verify connections.', 'error')
                    log_exception("Department Create Error")

        return redirect(url_for('admin.organization_page'))

    faculties = Faculty.query.all()
    departments = Department.query.all()
    return render_template(
        'admin/organization.html',
        faculties=faculties,
        departments=departments,
        active_page='organization',
    )


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
        db.session.delete(faculty)
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
        db.session.delete(department)
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
        active_page='lecturers',
    )


# ==========================================
# STUDENTS
# ==========================================
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

            # BUG FIX: was `level=int(level)` -- Student.level is
            # deliberately db.String(20), not Integer, specifically so
            # values like "400L" don't crash this insert (see models.py).
            # Storing the raw string as submitted.
            new_student = Student(
                full_name=full_name.strip(),
                matric_number=matric_number.strip(),
                level=level.strip(),
                rfid_uid=rfid_uid,
                department_id=int(department_id),
                user_id=new_user.id,
            )
            db.session.add(new_student)
            db.session.commit()
            flash(f"Student profile created successfully for {full_name}.", 'success')
        except Exception:
            db.session.rollback()
            flash('Database error occurred. Matric Number or RFID UID might already exist.', 'error')
            log_exception("Student Single Creation Error")

        return redirect(url_for('admin.students_page'))

    students = Student.query.order_by(Student.id.desc()).all()
    departments = Department.query.all()
    return render_template(
        'admin/students.html',
        students=students,
        departments=departments,
        active_page='students',
    )


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

        success_count = 0
        error_count = 0
        skipped_records = []

        for row in csv_reader:
            matric_no = row['matric_number'].strip()
            name = row['full_name'].strip()
            level_str = row['level'].strip()
            dept_name = row['department_name'].strip()
            rfid = row.get('rfid_uid', '').strip() or None

            if not matric_no or not name or not level_str or not dept_name:
                error_count += 1
                skipped_records.append(f"{name or 'Unknown'} (Incomplete Row fields)")
                continue

            existing_user = User.query.filter_by(username=matric_no).first()
            if existing_user:
                error_count += 1
                skipped_records.append(f"{name} (Matric number already registered)")
                continue

            department = Department.query.filter(
                db.func.lower(Department.name) == dept_name.lower()
            ).first()

            if not department:
                error_count += 1
                skipped_records.append(f"{name} (Department '{dept_name}' not found)")
                continue

            try:
                # BUG FIX: default password is this row's OWN matric number
                # -- previously hashed once, outside the loop, from a
                # `matric_no` that didn't exist yet at that point in the
                # file (NameError), which meant every bulk-enroll POST
                # crashed immediately before reading a single CSV row.
                default_pwd = matric_no
                hashed_password = bcrypt.hashpw(default_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                user = User(
                    username=matric_no,
                    password_hash=hashed_password,
                    role='student',
                    is_active=True,
                    requires_password_change=True,
                )
                db.session.add(user)
                db.session.flush()

                # BUG FIX: was `level=int(level_str)` -- same String(20)
                # reasoning as students_page()'s create form above.
                student = Student(
                    full_name=name,
                    matric_number=matric_no,
                    level=level_str,
                    rfid_uid=rfid,
                    department_id=department.id,
                    user_id=user.id,
                )
                db.session.add(student)
                success_count += 1
            except Exception as row_error:
                db.session.rollback()
                error_count += 1
                skipped_records.append(f"{name} (System exception: {row_error})")
                log_exception("Row Enrollment Error")

        db.session.commit()

        if success_count > 0:
            flash(f"Successfully enrolled {success_count} students in bulk. Default credentials set.", 'success')
        if error_count > 0:
            flash(f"Skipped {error_count} records due to validation issues. View logs.", 'warning')
            logger.warning(f"Skipped rows: {skipped_records}")

    except Exception:
        db.session.rollback()
        flash('Failed to process bulk CSV enrollment. Check data formatting.', 'error')
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

    return redirect(url_for('admin.students_page'))


# ==========================================
# COURSES
# ==========================================
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
            student_id = request.form.get('student_id')
            course_id = request.form.get('course_id')

            if not student_id or not course_id:
                flash('Select both a student and a course to enroll.', 'error')
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
                    db.session.commit()
                    flash('Student enrolled successfully.', 'success')
            except Exception:
                db.session.rollback()
                flash('Failed to enroll student.', 'error')
                log_exception("Enrollment Create Error")

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
            db.session.commit()
            flash(f"Course '{code}' assigned and registered successfully.", 'success')
        except Exception:
            db.session.rollback()
            flash('Course Code must be unique within its semester.', 'error')
            log_exception("Course Registration Error")

        return redirect(url_for('admin.courses_page'))

    courses = Course.query.all()
    departments = Department.query.all()
    lecturers = Lecturer.query.all()
    semesters = Semester.query.all()
    students = Student.query.all()
    return render_template(
        'admin/courses.html',
        courses=courses,
        departments=departments,
        lecturers=lecturers,
        semesters=semesters,
        students=students,
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

    today = datetime.now()
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

    for other in query.all():
        if room and other.room and other.room.strip().lower() == room.strip().lower():
            other_code = other.course.course_code if other.course else 'another course'
            return f'Room {room} is already booked by {other_code} at that time.'
        if course and other.course and other.course.lecturer_id == course.lecturer_id:
            lecturer_name = course.lecturer.full_name if course.lecturer else 'This lecturer'
            return f'{lecturer_name} already has {other.course.course_code} scheduled at an overlapping time.'
    return None


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
                db.session.delete(entry)
                db.session.commit()
                flash('Timetable slot removed.', 'success')
            except Exception:
                db.session.rollback()
                # Session.timetable_id deliberately isn't cascaded (models.py) --
                # a FK-RESTRICT failure here means real session history already
                # exists under this slot.
                flash('Could not delete: sessions already exist for this slot.', 'error')
                log_exception("Timetable Delete Error")
            return redirect(url_for('admin.timetable_page'))

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
            return redirect(url_for('admin.timetable_page'))

        try:
            semester_id_int = int(semester_id)
            day_of_week_int = int(day_of_week)
            start_time = datetime.strptime(start_time_raw, '%H:%M').time()
            end_time = datetime.strptime(end_time_raw, '%H:%M').time()
            course = Course.query.get(int(course_id))
        except (ValueError, TypeError):
            flash('Invalid timetable slot data.', 'error')
            return redirect(url_for('admin.timetable_page'))

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
            return redirect(url_for('admin.timetable_page'))

        error = _validate_timetable_slot(
            course, semester_id_int, day_of_week_int, start_time, end_time, room,
            exclude_id=int(timetable_id) if timetable_id else None,
        )
        if error:
            flash(error, 'error')
            return redirect(url_for('admin.timetable_page'))

        try:
            if action == 'update' and timetable_id:
                entry = Timetable.query.get_or_404(int(timetable_id))
                entry.course_id = course.id
                entry.semester_id = semester_id_int
                entry.day_of_week = day_of_week_int
                entry.start_time = start_time
                entry.end_time = end_time
                entry.room = room.strip() if room else None
                entry.type = slot_type
                db.session.commit()
                flash('Timetable slot updated.', 'success')
            else:
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
                db.session.commit()
                flash('Timetable slot added.', 'success')
        except Exception:
            db.session.rollback()
            flash('Failed to save timetable slot.', 'error')
            log_exception("Timetable Save Error")

        return redirect(url_for('admin.timetable_page'))

    timetable_entries = Timetable.query.order_by(
        Timetable.day_of_week.asc(), Timetable.start_time.asc()
    ).all()
    courses = Course.query.all()
    semesters = Semester.query.all()
    return render_template(
        'admin/timetable.html',
        timetable_entries=timetable_entries,
        courses=courses,
        semesters=semesters,
        weekday_names=WEEKDAY_NAMES,
        grid=_build_timetable_grid(timetable_entries),
        current_course=resolve_current_course(),
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
    return jsonify(resolve_current_course())


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
            db.session.commit()

            # Best-effort push to every student this announcement reaches --
            # same fire-after-commit, never-fail-the-request pattern as
            # api/student.py's attendance-confirmation push. A student who
            # never granted notification permission (or was offline) still
            # sees it in-app, since send_push_notification always persists
            # the Notification row before attempting FCM delivery.
            preview = announcement.body if len(announcement.body) <= 120 else announcement.body[:117] + '...'
            for student in students_for_announcement(announcement):
                send_push_notification(
                    student.user, 'announcement', announcement.title, preview,
                    data={'announcement_id': announcement.id},
                )

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
            'lecturer_name': course.lecturer.full_name if course.lecturer else 'Unassigned',
            'department_name': course.department.name if course.department else 'Unassigned',
            'enrolled_count': enrolled_count,
            'session_count': session_count,
            'average_attendance': average_attendance,
        })
    return rows


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
    except Exception:
        log_exception("Admin Reports Export Error")
        flash('Failed to export attendance report.', 'error')
        return redirect(url_for('admin.reports_page'))

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=admin_attendance_report.csv'},
    )
