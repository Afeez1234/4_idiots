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
    
    # Cascade delete to clean up departments if a faculty is removed
    departments = db.relationship('Department', backref='faculty', lazy=True, cascade="all, delete-orphan")


class Department(db.Model):
    __tablename__ = 'departments'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('faculties.id'), nullable=False)
    
    # Resolved duplicate declarations; unified with clean cascades
    students = db.relationship('Student', backref='department', lazy=True, cascade="all, delete-orphan")
    lecturers = db.relationship('Lecturer', backref='department', lazy=True, cascade="all, delete-orphan")
    courses = db.relationship('Course', backref='department', lazy=True, cascade="all, delete-orphan")


# ==========================================
# 2. AUTHENTICATION & ROLES
# ==========================================
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'lecturer', 'student'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    requires_password_change = db.Column(db.Boolean, default=True) 

    # Clean cascading links to profiles
    student = db.relationship('Student', backref='user', uselist=False, cascade="all, delete-orphan")
    lecturer = db.relationship('Lecturer', backref='user', uselist=False, cascade="all, delete-orphan")


# ==========================================
# 3. CORE PROFILES
# ==========================================
class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    matric_number = db.Column(db.String(50), unique=True, nullable=False)
    level = db.Column(db.Integer, nullable=False)
    rfid_uid = db.Column(db.String(50), unique=True, nullable=True)
    device_id = db.Column(db.String(255), nullable=True) 
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Direct many-to-many relationship helper to keep student.courses loops fully backward-compatible
    courses = db.relationship('Course', secondary='enrollments', backref=db.backref('enrolled_students', lazy='dynamic'))
    
    # Cascade deletes to cleanly wipe logs if a student is removed from the system
    enrollments = db.relationship('Enrollment', backref='student', lazy=True, cascade="all, delete-orphan")
    attendance = db.relationship('Attendance', backref='student', lazy=True, cascade="all, delete-orphan")


class Lecturer(db.Model):
    __tablename__ = 'lecturers'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    courses = db.relationship('Course', backref='lecturer', lazy=True)


# ==========================================
# 4. ACADEMIC STRUCTURE
# ==========================================
class Course(db.Model):
    __tablename__ = 'courses'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=False)
    
    # Cascades to clean up structural timetable entries, sessions, and academic enrollments
    sessions = db.relationship('Session', backref='course', lazy=True, cascade="all, delete-orphan")
    timetable = db.relationship('Timetable', backref='course', lazy=True, cascade="all, delete-orphan")
    enrollments = db.relationship('Enrollment', backref='course', lazy=True, cascade="all, delete-orphan")


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)


# ==========================================
# 5. TIMETABLE & SESSIONS
# ==========================================
class Timetable(db.Model):
    __tablename__ = 'timetable'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    day_of_week = db.Column(db.Integer, nullable=False) # 0 = Monday, 6 = Sunday
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room = db.Column(db.String(50), nullable=True)


class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    session_date = db.Column(db.Date, default=date.today)
    is_active = db.Column(db.Boolean, default=False)
    planned_start = db.Column(db.Time)
    planned_end = db.Column(db.Time)

    # Added relationship link to make querying session attendance records painless
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
    status = db.Column(db.Enum('present', 'absent', 'excused'), default='present')