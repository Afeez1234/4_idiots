# from flask import Blueprint, flash, render_template, redirect, request, url_for
# import bcrypt
# from datetime import datetime, timezone
# from utils import login_required

# # Notice we imported 'Attendance' to make our dashboard query cleaner
# from models import db, User, Student, Lecturer, Session as SessionModel, Attendance

# admin_bp = Blueprint('admin', __name__)


# @admin_bp.route('/admin/dashboard')
# @login_required('admin')
# def dashboard():
#     # Direct ORM counts
#     lecturer_count = Lecturer.query.count()
#     student_count = Student.query.count()
#     active_sessions = SessionModel.query.filter_by(is_active=True).count()
    
#     # 1. Fetch today's date using our new future-proofed timezone method
#     today = datetime.now(timezone.utc).date()
    
#     # 2. Replaced the bulky db.execute block with a sleek ORM query
#     today_scans = Attendance.query.filter(
#         db.func.date(Attendance.time_in) == today
#     ).count()

#     sessions = SessionModel.query.filter_by(is_active=True).all()

#     return render_template(
#         'admin1/dashboard.html',
#         lecturer_count=lecturer_count,
#         student_count=student_count,
#         active_sessions=active_sessions,
#         today_scans=today_scans,
#         sessions=sessions,
#     )


# @admin_bp.route('/admin/create-lecturer', methods=['GET', 'POST'])
# @login_required('admin')
# def create_lecturer():
#     if request.method == 'GET':
#         return render_template('admin1/create-lecturer.html')

#     full_name = request.form.get('full_name')
#     staff_id = request.form.get('staff_id')

#     if not full_name or not staff_id:
#         flash('Full name and staff ID are required.', 'error')
#         return render_template('admin1/create-lecturer.html')

#     # Check if user already exists
#     existing_user = User.query.filter_by(username=staff_id).first()
#     if existing_user:
#         flash('A user with this staff ID already exists.', 'error')
#         return render_template('admin1/create-lecturer.html')

#     hashed_password = bcrypt.hashpw(
#         staff_id.encode('utf-8'),
#         bcrypt.gensalt()
#     ).decode('utf-8')

#     try:
#         # Create user account (Defaults to requires_password_change=True)
#         new_user = User(
#             username=staff_id,
#             password_hash=hashed_password,
#             role='lecturer',
#             is_active=True,
#             requires_password_change=True,
#         )
#         db.session.add(new_user)
#         db.session.flush()  # Gets the new user ID without committing

#         # Create lecturer profile
#         new_lecturer = Lecturer(
#             user_id=new_user.id,
#             full_name=full_name,
#             staff_id=staff_id,
#         )
#         db.session.add(new_lecturer)
#         db.session.commit()

#         flash('Lecturer created successfully.', 'success')
#         return redirect(url_for('admin.create_lecturer'))

#     except Exception as e:
#         db.session.rollback()
#         print(f"Error creating lecturer: {e}") # Added for console debugging
#         flash('Error occurred while creating lecturer.', 'error')
#         return redirect(url_for('admin.create_lecturer'))


# @admin_bp.route('/admin/create-student', methods=['GET', 'POST'])
# @login_required('admin')
# def create_student():
#     if request.method == 'GET':
#         return render_template('admin1/create-student.html')

#     full_name = request.form.get('full_name')
#     matric_number = request.form.get('matric_number')
#     department = request.form.get('department')
#     level = request.form.get('level')
#     rfid_uid = request.form.get('rfid_uid')

#     if not full_name or not matric_number or not department or not level or not rfid_uid:
#         flash('All fields are required.', 'error')
#         return render_template('admin1/create-student.html')

#     # Check if user already exists
#     existing_user = User.query.filter_by(username=matric_number).first()
#     if existing_user:
#         flash('A user with this matric number already exists.', 'error')
#         return render_template('admin1/create-student.html')

#     hashed_password = bcrypt.hashpw(
#         matric_number.encode('utf-8'),
#         bcrypt.gensalt()
#     ).decode('utf-8')

#     try:
#         # Create user account (Defaults to requires_password_change=True)
#         new_user = User(
#             username=matric_number,
#             password_hash=hashed_password,
#             role='student',
#             is_active=True,
#             requires_password_change=True,
#         )
#         db.session.add(new_user)
#         db.session.flush()

#         # Create student profile
#         new_student = Student(
#             user_id=new_user.id,
#             full_name=full_name,
#             matric_number=matric_number,
#             department=department,
#             level=level,
#             rfid_uid=rfid_uid,
#         )
#         db.session.add(new_student)
#         db.session.commit()

#         flash('Student created successfully.', 'success')
#         return redirect(url_for('admin.create_student'))

#     except Exception as e:
#         db.session.rollback()
#         print(f"Error creating student: {e}") # Added for console debugging
#         flash('Error occurred while creating student.', 'error')
#         return redirect(url_for('admin.create_student'))


# from flask import Blueprint, render_template, request, redirect, url_for, flash, session
# import bcrypt
# from datetime import datetime, timezone

# # Imported Attendance and SessionModel for clean ORM queries
# from models import db, User, Faculty, Department, Course, Lecturer, Student, Session as SessionModel, Attendance

# admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# # ==========================================
# # 1. MIDDLEWARE: BULLETPROOF SECURITY
# # ==========================================
# @admin_bp.before_request
# def require_admin():
#     """Protects EVERY route in this blueprint automatically."""
#     if 'user_id' not in session or session.get('role') != 'admin':
#         flash('Unauthorized access. Admin clearance required.', 'error')
#         return redirect(url_for('auth.login'))

# # ==========================================
# # 2. MAIN DASHBOARD (Your original clean logic)
# # ==========================================
# @admin_bp.route('/dashboard')
# def dashboard():
#     lecturer_count = Lecturer.query.count()
#     student_count = Student.query.count()
#     active_sessions = SessionModel.query.filter_by(is_active=True).count()
    
#     # Timezone-aware date check
#     today = datetime.now(timezone.utc).date()
#     today_scans = Attendance.query.filter(
#         db.func.date(Attendance.time_in) == today
#     ).count()

#     sessions = SessionModel.query.filter_by(is_active=True).all()

#     return render_template(
#         'admin/dashboard.html',
#         lecturer_count=lecturer_count,
#         student_count=student_count,
#         active_sessions=active_sessions,
#         today_scans=today_scans,
#         sessions=sessions
#     )

# # ==========================================
# # 3. ORGANIZATION MANAGEMENT
# # ==========================================
# @admin_bp.route('/organization', methods=['GET', 'POST'])
# def manage_organization():
#     if request.method == 'POST':
#         action = request.form.get('action')
        
#         if action == 'add_faculty':
#             faculty_name = request.form.get('faculty_name')
#             if faculty_name:
#                 # Explicit duplicate check
#                 if Faculty.query.filter_by(name=faculty_name).first():
#                     flash(f'Faculty "{faculty_name}" already exists.', 'error')
#                 else:
#                     new_faculty = Faculty(name=faculty_name)
#                     db.session.add(new_faculty)
#                     db.session.commit()
#                     flash(f'Faculty "{faculty_name}" created successfully.', 'success')

#         elif action == 'add_department':
#             dept_name = request.form.get('dept_name')
#             faculty_id = request.form.get('faculty_id')
#             if dept_name and faculty_id:
#                 if Department.query.filter_by(name=dept_name, faculty_id=faculty_id).first():
#                     flash(f'Department "{dept_name}" already exists in this faculty.', 'error')
#                 else:
#                     new_dept = Department(name=dept_name, faculty_id=faculty_id)
#                     db.session.add(new_dept)
#                     db.session.commit()
#                     flash(f'Department "{dept_name}" created successfully.', 'success')
                    
#         return redirect(url_for('admin.manage_organization'))

#     faculties = Faculty.query.all()
#     departments = Department.query.all()
#     return render_template('admin/organization.html', faculties=faculties, departments=departments)

# # ==========================================
# # 4. LECTURER MANAGEMENT (With your explicit checks)
# # ==========================================
# @admin_bp.route('/lecturers', methods=['GET', 'POST'])
# def manage_lecturers():
#     if request.method == 'POST':
#         full_name = request.form.get('full_name')
#         staff_id = request.form.get('staff_id')
#         department_id = request.form.get('department_id')

#         if not full_name or not staff_id or not department_id:
#             flash('All fields (Name, Staff ID, Department) are required.', 'error')
#             return redirect(url_for('admin.manage_lecturers'))

#         # YOUR EXPLICIT DUPLICATE CHECK
#         existing_user = User.query.filter_by(username=staff_id).first()
#         if existing_user:
#             flash(f'A user with Staff ID {staff_id} already exists.', 'error')
#             return redirect(url_for('admin.manage_lecturers'))

#         hashed_password = bcrypt.hashpw(staff_id.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
#         try:
#             new_user = User(
#                 username=staff_id, 
#                 password_hash=hashed_password, 
#                 role='lecturer',
#                 requires_password_change=True # Forced security
#             )
#             db.session.add(new_user)
#             db.session.flush() 
            
#             new_lecturer = Lecturer(
#                 full_name=full_name,
#                 staff_id=staff_id,
#                 department_id=department_id,
#                 user_id=new_user.id
#             )
#             db.session.add(new_lecturer)
#             db.session.commit()
            
#             flash(f'Lecturer {full_name} added successfully!', 'success')
#         except Exception as e:
#             db.session.rollback()
#             print(f"Error creating lecturer: {e}")
#             flash('Database error occurred while adding lecturer.', 'error')
            
#         return redirect(url_for('admin.manage_lecturers'))

#     lecturers = Lecturer.query.all()
#     departments = Department.query.all()
#     return render_template('admin/lecturers.html', lecturers=lecturers, departments=departments)

# # ==========================================
# # 5. STUDENT MANAGEMENT (With your explicit checks)
# # ==========================================
# @admin_bp.route('/students', methods=['GET', 'POST'])
# def manage_students():
#     if request.method == 'POST':
#         full_name = request.form.get('full_name')
#         matric_number = request.form.get('matric_number')
#         department_id = request.form.get('department_id')
#         level = request.form.get('level')
#         rfid_uid = request.form.get('rfid_uid')

#         if not full_name or not matric_number or not department_id or not level or not rfid_uid:
#             flash('All fields are required.', 'error')
#             return redirect(url_for('admin.manage_students'))

#         # YOUR EXPLICIT DUPLICATE CHECK
#         existing_user = User.query.filter_by(username=matric_number).first()
#         if existing_user:
#             flash(f'A user with Matric Number {matric_number} already exists.', 'error')
#             return redirect(url_for('admin.manage_students'))

#         hashed_password = bcrypt.hashpw(matric_number.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
#         try:
#             new_user = User(
#                 username=matric_number, 
#                 password_hash=hashed_password, 
#                 role='student',
#                 requires_password_change=True # Forced security
#             )
#             db.session.add(new_user)
#             db.session.flush() 
            
#             new_student = Student(
#                 full_name=full_name,
#                 matric_number=matric_number,
#                 department_id=department_id,
#                 level=level,
#                 rfid_uid =rfid_uid,
#                 user_id=new_user.id
#             )
#             db.session.add(new_student)
#             db.session.commit()
            
#             flash(f'Student {full_name} added successfully!', 'success')
#         except Exception as e:
#             db.session.rollback()
#             print(f"Error creating student: {e}")
#             flash('Database error occurred while adding student.', 'error')
            
#         return redirect(url_for('admin.manage_students'))

#     students = Student.query.all()
#     departments = Department.query.all()
#     return render_template('admin/students.html', students=students, departments=departments)


import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
import bcrypt
from models import db, Faculty, Department, User, Student, Lecturer, Course, Enrollment
from extensions import log_exception, logger

# Define the Blueprint for the Admin portal
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    """
    Custom decorator to protect administrative routes.
    Verifies that the browser session carries a valid user ID and the 'admin' role.
    """
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            flash('Session expired. Please log in.', 'error')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'admin':
            flash('Access Denied. Administrative privileges required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard():
    """
    Renders the administrative dashboard showing total system metrics
    and active enrollment statistics.
    """
    try:
        # Pull high-level counts cleanly using SQLAlchemy ORM queries
        total_students = Student.query.count()
        total_lecturers = Lecturer.query.count()
        total_courses = Course.query.count()
        total_departments = Department.query.count()
        total_faculties = Faculty.query.count()

        # Retrieve all faculties for the management views
        faculties = Faculty.query.all()
        departments = Department.query.all()
        lecturers_list = Lecturer.query.all()
        
        # Pull recent device unbind requests or general student roster for management
        students = Student.query.order_by(Student.id.desc()).limit(10).all()

        return render_template(
            'admin/dashboard.html',
            total_students=total_students,
            total_lecturers=total_lecturers,
            total_courses=total_courses,
            total_departments=total_departments,
            total_faculties=total_faculties,
            lecturers_list=lecturers_list,
            faculties=faculties,
            departments=departments,
            students=students
        )
    except Exception:
        log_exception("Admin Dashboard Error")
        flash("An error occurred while loading administrative dashboard metrics.", "error")
        return redirect(url_for('auth.login'))


@admin_bp.route('/faculties/create', methods=['POST'])
@admin_required
def create_faculty():
    """
    Creates a new Faculty entity. Crucial for Phase 4 scale expansions.
    """
    name = request.form.get('name')
    if not name or not name.strip():
        flash('Faculty name is required.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        faculty = Faculty(name=name.strip())
        db.session.add(faculty)
        db.session.commit()
        flash(f"Faculty '{name}' added successfully.", 'success')
    except Exception:
        db.session.rollback()
        flash('Faculty name must be unique.', 'error')
        log_exception("Faculty Create Error")
        
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/departments/create', methods=['POST'])
@admin_required
def create_department():
    """
    Creates a new Department linked to an existing Faculty.
    """
    name = request.form.get('name')
    faculty_id = request.form.get('faculty_id')

    if not name or not faculty_id:
        flash('All fields are required to create a department.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        department = Department(name=name.strip(), faculty_id=int(faculty_id))
        db.session.add(department)
        db.session.commit()
        flash(f"Department '{name}' added successfully.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to create department. Verify connections.', 'error')
        log_exception("Department Create Error")
        
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/students/create', methods=['POST'])
@admin_required
def create_student():
    """
    Registers a single student, creating both a secure User credential profile
    and a linking Student profile.
    """
    full_name = request.form.get('full_name')
    matric_number = request.form.get('matric_number')
    level = request.form.get('level')
    department_id = request.form.get('department_id')
    rfid_uid = request.form.get('rfid_uid') or None

    if not all([full_name, matric_number, level, department_id]):
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        # Check if user already exists
        existing_user = User.query.filter_by(username=matric_number.strip()).first()
        if existing_user:
            flash('Matric Number is already registered as a user username.', 'error')
            return redirect(url_for('admin.dashboard'))

        # 1. Create secure default login credentials (hashed via bcrypt)
        # Defaults to SUAAMS2026, forcing a reset on first login!
        default_pwd = matric_number
        hashed_password = bcrypt.hashpw(default_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        new_user = User(
            username=matric_number.strip(),
            password_hash=hashed_password,
            role='student',
            is_active=True,
            requires_password_change=True # Security protocol enforce
        )
        db.session.add(new_user)
        db.session.flush() # Secure user.id before commit to link student

        # 2. Link Student Profile
        new_student = Student(
            full_name=full_name.strip(),
            matric_number=matric_number.strip(),
            level=int(level),
            rfid_uid=rfid_uid,
            department_id=int(department_id),
            user_id=new_user.id
        )
        db.session.add(new_student)
        db.session.commit()
        
        flash(f"Student profile created successfully for {full_name}.", 'success')
    except Exception:
        db.session.rollback()
        flash('Database error occurred. Matric Number or RFID UID might already exist.', 'error')
        log_exception("Student Single Creation Error")

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/students/bulk-enroll', methods=['POST'])
@admin_required
def bulk_enroll_students():
    """
    Processes university-scale bulk enrollments from an uploaded CSV file.
    Expects columns: matric_number, full_name, level, department_name, rfid_uid
    """
    if 'file' not in request.files:
        flash('No file selected.', 'error')
        return redirect(url_for('admin.dashboard'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected.', 'error')
        return redirect(url_for('admin.dashboard'))

    if not file.filename.endswith('.csv'):
        flash('Invalid file format. Please upload a structured .csv file.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        # Read the file stream cleanly
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_reader = csv.DictReader(stream)

        # Basic verification of key columns
        required_cols = {'matric_number', 'full_name', 'level', 'department_name'}
        if not required_cols.issubset(set(csv_reader.fieldnames or [])):
            flash('CSV missing required headers: matric_number, full_name, level, department_name', 'error')
            return redirect(url_for('admin.dashboard'))

        success_count = 0
        error_count = 0
        skipped_records = []

        # Define high-security default credentials
        default_pwd = matric_no
        hashed_password = bcrypt.hashpw(default_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        for row in csv_reader:
            matric_no = row['matric_number'].strip()
            name = row['full_name'].strip()
            level_str = row['level'].strip()
            dept_name = row['department_name'].strip()
            rfid = row.get('rfid_uid', '').strip() or None

            # Skip incomplete data rows
            if not matric_no or not name or not level_str or not dept_name:
                error_count += 1
                skipped_records.append(f"{name or 'Unknown'} (Incomplete Row fields)")
                continue

            # Check if user already registered
            existing_user = User.query.filter_by(username=matric_no).first()
            if existing_user:
                error_count += 1
                skipped_records.append(f"{name} (Matric number already registered)")
                continue

            # Lookup department by case-insensitive name
            department = Department.query.filter(
                db.func.lower(Department.name) == dept_name.lower()
            ).first()

            if not department:
                error_count += 1
                skipped_records.append(f"{name} (Department '{dept_name}' not found)")
                continue

            try:
                # 1. Register User Profile
                user = User(
                    username=matric_no,
                    password_hash=hashed_password,
                    role='student',
                    is_active=True,
                    requires_password_change=True
                )
                db.session.add(user)
                db.session.flush() # Sync ID mapping

                # 2. Register Student Profile
                student = Student(
                    full_name=name,
                    matric_number=matric_no,
                    level=int(level_str),
                    rfid_uid=rfid,
                    department_id=department.id,
                    user_id=user.id
                )
                db.session.add(student)
                success_count += 1
            except Exception as row_error:
                # NOTE: skipped_records itself (which does include the raw
                # exception text) is never flashed or rendered to the admin
                # -- only the count is shown in the UI, the full list only
                # ever reaches logs below. Keeping that content as-is since
                # it's genuinely useful for an admin diagnosing a bad CSV
                # row; only the print() -> logger swap changes here. Still
                # need `as row_error` bound here (unlike the other sites in
                # this file) since skipped_records.append below uses it.
                db.session.rollback()
                error_count += 1
                skipped_records.append(f"{name} (System exception: {row_error})")
                log_exception("Row Enrollment Error")

        # Finalize successful records
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

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/lecturers/create', methods=['POST'])
@admin_required
def create_lecturer():
    """
    Creates a new Lecturer account, generating secure login credentials
    and linking the lecturer profile to their structural Department.
    """
    full_name = request.form.get('full_name')
    staff_id = request.form.get('staff_id')
    department_id = request.form.get('department_id')

    if not all([full_name, staff_id, department_id]):
        flash('All fields are required to register a lecturer.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        # Prevent credential duplication
        existing_user = User.query.filter_by(username=staff_id.strip()).first()
        if existing_user:
            flash('Staff ID is already registered as an active username.', 'error')
            return redirect(url_for('admin.dashboard'))

        # Create user profile (hashed secure default)
        default_pwd = staff_id
        hashed_password = bcrypt.hashpw(default_pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

        user = User(
            username=staff_id.strip(),
            password_hash=hashed_password,
            role='lecturer',
            is_active=True,
            requires_password_change=True
        )
        db.session.add(user)
        db.session.flush()

        # Link Lecturer profile
        lecturer = Lecturer(
            full_name=full_name.strip(),
            staff_id=staff_id.strip(),
            department_id=int(department_id),
            user_id=user.id
        )
        db.session.add(lecturer)
        db.session.commit()
        
        flash(f"Lecturer account created successfully for {full_name}.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to create lecturer account. Verify values.', 'error')
        log_exception("Lecturer Account Error")

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/courses/create', methods=['POST'])
@admin_required
def create_course():
    """
    Creates a new Academic Course and maps it immediately to an active Department
    and an assigned Lecturer.
    """
    title = request.form.get('title')
    code = request.form.get('code')
    department_id = request.form.get('department_id')
    lecturer_id = request.form.get('lecturer_id')

    if not all([title, code, department_id, lecturer_id]):
        flash('All academic course parameters must be specified.', 'error')
        return redirect(url_for('admin.dashboard'))

    try:
        course = Course(
            title=title.strip(),
            code=code.strip().upper(),
            department_id=int(department_id),
            lecturer_id=int(lecturer_id)
        )
        db.session.add(course)
        db.session.commit()
        flash(f"Course '{code}' assigned and registered successfully.", 'success')
    except Exception:
        db.session.rollback()
        flash('Course Code must be unique.', 'error')
        log_exception("Course Registration Error")

    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/students/unbind/<int:student_id>', methods=['POST'])
@admin_required
def reset_student_binding(student_id):
    """
    Resets the device binding of a student (Phase 5, feature 26).
    Enables them to log in cleanly on a new physical device upon presenting valid identification.
    """
    try:
        student = Student.query.get_or_404(student_id)
        student.device_id = None
        # SECURITY FIX: unbinding a device used to only clear device_id,
        # which blocks a *future* login from the old device but does
        # nothing to a refresh token that device already holds -- it could
        # keep silently refreshing itself for up to JWT_REFRESH_TOKEN_EXPIRES
        # (14 days) after being "unbound". Clearing current_refresh_jti here
        # makes the old device's next /api/v1/auth/refresh call fail
        # immediately (see mobile_refresh in api/auth.py), bounding its
        # remaining access to whatever's left of its current short-lived
        # access token (<=30 min).
        if student.user:
            student.user.current_refresh_jti = None
        db.session.commit()
        flash(f"Successfully cleared hardware device binding for {student.full_name}.", 'success')
    except Exception:
        db.session.rollback()
        flash('Failed to unbind device. System database exception.', 'error')
        log_exception("Device Unbind Critical Exception")

    return redirect(url_for('admin.dashboard'))