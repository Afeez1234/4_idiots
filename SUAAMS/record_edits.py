"""Fixing and removing courses, lecturers and students from the admin pages.

Before this, a record created with a typo (a wrong course code, a misspelt
lecturer's name) could only be "fixed" by deleting its whole department.

EDIT is always allowed. Everything else in the system points at these rows
by id -- sessions, attendance, enrollments, the beacon (student_id), the
app's login token (user id) -- so a corrected code or name shows up
everywhere on the next page load or app refresh, and nobody is signed out.

Two things travel with an edit:
  * a staff ID / matric number is also the login username, so it changes
    User.username in the same step;
  * if that person has never set their own password, their password is
    still the default -- the OLD (mistyped) ID. It is reset to the new ID,
    so "your first password is your staff ID / matric number" stays true.

DELETE is only for records nothing has happened to yet: the course that was
created by mistake this morning, not one with a semester of attendance
under it. A record with history is refused with the reason, and the admin
uses Status (people_status.py) or reassigns the course instead. That rule
is the whole safety net -- the page asks a plain "are you sure", not a
type-the-name confirmation like faculty deletes, because what a delete here
can take with it is small: enrollments and draft timetable slots for a
course, co-lecturer links for a lecturer, course registrations for a
student. Those are counted into the audit entry before they go.
"""
import bcrypt
from sqlalchemy import func

from models import (
    db, Announcement, Attendance, Course, Department, Enrollment, Lecturer,
    OfflineCheckinLog, Result, Semester, Session, Student, Timetable, User,
)
from utils import normalize_level

KINDS = ('courses', 'lecturers', 'students')


class EditError(ValueError):
    pass


# ---- reading the form -------------------------------------------------------

def _text(form, name, label, max_len):
    value = ' '.join((form.get(name) or '').split())
    if not value:
        raise EditError(f'{label} is required.')
    if len(value) > max_len:
        raise EditError(f'{label} must be {max_len} characters or fewer.')
    return value


def _ref(form, name, model, label, required=True):
    """An id from a <select>, checked to exist. None when optional and blank."""
    raw = str(form.get(name) or '').strip()
    if not raw:
        if required:
            raise EditError(f'Choose a {label}.')
        return None
    try:
        row = db.session.get(model, int(raw))
    except ValueError:
        row = None
    if row is None:
        raise EditError(f'That {label} no longer exists.')
    return row.id


def _username_taken(username, user_id):
    """Case-insensitive, so 'stf/1' can't sit beside 'STF/1'."""
    return db.session.query(User.id).filter(
        func.lower(User.username) == username.lower(), User.id != user_id,
    ).first() is not None


def _rename_login(user, new_id):
    """Move the login to the corrected ID (see module docstring)."""
    if user is None or user.username == new_id:
        return
    user.username = new_id
    if user.requires_password_change:
        user.password_hash = bcrypt.hashpw(new_id.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def _apply(record, fields):
    """Set the fields; return {field: {'from', 'to'}} for those that changed."""
    diff = {}
    for name, value in fields.items():
        old = getattr(record, name)
        if old != value:
            diff[name] = {'from': old, 'to': value}
            setattr(record, name, value)
    return diff


# ---- edit -------------------------------------------------------------------
# Each returns the changes (empty if nothing changed). Not committed: the
# route commits together with its audit entry, like people_status.

def edit_course(course, form):
    code = _text(form, 'code', 'Course code', 20).upper()
    semester_id = _ref(form, 'semester_id', Semester, 'semester', required=False)
    units = (form.get('credit_units') or '').strip()
    if units:
        if not units.isdigit() or not 1 <= int(units) <= 10:
            raise EditError('Credit units must be a whole number from 1 to 10.')
        units = int(units)
    else:
        units = None
    # Same rule as uq_course_code_semester, checked first so the admin gets
    # a sentence instead of a database error.
    clash = Course.query.filter(
        Course.course_code == code, Course.semester_id == semester_id, Course.id != course.id,
    ).first()
    if clash:
        raise EditError(f'{code} already exists in that semester.')
    return _apply(course, {
        'course_code': code,
        'course_title': _text(form, 'title', 'Course title', 150),
        # Blank allowed: general courses (GST) belong to no department.
        'department_id': _ref(form, 'department_id', Department, 'department', required=False),
        'semester_id': semester_id,
        'credit_units': units,
    })


def edit_lecturer(lecturer, form):
    staff_id = _text(form, 'staff_id', 'Staff ID', 50)
    if staff_id != lecturer.staff_id and _username_taken(staff_id, lecturer.user_id):
        raise EditError(f"Staff ID '{staff_id}' is already someone's login.")
    diff = _apply(lecturer, {
        'full_name': _text(form, 'full_name', 'Full name', 150),
        'staff_id': staff_id,
        'department_id': _ref(form, 'department_id', Department, 'department'),
    })
    if 'staff_id' in diff:
        _rename_login(lecturer.user, staff_id)
    return diff


def edit_student(student, form):
    matric = _text(form, 'matric_number', 'Matric number', 50)
    if matric != student.matric_number and _username_taken(matric, student.user_id):
        raise EditError(f"Matric number '{matric}' is already someone's login.")
    level = normalize_level(form.get('level'))
    if level is None:
        raise EditError('Level must be one of 100, 200, 300, 400 or 500.')
    rfid = (form.get('rfid_uid') or '').strip() or None
    if rfid and Student.query.filter(Student.rfid_uid == rfid, Student.id != student.id).first():
        raise EditError(f'RFID card {rfid} belongs to another student.')
    diff = _apply(student, {
        'full_name': _text(form, 'full_name', 'Full name', 150),
        'matric_number': matric,
        'level': level,
        'department_id': _ref(form, 'department_id', Department, 'department'),
        'rfid_uid': rfid,
    })
    if 'matric_number' in diff:
        _rename_login(student.user, matric)
    return diff


EDITORS = {'courses': edit_course, 'lecturers': edit_lecturer, 'students': edit_student}


# ---- what blocks a delete ---------------------------------------------------
# One GROUP BY per kind of history, for a whole page of rows at once, so the
# roster can grey out the Delete button without a query per row.

def _counts(column, ids):
    if not ids:
        return {}
    return dict(db.session.query(column, func.count()).filter(column.in_(ids)).group_by(column))


def _plural(n, word):
    return f'{n} {word}' + ('' if n == 1 else 's')


def delete_blockers(kind, records):
    """{record.id: reason it can't be deleted} for the records that can't."""
    ids = [r.id for r in records]
    out = {}

    def block(counts, key_of, sentence):
        for r in records:
            n = counts.get(key_of(r), 0)
            if n and r.id not in out:
                out[r.id] = sentence(n, r)

    if kind == 'courses':
        block(_counts(Session.course_id, ids), lambda r: r.id,
              lambda n, r: f'Has {_plural(n, "class session")}.')
        block(_counts(Result.course_id, ids), lambda r: r.id,
              lambda n, r: f'Has {_plural(n, "result")}.')

    elif kind == 'lecturers':
        user_ids = [r.user_id for r in records]
        by_user = lambda r: r.user_id   # noqa: E731
        coordinated = {}
        for lect_id, code in (db.session.query(Course.lecturer_id, Course.course_code)
                              .filter(Course.lecturer_id.in_(ids))):
            coordinated.setdefault(lect_id, []).append(code)
        for r in records:
            if r.id in coordinated:
                out[r.id] = (f'Coordinates {", ".join(sorted(coordinated[r.id]))}. '
                             f'Make someone else coordinator first.')
        # Things they did that carry their name. Some of these columns are
        # NOT NULL (the delete would fail outright); the rest are SET NULL,
        # which would quietly erase who ran the class or marked the student.
        for column, word in ((Session.started_by, 'class session'),
                             (Attendance.marked_by, 'attendance mark'),
                             (OfflineCheckinLog.reviewed_by, 'offline tap review'),
                             (Result.entered_by, 'result'),
                             (Announcement.sender_id, 'announcement'),
                             (Timetable.created_by, 'timetable slot')):
            block(_counts(column, user_ids), by_user,
                  lambda n, r, word=word: f'Has {_plural(n, word)}. Set status to Left instead.')

    elif kind == 'students':
        for column, word in ((Attendance.student_id, 'attendance record'),
                             (OfflineCheckinLog.student_id, 'offline tap'),
                             (Result.student_id, 'result')):
            block(_counts(column, ids), lambda r: r.id,
                  lambda n, r, word=word: f'Has {_plural(n, word)}. Use Status instead.')

    return out


# ---- delete -----------------------------------------------------------------

def delete_record(kind, record):
    """Delete a record with no history; return what went with it (counts).
    Raises EditError with the reason if it has history. Not committed."""
    reason = delete_blockers(kind, [record]).get(record.id)
    if reason:
        raise EditError(reason)

    if kind == 'courses':
        removed = {
            'enrollments': Enrollment.query.filter_by(course_id=record.id).count(),
            'timetable_slots': Timetable.query.filter_by(course_id=record.id).count(),
            'announcements': Announcement.query.filter_by(course_id=record.id).count(),
            'co_lecturers': len(record.co_lecturers),
        }
        # Course's cascades remove the enrollments, slots and announcements;
        # the co-lecturer links go with the course through `secondary`.
        db.session.delete(record)
        return removed

    if kind == 'lecturers':
        # Their co-lecturer links. Removed through the Course side, which
        # owns the relationship: deleting the Lecturer alone leaves the link
        # rows to the database's ON DELETE CASCADE, which SQLite (tests)
        # doesn't enforce.
        courses = Course.query.filter(Course.co_lecturers.any(Lecturer.id == record.id)).all()
        for course in courses:
            course.co_lecturers.remove(record)
        removed = {'co_lecturer_on': len(courses)}
    else:
        removed = {'enrollments': Enrollment.query.filter_by(student_id=record.id).count()}

    # The login goes too. User's cascades take the profile row (and with it
    # a student's enrollments), device tokens and notifications.
    if record.user is not None:
        db.session.delete(record.user)
    else:
        db.session.delete(record)
    return removed
