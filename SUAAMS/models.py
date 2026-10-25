from campus_time import campus_today
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timezone
from sqlalchemy.dialects.mysql import MEDIUMTEXT

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
    # Years in the programme (4 or 5). Its final level is years x 100: the
    # yearly promotion (promotion.py) stops there and lists those students
    # as due to graduate instead. Nullable: departments made before this
    # existed have none until an admin sets it, and promotion refuses to
    # run while any department with students is missing it.
    programme_years = db.Column(db.Integer, nullable=True)

    students = db.relationship('Student', backref='department', lazy=True, cascade="all, delete-orphan")
    lecturers = db.relationship('Lecturer', backref='department', lazy=True, cascade="all, delete-orphan")
    # NEW: HOD profiles cascade the same way Student/Lecturer profiles do --
    # deleting a department removes the HOD record tied to it (not the
    # underlying User account, which cascades separately from User itself).
    hods = db.relationship('HOD', backref='department', lazy=True, cascade="all, delete-orphan")
    courses = db.relationship('Course', backref='department', lazy=True, cascade="all, delete-orphan")


class PromotionRun(db.Model):
    # One row per academic year in which students were moved up a level
    # (promotion.py). academic_year is unique, which is what stops the same
    # year being promoted twice -- e.g. by someone re-running it after
    # activating the second semester. moves holds {new_level: [student_id,
    # ...]} as JSON so the run can be undone exactly: only students still at
    # the level this run gave them are moved back. MEDIUMTEXT on MySQL: plain
    # TEXT stops at 64 KB, about 10,000 students' ids.
    __tablename__ = 'promotion_runs'
    id = db.Column(db.Integer, primary_key=True)
    academic_year = db.Column(db.String(20), nullable=False, unique=True)
    promoted = db.Column(db.Integer, nullable=False)
    moves = db.Column(db.Text().with_variant(MEDIUMTEXT, 'mysql'), nullable=False)
    run_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


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
    # NEW: push notification support (see DeviceToken/Notification below).
    device_tokens = db.relationship('DeviceToken', backref='user', lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade="all, delete-orphan")


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
    # Where the student stands with the school: active, suspended,
    # rusticated, graduated, withdrawn, expelled, deceased -- see
    # people_status.py, which is the only place that should change it (it
    # also switches the login off and releases the phone). A status, never a
    # delete: deleting a student cascades away their attendance and results.
    status = db.Column(db.String(20), nullable=False, default='active', server_default='active')
    # Unused since 2026-10-23: the RFID card reader was retired on
    # 2026-10-12 and nothing asks for or shows this any more. Kept until a
    # migration drops it.
    rfid_uid = db.Column(db.String(50), unique=True, nullable=True)
    # unique: one phone binds at most one student (see mobile_login in
    # api/auth.py). NULL means unbound, and MySQL allows any number of NULLs
    # in a unique index, so unbound students don't collide.
    device_id = db.Column(db.String(255), unique=True, nullable=True)
    # When the current phone was bound (UTC); NULL while unbound, and for
    # phones bound before 2026-10-25, when this was added. The admin's
    # record drawer shows it. Set and cleared only through bind_device /
    # unbind_device below, so the two columns can't disagree.
    device_bound_at = db.Column(db.DateTime, nullable=True)
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
    # Read watermark for the announcements badge. An announcement counts as
    # unread for this student while its id is greater than this value.
    #
    # A watermark rather than a per-announcement read receipt (a join table
    # of student x announcement) on purpose: the list is ordered newest-first
    # and shown in full, so "everything above this line has been seen" is the
    # only distinction the UI actually needs. A receipt table would grow
    # unboundedly for no visible gain.
    #
    # Null means "has never opened the list" -- every announcement is
    # unread, which is the correct default for a new install. It is also
    # what makes the behaviour safe if this column is added to an existing
    # table: nobody silently loses a badge they should have seen.
    last_seen_announcement_id = db.Column(db.Integer, nullable=True)

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

    def bind_device(self, device_id):
        """Lock the account to this phone (first login). Not committed."""
        self.device_id = device_id
        self.device_bound_at = datetime.now(timezone.utc)

    def unbind_device(self):
        """Release the phone (admin unbind, or a status that ends the
        account). Not committed."""
        self.device_id = None
        self.device_bound_at = None
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
    # active, on_leave or left -- see people_status.py. Like Student.status,
    # changed only there, never by deleting the row (their past sessions
    # and the attendance under them must survive them leaving).
    status = db.Column(db.String(20), nullable=False, default='active', server_default='active')

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
    # The course COORDINATOR. A course can have more lecturers than this
    # (see co_lecturers below); every lecturer on it has the same powers.
    # Kept as the existing column so courses with one lecturer need nothing
    # new, and so the coordinator lives in exactly one place.
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

    # Lecturers who teach the course alongside the coordinator. Courses here
    # routinely have several (a GST course can list six), and before this
    # only the coordinator could start sessions, mark students present or be
    # notified -- the others couldn't run their own classes at all.
    co_lecturers = db.relationship('Lecturer', secondary='course_lecturers', lazy='selectin')

    @property
    def all_lecturers(self):
        """Coordinator first, then co-lecturers."""
        people = [self.lecturer] if self.lecturer else []
        return people + [l for l in self.co_lecturers if l is not self.lecturer]

    @property
    def lecturer_names(self):
        """Every lecturer's name, comma-separated (or None)."""
        return ', '.join(l.full_name for l in self.all_lecturers) or None

    @property
    def lecturer_summary(self):
        """Short form for tables: 'Dr A' or 'Dr A + 2 more' (or None)."""
        people = self.all_lecturers
        if not people:
            return None
        extra = len(people) - 1
        return people[0].full_name + (f' + {extra} more' if extra else '')


# Co-lecturers of a course (the coordinator stays on courses.lecturer_id).
# Rows go when either the course or the lecturer is deleted.
course_lecturers = db.Table(
    'course_lecturers',
    db.Column('course_id', db.Integer, db.ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True),
    db.Column('lecturer_id', db.Integer, db.ForeignKey('lecturers.id', ondelete='CASCADE'), primary_key=True),
)


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

    # Lecture / Tutorial / Practical ('L', 'T', 'P'), as printed on the
    # Student Affairs sheets: "ACC204(T)". NULL for slots added by hand.
    kind = db.Column(db.String(1), nullable=True)

    # Draft slots (from a timetable import that hasn't been published yet)
    # are invisible to students and lecturers, and aren't used for the "what
    # should be running now" lookups -- but they still count for clash
    # checks, because a planned class still occupies its room. Slots added
    # one at a time on the form are published straight away, as before.
    is_published = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())

    # The campus date this slot's class started running, for Analytics'
    # "classes held vs timetabled" (analytics.delivery). Without it a slot
    # added in week 6 counted weeks 1-5 as missed, and a class moved from
    # Monday to Tuesday counted Tuesdays as missed back to week 1. Set when
    # the slot is published or its course, day or times change; NOT reset
    # by a re-publish that leaves those the same (timetable_publish), so
    # re-issuing a sheet to fix a room keeps the course's history. NULL =
    # from the first day of teaching (slots from before this column).
    effective_from = db.Column(db.Date, nullable=True)

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
    # Campus date (compared with the timetable's weekday and with "today"
    # on campus), not the server's -- see campus_time.py.
    session_date = db.Column(db.Date, default=campus_today)
    is_active = db.Column(db.Boolean, default=False)
    planned_start = db.Column(db.Time, nullable=True)
    planned_end = db.Column(db.Time, nullable=True)
    # NEW
    room = db.Column(db.String(50), nullable=True)
    # Which user started this session. With several lecturers per course,
    # this is how you can tell which of them ran a given class. NULL for
    # sessions from before it was recorded. SET NULL: deleting an account
    # must not delete class history.
    started_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

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
    # How the student checked in: 'nfc' (phone tap at the terminal), 'ble'
    # (Bluetooth code, the fallback for phones that can't tap), 'rfid' (ID
    # card on the terminal), 'manual' (marked by the lecturer -- see
    # mark_student_present in utils.py), 'offline' (a tap the terminal read
    # while it couldn't reach the server, accepted by the lecturer -- see
    # review_offline_tap in utils.py). BLE is weaker evidence of presence
    # than NFC (see ble_beacon.py), so this is what lets a lecturer see the mix.
    # NULL = recorded before this column existed; method unknown. Not
    # backfilled, because guessing would be worse than admitting it.
    method = db.Column(db.String(8), nullable=True)
    # Who marked it, for method='manual' and 'offline' (NULL for every self
    # check-in).
    # A manual mark is a human vouching for presence with no device evidence
    # behind it, so it has to be attributable. ON DELETE SET NULL rather than
    # a cascade: removing a lecturer's account must not delete the
    # attendance they recorded.
    marked_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    # Which reader took the check-in (NFC tap, Bluetooth code, accepted
    # offline tap); NULL for hand marks and readers not yet registered.
    # SET NULL: retiring a reader keeps its history. See Terminal.
    # Named like the migration's, so create_all() (reset_db.py) and the
    # migration build the same constraint.
    terminal_id = db.Column(db.Integer, db.ForeignKey('terminals.id', ondelete='SET NULL',
                                                      name='fk_attendance_terminal'), nullable=True)
    # Whether that reader is in the class's room (terminal_rooms.room_verdict):
    # True = the reader is in another room, False = same room, NULL = not
    # checked (no reader, no reader room, or no class room). In "flag" mode
    # a wrong-room check-in is recorded and shown; in "enforce" mode it is
    # refused, so True only appears from flag mode.
    wrong_room = db.Column(db.Boolean, nullable=True)

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


# ==========================================
# 9. NOTIFICATIONS
# ==========================================
class DeviceToken(db.Model):
    # NEW TABLE. One row per (user, installed app instance) -- a user can
    # hold multiple rows if they're logged into more than one physical
    # device (mirrors that push delivery is per-installation, unlike
    # Student.device_id's single-device login binding above, which is a
    # separate concern). fcm_token is unique because the same token can only
    # ever point at one live app instance at a time -- if it shows up again
    # under a different user_id (e.g. someone logged out and a different
    # student logged in on the same phone), the registration endpoint
    # updates this row's user_id in place rather than inserting a duplicate.
    __tablename__ = 'device_tokens'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    fcm_token = db.Column(db.String(255), unique=True, nullable=False)
    platform = db.Column(db.Enum('android', 'ios'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Notification(db.Model):
    # NEW TABLE. Persisted in-app record of every push sent -- the source of
    # truth for the notification list screen, independent of whether the
    # FCM send itself succeeded (a student who was offline when it fired
    # still sees it here next time they open the app). `type` is a plain
    # string rather than db.Enum deliberately: more notification types
    # (absentee alerts, class-starting-soon) are on the roadmap but not
    # wired yet, and a string column avoids a schema migration just to add
    # an enum value once those land.
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.String(500), nullable=False)
    # Deep-link payload (e.g. {"session_id": 5}) -- lets the app route a tap
    # straight to the relevant screen instead of just opening to the list.
    data = db.Column(db.JSON, nullable=True)
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


# ==========================================
# 8. OFFLINE CHECK-IN LOG
# ==========================================
class OfflineCheckinLog(db.Model):
    """Taps a terminal physically read while it could not reach the backend.

    WHY THIS EXISTS, AND WHY IT CANNOT CREDIT ATTENDANCE
    ---------------------------------------------------
    The roadmap calls for terminals to log taps offline and push the
    backlog when connectivity returns. That is implemented, but with one
    hard limit baked in: a beacon is only valid for
    BEACON_TOKEN_TTL_SECONDS (beacon.py), the anti-relay window CLAUDE.md
    calls canonical. A beacon captured offline has therefore ALWAYS expired
    by the time it syncs, and the server will not -- must not -- credit it
    automatically.

    So this table records PROVENANCE, not attendance: "a terminal
    physically read a genuine beacon for this student and this session at
    time T, but the backend was unreachable at the time." The signature is
    still verified on arrival, which proves the token was minted by us and
    not forged, and the student/session binding still comes out of the
    token itself.

    The sync itself deliberately does NOT create an Attendance row, because
    doing so would let anyone with a captured RF signal mark a peer present
    hours later -- exactly the buddy-punching vector the short window exists
    to prevent. Instead the course lecturer reviews pending rows on the
    session page and accepts or rejects them (utils.review_offline_tap). An
    accepted tap becomes attendance with method='offline' and the lecturer
    as marked_by: a person vouches for it, backed by a genuine signed read.

    The terminal sends its READ time with each capture. It has no battery
    clock, but it syncs over NTP for the Bluetooth codes and keeps counting
    while offline, so the time is real once it has synced since boot. That
    read time is what closes the replay gap: a token read more than a few
    seconds after it was minted can't come from an unmodified app, so the
    sync rejects it instead of offering it for review (where "Accept all"
    would have credited it). Without a usable read time -- older firmware,
    or a terminal that booted offline and never synced -- captured_at
    falls back to the token's mint time and review works as before.
    """
    __tablename__ = 'offline_checkin_logs'
    id = db.Column(db.Integer, primary_key=True)

    # Both bound from the beacon payload itself, not trusted from the
    # terminal. A terminal cannot choose who a capture is attributed to.
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)

    # Which physical terminal produced this, for reconciliation ("terminal-02
    # at the door reported this"). Attribution only -- not authentication;
    # the terminal proves itself with X-Terminal-Secret on every request.
    terminal_id = db.Column(db.String(64), nullable=False)

    # When the student tapped: the terminal's read time (its clock is
    # NTP-synced for the Bluetooth codes). For firmware that doesn't send
    # one, or a terminal whose clock never synced, it falls back to the
    # token's mint time (exp minus the TTL). A read too long after the mint
    # is rejected at sync time -- see sync_offline_checkin_backlog.
    captured_at = db.Column(db.DateTime, nullable=False)

    # When the record reached the server. The gap between this and
    # captured_at is the outage that caused the backlog.
    synced_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # pending_verification -- a genuine tap, no attendance recorded; needs a
    #                        lecturer to look at it.
    # superseded          -- attendance for this student/session was already
    #                        recorded live, so this adds nothing.
    # accepted            -- the lecturer accepted it; an Attendance row with
    #                        method='offline' now exists.
    # rejected            -- the lecturer rejected it, or the student is no
    #                        longer enrolled. Kept for the audit trail.
    status = db.Column(
        db.Enum('pending_verification', 'superseded', 'accepted', 'rejected'),
        default='pending_verification',
        nullable=False,
    )
    # Why a record landed in 'rejected' or 'superseded' -- kept short and
    # human-readable so the audit trail shows a reason, not a stack trace.
    reason = db.Column(db.String(120), nullable=True)

    # Which lecturer accepted or rejected it, and when. NULL while pending.
    # ON DELETE SET NULL for the same reason as Attendance.marked_by:
    # removing a lecturer's account must not erase the review history.
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    # Same meaning as Attendance.wrong_room, worked out at sync time from
    # the reader that uploaded the tap; copied onto the attendance row if
    # the lecturer accepts it.
    wrong_room = db.Column(db.Boolean, nullable=True)

    student = db.relationship('Student')

    __table_args__ = (
        # One row per student per session. The terminal may capture the
        # same tap more than once (a student tapping twice at a door that
        # was offline), and a second identical record tells a lecturer
        # nothing new. This also makes the sync endpoint idempotent, so a
        # retried flush can't duplicate rows.
        db.UniqueConstraint('student_id', 'session_id', name='uq_offline_checkin_student_session'),
        # Reconciliation queries filter by session then status.
        db.Index('ix_offline_checkin_session_status', 'session_id', 'status'),
    )


# ==========================================
# READERS (ESP32 TERMINALS)
# ==========================================
class Terminal(db.Model):
    """One physical reader, registered on the admin Terminals page.

    Before this the server knew ONE reader identity (TERMINAL_ID /
    TERMINAL_SECRET in the environment), shared by every reader, so it
    couldn't tell readers apart: any reader accepted any class's check-in,
    and one dumped board exposed the secret of all of them. Each reader now
    has its own code and secret, and a room, so a check-in at a reader in
    another room can be flagged or refused (terminal_rooms.py).

    The secret is shown to the admin once, when generated, and only its
    SHA-256 is stored. A plain hash is enough here: the secret is 32 random
    bytes, not a password a person chose, so there's nothing to guess.
    """
    __tablename__ = 'terminals'
    id = db.Column(db.Integer, primary_key=True)
    # What the reader sends as X-Terminal-Id (TERMINAL_ID in its secrets.h).
    code = db.Column(db.String(32), nullable=False, unique=True)
    name = db.Column(db.String(100), nullable=False)
    # As written on the timetable ("LT 1"); compared loosely, so "LT1" and
    # "lt-1" match too. NULL = a reader with no fixed room: never flagged.
    room = db.Column(db.String(50), nullable=True)
    # BLE_TERMINAL_NUMBER in its secrets.h; inside every Bluetooth code it
    # broadcasts (covered by the code's HMAC), which is how a Bluetooth
    # check-in is traced to this reader.
    ble_number = db.Column(db.Integer, nullable=True, unique=True)
    secret_hash = db.Column(db.String(64), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    # Updated on every request the reader authenticates (check-in, offline
    # upload); the Terminals page shows online/offline from it.
    last_seen_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# ==========================================
# AUDIT TRAIL
# ==========================================
class AuditLog(db.Model):
    """One row per change someone made through the admin dashboard (plus
    admin logins, password changes, and accounts created from the command
    line). Written by audit.log_action(); read by the admin Activity page.

    Append-only by convention: nothing in the app updates or deletes these
    rows. That is what makes it worth trusting when several people share
    admin access -- each of them has a personal login (create_admin.py), and
    every entry names who did it.
    """
    __tablename__ = 'audit_logs'

    # Integer, not BigInteger: 2 billion entries is far beyond this
    # project's life, and SQLite (the test database) only auto-increments a
    # plain INTEGER primary key.
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime, nullable=False, index=True,
        default=lambda: datetime.now(timezone.utc),
    )

    # Who did it. actor_id is deliberately NOT a foreign key: an audit
    # entry must outlive the account it describes, and even ON DELETE SET
    # NULL would erase which account it was. actor_label is a snapshot of
    # the username at the time, so a later rename doesn't rewrite history.
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    actor_label = db.Column(db.String(100), nullable=False)
    actor_role = db.Column(db.String(20), nullable=True)

    # What happened, as "thing.verb" -- e.g. "student.create",
    # "faculty.delete". Indexed because the Activity page filters on it.
    action = db.Column(db.String(60), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=True)
    entity_id = db.Column(db.String(64), nullable=True)
    # A short human sentence for the Activity page ("Created student Ada Obi
    # (MCT/19/0001)"), so reading the log never needs a database lookup that
    # would fail once the thing has been deleted.
    summary = db.Column(db.String(255), nullable=False)
    # Machine-readable specifics: before/after values, counts, filenames.
    # Secrets are stripped before they get here (audit._scrub).
    details = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
