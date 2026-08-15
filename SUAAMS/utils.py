from datetime import datetime, timedelta
from flask import session,redirect,url_for,flash
from functools import wraps

#it finally worked !!!!!!!!!
def login_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access that page.', 'error')
                return redirect(url_for('auth.login'))
            if session.get('role') != role:
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)
        return wrapper
    return decorator


def session_status_for_course(course_id, on_date):
    """
    (session_status, present_count) for a course on a given date -- shared
    by resolve_current_course() below and the admin timetable grid's
    per-slot "today" status (blueprints/admin.py's _build_timetable_grid),
    so both places agree on what "live"/"ended"/"not_started" means instead
    of each re-deriving it from Session/Attendance independently.
    """
    from models import Session as SessionModel, Attendance

    session_row = (
        SessionModel.query
        .filter_by(course_id=course_id, session_date=on_date)
        .order_by(SessionModel.id.desc())
        .first()
    )
    if session_row is None:
        return 'not_started', None
    status = 'live' if session_row.is_active else 'ended'
    return status, Attendance.query.filter_by(session_id=session_row.id).count()


def resolve_current_course(semester=None, at=None):
    """
    Timetable -> "what's happening right now" resolution (day of week +
    current time + active academic session -> matching Timetable slot ->
    course/room/session status). Local import of models to avoid a
    models<->utils circular import at module load time.

    Boundary choice: start_time <= now < end_time (inclusive start,
    exclusive end) -- so back-to-back slots never both claim the exact
    boundary instant.

    Returns a plain dict (JSON-serializable) with a 'status' of:
    - 'no_active_semester'  -- no Semester has is_active=True (and none was
      passed in explicitly)
    - 'no_class_now'        -- active semester exists, but no Timetable slot
      covers this exact weekday+time
    - 'in_session'          -- a slot matches; course/room/session details
      included. 'overlap_warning' is True if more than one slot matched
      (data-integrity edge case -- the conflict check on create/update
      should prevent this going forward, but older/imported rows might
      still collide); the earliest start_time (then lowest id) is used as
      the deterministic pick.
    """
    from models import Timetable, Semester

    now = at or datetime.now()

    if semester is None:
        semester = Semester.query.filter_by(is_active=True).first()
    if semester is None:
        return {'status': 'no_active_semester'}

    today_weekday = now.weekday()
    current_time = now.time()

    candidates = (
        Timetable.query
        .filter(
            Timetable.semester_id == semester.id,
            Timetable.day_of_week == today_weekday,
            Timetable.start_time <= current_time,
            Timetable.end_time > current_time,
        )
        .order_by(Timetable.start_time.asc(), Timetable.id.asc())
        .all()
    )
    # Defensive: course_id/start_time/end_time are all NOT NULL in the
    # schema, so this should never filter anything out in practice -- kept
    # anyway so a malformed/orphaned row can't turn into a 500 here.
    candidates = [c for c in candidates if c.course is not None]

    if not candidates:
        return {'status': 'no_class_now', 'semester': semester.name}

    entry = candidates[0]
    overlap_warning = len(candidates) > 1

    session_status, present_count = session_status_for_course(entry.course_id, now.date())

    return {
        'status': 'in_session',
        'entry_id': entry.id,
        'course_id': entry.course_id,
        'course_code': entry.course.course_code,
        'course_title': entry.course.course_title,
        'lecturer': entry.course.lecturer.full_name if entry.course.lecturer else None,
        'room': entry.room,
        'start_time': entry.start_time.strftime('%H:%M'),
        'end_time': entry.end_time.strftime('%H:%M'),
        'semester': semester.name,
        'overlap_warning': overlap_warning,
        'session_status': session_status,
        'present_count': present_count,
    }


# Grace period after Session.planned_start during which a check-in still
# counts as 'present' rather than 'late'.
LATE_GRACE_MINUTES = 10


def compute_attendance_status(session, at=None):
    """
    Session.planned_start + LATE_GRACE_MINUTES -> 'present' or 'late' for a
    check-in happening right now. planned_start is optional (a lecturer can
    start a session without one), in which case there's no scheduled time to
    be late against, so this always returns 'present'. Compares naive local
    wall-clock time, matching resolve_current_course()'s existing convention
    for Timetable/Session time columns (none of them are timezone-aware).
    """
    if session.planned_start is None:
        return 'present'

    now = at or datetime.now()
    session_date = session.session_date or now.date()
    cutoff = datetime.combine(session_date, session.planned_start) + timedelta(minutes=LATE_GRACE_MINUTES)
    return 'late' if now > cutoff else 'present'


def resolve_timetable_slot_for_course(course_id, semester=None, on_date=None):
    """
    Course + today's weekday -> its scheduled Timetable slot, used to
    auto-fill Session.planned_start/planned_end when a lecturer starts a
    session instead of requiring manual time entry. Same semester/weekday
    resolution as resolve_current_course() above, but scoped to one course
    rather than "whatever's on right now" -- so it still finds today's slot
    even if the lecturer clicks Start Session a few minutes before/after the
    exact scheduled window (resolve_current_course's on-the-dot time filter
    would report no_class_now in that case).

    Returns the matching Timetable row, or None if there's no active
    semester or no slot for this course today.
    """
    from models import Timetable, Semester

    on_date = on_date or datetime.now()

    if semester is None:
        semester = Semester.query.filter_by(is_active=True).first()
    if semester is None:
        return None

    return (
        Timetable.query
        .filter(
            Timetable.course_id == course_id,
            Timetable.semester_id == semester.id,
            Timetable.day_of_week == on_date.weekday(),
        )
        .order_by(Timetable.start_time.asc(), Timetable.id.asc())
        .first()
    )

