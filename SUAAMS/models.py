from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timezone

db = SQLAlchemy()

# ==========================================
# 1. ORGANIZATIONAL STRUCTURE
# ==========================================
class Faculty(db.Model):
    __tablename__ = 'faculties'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)

    departments = db.relationship('Department', backref='faculty', lazy=True, cascade="all, delete-orphan")


class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'), nullable=False)

    students = db.relationship('Student', backref='department', lazy=True, cascade="all, delete-orphan")
    lecturers = db.relationship('Lecturer', backref='department', lazy=True, cascade="all, delete-orphan")
    # NEW: HOD profiles cascade the same way Student/Lecturer profiles do --
    # deleting a department removes the HOD record tied to it (not the
    # underlying User account, which cascades separately from User itself).
    hods = db.relationship('HOD', backref='department', lazy=True, cascade="all, delete-orphan")
    courses = db.relationship('Course', backref='department', lazy=True, cascade="all, delete-orphan")


class Semester(db.Model):
    # NEW TABLE. is_active is a plain boolean, not a DB-level "only one
    # true" constraint -- MySQL doesn't support partial/filtered unique
    # indexes the way Postgres does, so "only one active at a time" has to
    # be enforced at the application layer (e.g. the endpoint that
    # activates a semester must deactivate all others in the same
    # transaction). Flagging this explicitly since it's a real invariant
    # that nothing in this file enforces on its own.
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)  # e.g. "2025/2026 First Semester"
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=False, nullable=False)

    # DELIBERATELY NOT cascading here (no cascade="all, delete-orphan"),
    # unlike Faculty->Department or Department->Course above. A semester is
    # a cross-cutting time period referenced BY many courses/timetable
    # entries/results, not a strict owner of them the way a Department owns
    # its Courses. Cascading would mean deleting one old semester record
    # silently wipes every course/attendance/results history tied to it --
    # wrong for an academic records system, where that history should
    # persist. Net effect: the DB will refuse to delete a Semester while
    # courses/timetable/results still reference it (FK RESTRICT), which is
    # the safer default. If you actually want semester archival/deletion,
    # that needs an explicit, deliberate app-level flow -- not a cascade.
    courses = db.relationship('Course', backref='semester', lazy=True)
    timetable_entries = db.relationship('Timetable', backref='semester', lazy=True)
    results = db.relationship('Result', backref='semester', lazy=True)


# ==========================================
# 2. AUTHENTICATION & ROLES
# ==========================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # NEW: 'hod' added to the role enum.
    role = db.Column(db.Enum('admin', 'hod', 'lecturer', 'student'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    requires_password_change = db.Column(db.Boolean, default=True)

    # Tracks the JTI (JWT ID) of the current valid refresh token for this
    # user. Enables rotation (a refresh call must present the JTI stored
    # here, and immediately overwrites it with the new one) and revocation
    # (nulling this -- e.g. from reset_student_binding on device unbind --
    # makes the next refresh attempt fail, without needing a full token
    # blocklist). Deliberately a single value, not a list/table: mirrors
    # Student.device_id's existing one-device-at-a-time design rather than
    # supporting multiple concurrent sessions per account.
    current_refresh_jti = db.Column(db.String(64), nullable=True)

    # Clean cascading links to profiles -- deleting a User account removes
    # whichever role-profile row belongs to it.
    student = db.relationship('Student', backref='user', uselist=False, cascade="all, delete-orphan")
    lecturer = db.relationship('Lecturer', backref='user', uselist=False, cascade="all, delete-orphan")
    hod = db.relationship('HOD', backref='user', uselist=False, cascade="all, delete-orphan")


# ==========================================
# 3. CORE PROFILES
# ==========================================
class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    matric_number = db.Column(db.String(50), unique=True, nullable=False)
    # KEPT as String(20), not converted to Integer -- per explicit
    # instruction, to avoid a migration that tries to cast existing level
    # values to int and fails if any aren't cleanly numeric (e.g. "400L"
    # style values).
    level = db.Column(db.String(20), nullable=False)
    rfid_uid = db.Column(db.String(50), unique=True, nullable=True)
    device_id = db.Column(db.String(255), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # NEW. server_default (not just the Python-side `default=`) so the
    # column has a DB-level fallback -- required for the migration to
    # backfill this NOT NULL column on existing student rows, and also
    # covers any insert that bypasses the ORM's default (e.g. raw
    # server-side tooling).
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.now(),
        nullable=False,
    )

    # Direct many-to-many relationship helper to keep student.courses loops
    # fully backward-compatible. viewonly=True (on both this side and the
    # 'enrolled_students' backref) because the real source of truth for
    # writes is the Enrollment model's own student/course relationships
    # below -- without viewonly, SQLAlchemy sees two different relationship
    # configs both claiming to manage enrollments.student_id/course_id and
    # warns about the overlap (SAWarning at configure_mappers() time).
    # Nothing ever writes through student.courses.append(...) or
    # course.enrolled_students.append(...); enrollments are always created
    # via Enrollment(student_id=.., course_id=..) directly, so this is a
    # pure read convenience.
    courses = db.relationship(
        'Course',
        secondary='enrollments',
        viewonly=True,
        backref=db.backref('enrolled_students', lazy='dynamic', viewonly=True),
    )

    # Cascade deletes to cleanly wipe logs if a student is removed from the system
    enrollments = db.relationship('Enrollment', backref='student', lazy=True, cascade="all, delete-orphan")
    attendance = db.relationship('Attendance', backref='student', lazy=True, cascade="all, delete-orphan")
    # NEW
    results = db.relationship('Result', backref='student', lazy=True, cascade="all, delete-orphan")


class Lecturer(db.Model):
    __tablename__ = 'lecturers'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # DELIBERATELY not cascading: a course shouldn't vanish just because
    # the lecturer account teaching it gets deleted (it has its own
    # enrollment/attendance/results history). Same as the original schema.
    courses = db.relationship('Course', backref='lecturer', lazy=True)


class HOD(db.Model):
    # NEW TABLE (Head of Department). Structurally identical to Lecturer --
    # its own profile row linked 1:1 to a User account, scoped to a
    # Department. Nothing elsewhere in this file grants HODs different
    # permissions; that's an application-layer (route/endpoint) concern
    # exactly like how 'admin' vs 'lecturer' vs 'student' is already
    # enforced via @login_required(role)/JWT role claims, not via anything
    # in the schema itself.
    __tablename__ = 'hods'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)


# ==========================================
# 4. ACADEMIC STRUCTURE
# ==========================================
class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    # RENAMED from title/code -> course_title/course_code per the new
    # schema. All call sites that read course.title/course.code
    # (blueprints/admin.py, blueprints/student.py, api/lecturer.py,
    # api/student.py) and the one Jinja template reference
    # (templates/lecturer/course_workspace.html) have been updated to
    # match. JSON response key names were left unchanged (e.g. "title":
    # course.course_title) so no Flutter-side changes were needed.
    course_title = db.Column(db.String(150), nullable=False)
    course_code = db.Column(db.String(20), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'), nullable=False)
    # MADE NULLABLE per explicit instruction, to avoid `flask db migrate`
    # generating an ALTER that requires a value for every existing row.
    # department_id wasn't a new column (it was already NOT NULL in the
    # original schema) -- relaxing it here too, not just the two genuinely
    # new columns below, since that's what was asked. semester_id and
    # credit_units ARE new columns, so this matters even more for them:
    # without nullable=True, adding them to a table with existing rows
    # would fail outright (no value to backfill with).
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=True)
    credit_units = db.Column(db.Integer, nullable=True)

    # DESIGN DECISION: course_code is no longer globally unique (the old
    # schema had unique=True on this column). With semester_id now on
    # Course, the same course code presumably recurs every semester (e.g.
    # "CPE401" offered every year) -- a global unique constraint would make
    # that impossible. Added a composite unique constraint on
    # (course_code, semester_id) instead: unique *within* a semester, but
    # free to repeat across semesters. Flagging this since the spec didn't
    # explicitly state which behavior was wanted.
    __table_args__ = (
        db.UniqueConstraint('course_code', 'semester_id', name='uq_course_code_semester'),
    )

    # Cascades to clean up structural timetable entries, sessions, and academic enrollments
    sessions = db.relationship('Session', backref='course', lazy=True, cascade="all, delete-orphan")
    timetable = db.relationship('Timetable', backref='course', lazy=True, cascade="all, delete-orphan")
    enrollments = db.relationship('Enrollment', backref='course', lazy=True, cascade="all, delete-orphan")
    # NEW
    results = db.relationship('Result', backref='course', lazy=True, cascade="all, delete-orphan")
    announcements = db.relationship('Announcement', backref='course', lazy=True, cascade="all, delete-orphan")


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)

    # NEW: wasn't enforced in the DB before (a student could accidentally
    # be enrolled in the same course twice). Now a real constraint.
    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', name='uq_enrollment_student_course'),
    )


# ==========================================
# 5. TIMETABLE & SESSIONS
# ==========================================
class Timetable(db.Model):
    __tablename__ = 'timetable'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    # NEW
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0 = Monday, 6 = Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(50), nullable=True)
    # NEW: 'scheduled' (regular recurring weekly slot) vs 'fixed' (a
    # one-off/pinned slot that shouldn't be touched by future timetable
    # regeneration) -- implemented faithfully per the spec; the actual
    # scheduling-engine behavior difference between the two is an
    # application-layer concern, not something this column enforces.
    type = db.Column(db.Enum('scheduled', 'fixed'), nullable=False, default='scheduled')
    # NEW: who created this timetable entry (an HOD or admin, presumably).
    # NOT NULL -- an audit field like this should always have a known
    # author at creation time. No cascade from User (deleting the creator's
    # account shouldn't retroactively delete the timetable entries they
    # made; the FK just protects against orphaning this audit trail, same
    # reasoning as Announcement.sender_id/Result.entered_by below).
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Sessions can optionally trace back to the timetable slot they were
    # generated from (see Session.timetable_id below) -- no cascade here
    # either, deleting a timetable entry shouldn't retroactively delete
    # historical sessions/attendance that already happened under it.
    sessions = db.relationship('Session', backref='timetable', lazy=True)


class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    # NEW, nullable: a session can be created ad hoc (no matching timetable
    # slot) or generated from a recurring Timetable entry.
    timetable_id = db.Column(db.Integer, db.ForeignKey('timetable.id'), nullable=True)
    # RE-ADDED: actual start/stop timestamps, distinct from planned_start/
    # planned_end below (the *planned* schedule). Both nullable: start_time
    # gets set when a lecturer actually starts the session, stop_time when
    # they end it -- a freshly created session has neither yet.
    start_time = db.Column(db.Time, nullable=True)
    stop_time = db.Column(db.Time, nullable=True)
    session_date = db.Column(db.Date, default=date.today)
    is_active = db.Column(db.Boolean, default=False)
    planned_start = db.Column(db.Time, nullable=True)
    planned_end = db.Column(db.Time, nullable=True)
    # NEW
    room = db.Column(db.String(50), nullable=True)

    attendance_records = db.relationship('Attendance', backref='session', lazy=True, cascade="all, delete-orphan")


# ==========================================
# 6. ATTENDANCE TRACKING
# ==========================================
class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    time_in = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    # NEW: 'late' added alongside the existing present/absent/excused.
    status = db.Column(db.Enum('present', 'late', 'absent', 'excused'), default='present')

    # NEW: wasn't enforced before (a student could be marked twice for the
    # same session). Matches the existing attendance_already_recorded()
    # check in app.py/api/student.py, now backed by a real constraint.
    __table_args__ = (
        db.UniqueConstraint('student_id', 'session_id', name='uq_attendance_student_session'),
    )


# ==========================================
# 7. COMMUNICATION
# ==========================================
class Announcement(db.Model):
    # NEW TABLE.
    __tablename__ = 'announcements'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    body = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scope = db.Column(db.Enum('university', 'department', 'course'), nullable=False)
    # Nullable per the spec: only populated when scope narrows the
    # announcement to a specific department/course. Not cross-validated at
    # the schema level (e.g. scope='course' implying course_id must be
    # set) -- that's an application-layer check, same as elsewhere in this
    # file where business rules aren't enforceable as plain columns.
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


# ==========================================
# 8. RESULTS
# ==========================================
class Result(db.Model):
    # NEW TABLE.
    __tablename__ = 'results'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    semester_id = db.Column(db.Integer, db.ForeignKey('semesters.id'), nullable=False)
    # DESIGN DECISION: Numeric(5,2) -- e.g. 85.50 -- rather than Float, to
    # avoid floating-point rounding surprises on an academic score. Assumed
    # both score and grade are required together (a Result row represents
    # a finalized entry, not a partial draft); flagging in case that's
    # wrong and one of them should be nullable pending the other.
    score = db.Column(db.Numeric(5, 2), nullable=False)
    grade = db.Column(db.Enum('A', 'B', 'C', 'D', 'F'), nullable=False)
    entered_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint('student_id', 'course_id', 'semester_id', name='uq_result_student_course_semester'),
    )
