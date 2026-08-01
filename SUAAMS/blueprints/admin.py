import csv
import io
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import bcrypt
from models import (
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, HOD, Semester, Announcement,
)
from extensions import log_exception, logger

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
def courses_page():
    if request.method == 'POST':
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
    return render_template(
        'admin/courses.html',
        courses=courses,
        departments=departments,
        lecturers=lecturers,
        semesters=semesters,
        active_page='courses',
    )


# ==========================================
# SEMESTERS
# ==========================================
@admin_bp.route('/semesters', methods=['GET', 'POST'])
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
def hods_page():
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        staff_id = request.form.get('staff_id')
        department_id = request.form.get('department_id')

        if not all([full_name, staff_id, department_id]):
            flash('All fields are required to assign an HOD.', 'error')
            return redirect(url_for('admin.hods_page'))

        try:
            existing_user = User.query.filter_by(username=staff_id.strip()).first()
            if existing_user:
                flash('Staff ID is already registered as an active username.', 'error')
                return redirect(url_for('admin.hods_page'))

            # GAP (also flagged in hods.html's own comment): nothing stops
            # a department getting a second HOD at the schema level --
            # HOD.department_id has no unique constraint in models.py.
            # Rejecting a duplicate assignment here since the schema
            # doesn't enforce it.
            existing_hod = HOD.query.filter_by(department_id=int(department_id)).first()
            if existing_hod:
                flash(f"{existing_hod.department.name} already has an HOD assigned ({existing_hod.full_name}).", 'error')
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
    return render_template(
        'admin/hods.html',
        hods=hods,
        departments=departments,
        active_page='hods',
    )


# ==========================================
# ANNOUNCEMENTS
# ==========================================
@admin_bp.route('/announcements', methods=['GET', 'POST'])
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
