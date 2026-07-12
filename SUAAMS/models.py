from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date, timezone

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum('admin', 'lecturer', 'student'), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    requires_password_change = db.Column(db.Boolean, default=False)

    # Relationships with Cascades (Deleting a user deletes their profile automatically)
    student = db.relationship('Student', backref='user', uselist=False, cascade="all, delete-orphan")
    lecturer = db.relationship('Lecturer', backref='user', uselist=False, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<User {self.username}>'


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column('FULL_NAME', db.String(150), nullable=False)
    matric_number = db.Column('MATRIC_NUMBER', db.String(50), unique=True, nullable=False)
    department = db.Column('DEPARTMENT', db.String(100))
    level = db.Column('LEVEL', db.String(20))
    rfid_uid = db.Column('RFID_UID', db.String(50), unique=True)
    
    # Timezone-aware timestamp
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Advanced Relationships
    # 1. The Direct Many-to-Many (Lets you do `student.courses` directly!)
    courses = db.relationship('Course', secondary='enrollments', backref=db.backref('enrolled_students', lazy='dynamic'))
    
    # 2. Standard relationships with cleanup cascades
    enrollments = db.relationship('Enrollment', backref='student', lazy='dynamic', cascade="all, delete-orphan")
    attendance_records = db.relationship('Attendance', backref='student', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Student {self.matric_number}>'


class Lecturer(db.Model):
    __tablename__ = 'lecturers'

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    staff_id = db.Column(db.String(50), unique=True, nullable=False)
    department = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # Relationships
    courses = db.relationship('Course', backref='lecturer', lazy='dynamic')

    def __repr__(self):
        return f'<Lecturer {self.staff_id}>'


class Course(db.Model):
    __tablename__ = 'courses'

    id = db.Column(db.Integer, primary_key=True)
    course_title = db.Column(db.String(150), nullable=False)
    course_code = db.Column(db.String(20), unique=True, nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('lecturers.id'))

    # Relationships with cleanup cascades
    sessions = db.relationship('Session', backref='course', lazy='dynamic', cascade="all, delete-orphan")
    enrollments = db.relationship('Enrollment', backref='course', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Course {self.course_code}>'


class Session(db.Model):
    __tablename__ = 'sessions'

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))
    start_time = db.Column(db.Time)
    stop_time = db.Column(db.Time)
    session_date = db.Column(db.Date, default=date.today)
    is_active = db.Column(db.Boolean, default=False)
    planned_start = db.Column(db.Time)
    planned_end = db.Column(db.Time)

    # Relationships with cleanup cascades
    attendance_records = db.relationship('Attendance', backref='session', lazy='dynamic', cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Session {self.id} - Course {self.course_id}>'


class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'))

    def __repr__(self):
        return f'<Enrollment Student {self.student_id} - Course {self.course_id}>'


class Attendance(db.Model):
    __tablename__ = 'attendance'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'))
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'))
    
    # Timezone-aware timestamp
    time_in = db.Column('TIME_IN', db.Time, default=lambda: datetime.now(timezone.utc).time())
    status = db.Column(db.String(20), default='present')

    def __repr__(self):
        return f'<Attendance Student {self.student_id} - Session {self.session_id}>'