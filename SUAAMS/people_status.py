"""Student and lecturer status: who is still part of the school.

The ONLY place Student.status / Lecturer.status should change, because a
status carries side effects that must happen together:

  * anything but "active" switches the login off (User.is_active = False)
    and revokes the phone's refresh token. Web pages and every app request
    check is_active (api/auth.install_account_check), so the account is
    refused at its next request and the app signs out;
  * a student's exit (graduated, withdrawn, expelled, deceased) releases the
    phone binding, so that phone can be used by another student later;
  * a lecturer who has LEFT is taken off the co-lecturer list of every course
    still running, and is refused while they coordinate one -- a course must
    always have a coordinator, so the admin picks the replacement first.

Nothing is ever deleted: attendance, results and the sessions a lecturer
ran stay. Setting someone back to "active" switches the login back on (a
returning suspended or rusticated student; a lecturer back from leave).
"""
import csv
import io

from campus_time import campus_today
from models import db, Course, DeviceToken, Lecturer, Semester, Student, course_lecturers

STUDENT_STATUSES = {
    'active': 'Active',
    'suspended': 'Suspended',
    'rusticated': 'Rusticated',
    'graduated': 'Graduated',
    'withdrawn': 'Withdrawn',
    'expelled': 'Expelled',
    'deceased': 'Deceased',
}
# Leaving for good: the phone binding is released.
STUDENT_EXITS = {'graduated', 'withdrawn', 'expelled', 'deceased'}

LECTURER_STATUSES = {
    'active': 'Active',
    'on_leave': 'On leave',
    'left': 'Left',
}

REASON_MAX = 255
MAX_ROWS = 2000         # a whole graduating set fits in one file


class StatusError(ValueError):
    pass


def _check(status, statuses, reason):
    if status not in statuses:
        raise StatusError('Choose a valid status.')
    reason = ' '.join((reason or '').split())
    if not reason:
        raise StatusError('Give a short reason -- it goes in the activity log.')
    if len(reason) > REASON_MAX:
        raise StatusError(f'Keep the reason under {REASON_MAX} characters.')
    return reason


def _switch_login(user, active):
    if user is None:
        return
    user.is_active = active
    if not active:
        user.current_refresh_jti = None     # the phone can't refresh any more
        # Nor receive pushes: an expelled student's or departed lecturer's
        # phone shouldn't keep getting the school's notifications. Back to
        # active, the app registers again at its next login.
        DeviceToken.query.filter_by(user_id=user.id).delete()


def set_student_status(student, status, reason):
    """Returns the cleaned reason, or None if the status didn't change.
    Not committed: the caller commits with its audit entry."""
    reason = _check(status, STUDENT_STATUSES, reason)
    if student.status == status:
        return None
    student.status = status
    _switch_login(student.user, status == 'active')
    if status in STUDENT_EXITS:
        student.unbind_device()
    return reason


def running_courses(lecturer, coordinating=True):
    """Courses not yet over that this lecturer coordinates (or co-teaches):
    no semester set, or a semester that hasn't ended."""
    not_over = db.or_(Course.semester_id.is_(None), Semester.end_date >= campus_today())
    query = Course.query.outerjoin(Semester, Course.semester_id == Semester.id).filter(not_over)
    if coordinating:
        query = query.filter(Course.lecturer_id == lecturer.id)
    else:
        query = query.join(course_lecturers, course_lecturers.c.course_id == Course.id) \
                     .filter(course_lecturers.c.lecturer_id == lecturer.id)
    return query.order_by(Course.course_code).all()


def set_lecturer_status(lecturer, status, reason):
    """Returns the cleaned reason, or None if the status didn't change.
    Raises StatusError if they still coordinate a running course."""
    reason = _check(status, LECTURER_STATUSES, reason)
    if lecturer.status == status:
        return None
    if status == 'left':
        coordinated = running_courses(lecturer)
        if coordinated:
            codes = ', '.join(c.course_code for c in coordinated)
            raise StatusError(f"{lecturer.full_name} still coordinates {codes}. Choose a new coordinator "
                              f"on the Courses page first.")
        for course in running_courses(lecturer, coordinating=False):
            course.co_lecturers = [l for l in course.co_lecturers if l.id != lecturer.id]
    lecturer.status = status
    _switch_login(lecturer.user, status == 'active')
    return reason


# ---- bulk: a CSV of matric numbers / staff IDs -----------------------------------

def read_ids(data, column):
    """bytes of a CSV with a `column` header (or a bare list of IDs, one per
    line) -> unique IDs in file order. Raises StatusError."""
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise StatusError("The file isn't UTF-8 text. In Excel use Save As -> \"CSV UTF-8\".")
    rows = [r for r in csv.reader(io.StringIO(text)) if r and r[0].strip()]
    if not rows:
        raise StatusError('The file is empty.')
    header = [h.strip().lower().replace(' ', '_') for h in rows[0]]
    index = header.index(column) if column in header else None
    if index is not None:
        rows = rows[1:]
    ids = list(dict.fromkeys(r[index or 0].strip() for r in rows if len(r) > (index or 0) and r[index or 0].strip()))
    if len(ids) > MAX_ROWS:
        raise StatusError(f'The file has {len(ids)} IDs. Use at most {MAX_ROWS} at a time.')
    return ids


def find_people(kind, ids):
    """(found [person], missing [id]) -- matched case-insensitively."""
    model, column = (Student, Student.matric_number) if kind == 'students' else (Lecturer, Lecturer.staff_id)
    found = {}
    lowered = [i.lower() for i in ids]
    for start in range(0, len(lowered), 500):
        for person in model.query.filter(db.func.lower(column).in_(lowered[start:start + 500])):
            found[(person.matric_number if kind == 'students' else person.staff_id).lower()] = person
    return [found[i] for i in lowered if i in found], [i for i in ids if i.lower() not in found]
