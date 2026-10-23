import re
import bcrypt
from datetime import datetime, timedelta, timezone
from flask import session,redirect,url_for,flash
from functools import wraps
# Timetable columns hold campus wall-clock times, so "now" must be campus
# time too. datetime.now() is UTC on Render. See campus_time.py.
from campus_time import campus_now


# The only levels the school runs. Stored as the bare number ("400", never
# "400L") -- the HOD pages already append the "L" when displaying, so a
# stored "400L" rendered as "400LL" and split the roster's level filter in
# two. Student.level stays a String column; this tuple is what keeps it clean.
VALID_LEVELS = ('100', '200', '300', '400', '500')


def normalize_level(raw):
    """Canonical form of a typed level, or None if it isn't a real level.

    Accepts the spellings admins actually type -- "400", "400L", "400 l",
    " 400 " -- and returns "400". Anything outside VALID_LEVELS ("1000",
    "40", "Year 4") returns None so the caller can reject it rather than
    store it. Used by both the Add Student form and the CSV bulk enroll; the
    CSV never passes through the form's dropdown, so the server check is the
    one that actually guarantees clean data.
    """
    if raw is None:
        return None
    value = re.sub(r'\s+', '', str(raw)).upper()
    if value.endswith('L'):
        value = value[:-1]
    return value if value in VALID_LEVELS else None

#it finally worked !!!!!!!!!
def course_level(course_code):
    """A course's level read from its code: the first digit of the number is
    the level ("MCT401" -> "400", "GST 212" -> "200", "XYZ-SAM101" -> "100").
    None when the code doesn't follow that rule ("PROJ", "MCT901").

    Courses have no level column -- only students do. Every course code the
    school issues follows this convention, so reading it beats a column
    admins would have to fill in and keep correct. Used by the timetable
    page's department/level view.
    """
    match = re.search(r'\d', course_code or '')
    level = f"{match.group()}00" if match else None
    return level if level in VALID_LEVELS else None


def login_required(role):
    """`role` accepts either a single role string (the common case) or an
    iterable of roles -- the latter is for routes an HOD-who's-also-a-
    Lecturer needs to reach (e.g. lecturer.dashboard accepts
    ('lecturer', 'hod') so someone holding both profiles can manage their
    courses without a second login/account)."""
    allowed_roles = {role} if isinstance(role, str) else set(role)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access that page.', 'error')
                return redirect(url_for('auth.login'))
            if session.get('role') not in allowed_roles:
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)
        return wrapper
    return decorator


MIN_PASSWORD_LENGTH = 6


def new_password_problem(user, new_password):
    """Why `new_password` can't replace `user`'s password, or None if it can.

    Shared by the web form (blueprints/auth.py) and the app
    (api/auth.py), so both refuse the same things:
      * shorter than MIN_PASSWORD_LENGTH;
      * the username -- for a student that's the matric number, which is
        also the first password, so the forced change could be "passed" by
        typing the same thing again and the account stayed guessable;
      * the password they already have, for the same reason.
    """
    if not isinstance(new_password, str) or len(new_password) < MIN_PASSWORD_LENGTH:
        return f'Password must be at least {MIN_PASSWORD_LENGTH} characters long.'
    if new_password.strip().lower() == (user.username or '').strip().lower():
        return 'Your new password must be different from your username or matric number.'
    if bcrypt.checkpw(new_password.encode('utf-8'), user.password_hash.encode('utf-8')):
        return 'Your new password must be different from your current one.'
    return None


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


def resolve_current_course(semester=None, at=None, course_ids=None):
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

    course_ids limits the search to those courses -- the admin timetable's
    department/level view asks "what's on now for Mechatronics 400", since
    campus-wide there can be dozens of classes at once.
    """
    from models import Timetable, Semester

    now = at or campus_now()

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
            Timetable.is_published.is_(True),  # a draft isn't "happening now"
        )
        .order_by(Timetable.start_time.asc(), Timetable.id.asc())
    )
    if course_ids is not None:
        candidates = candidates.filter(Timetable.course_id.in_(course_ids))
    candidates = candidates.all()
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
        'lecturer': entry.course.lecturer_summary,  # 'Dr A + 2 more'
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
    be late against, so this always returns 'present'. Compares naive
    CAMPUS wall-clock time, because planned_start is one. This used to use
    datetime.now(), which is UTC on Render -- an hour behind Lagos -- so every
    late cutoff was effectively an hour later than the timetable said.
    """
    if session.planned_start is None:
        return 'present'

    now = at or campus_now()
    session_date = session.session_date or now.date()
    cutoff = datetime.combine(session_date, session.planned_start) + timedelta(minutes=LATE_GRACE_MINUTES)
    return 'late' if now > cutoff else 'present'


def students_not_checked_in(session):
    """Enrolled students with no attendance record for this session yet,
    sorted by name -- the list a lecturer picks from to mark someone present
    by hand. Nothing in the system writes 'absent' rows, so "no record" is
    exactly "hasn't been marked".
    """
    from models import Student, Enrollment, Attendance

    recorded = Attendance.query.with_entities(Attendance.student_id)\
        .filter(Attendance.session_id == session.id)
    return (
        Student.query
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.course_id == session.course_id,
                # A suspended, expelled, ... student isn't expected in class.
                Student.status == 'active',
                ~Student.id.in_(recorded))
        .order_by(Student.full_name)
        .all()
    )


# ---- The attendance rule -------------------------------------------------
# One definition, used by every page that shows an attendance percentage:
# the same as the course register lecturers download for exam eligibility
# (build_course_register_csv).
#
#   * a class counts as HELD once it has finished (Session.is_active False).
#     A running class isn't held yet: counting it made a student who hadn't
#     tapped in yet look lower in the app than on the register;
#   * a student ATTENDED if marked present or late. Excused and absent
#     don't count.
#
# Until 2026-10-15 eight places computed this, with three different rules
# (all sessions or finished only; every attendance row or present/late),
# so the student app, the HOD pages, the lecturer pages, Reports and the
# register could each show a different number for the same student. Each
# helper is one grouped query for any number of courses.

ATTENDED_STATUSES = ('present', 'late')


def held_sessions(course_ids):
    """{course_id: classes held (finished)}."""
    from models import db, Session as SessionModel
    if not course_ids:
        return {}
    return dict(db.session.query(SessionModel.course_id, db.func.count(SessionModel.id))
                .filter(SessionModel.course_id.in_(list(course_ids)),
                        SessionModel.is_active.is_(False))
                .group_by(SessionModel.course_id))


def attended_by_course(course_ids):
    """{course_id: attendances in held classes, all students together}."""
    from models import db, Session as SessionModel, Attendance
    if not course_ids:
        return {}
    return dict(db.session.query(SessionModel.course_id, db.func.count(Attendance.id))
                .join(Attendance, Attendance.session_id == SessionModel.id)
                .filter(SessionModel.course_id.in_(list(course_ids)),
                        SessionModel.is_active.is_(False),
                        Attendance.status.in_(ATTENDED_STATUSES))
                .group_by(SessionModel.course_id))


def attended_by_session(course_ids):
    """{session_id: attendances} for every held class of these courses. A
    held class nobody attended is absent from the dict (read it with
    .get(id, 0)). For per-class trends (lecturer analytics, web and app),
    which each had their own copy of this query, the web page one per
    course."""
    from models import db, Session as SessionModel, Attendance
    if not course_ids:
        return {}
    return dict(db.session.query(Attendance.session_id, db.func.count(Attendance.id))
                .join(SessionModel, Attendance.session_id == SessionModel.id)
                .filter(SessionModel.course_id.in_(list(course_ids)),
                        SessionModel.is_active.is_(False),
                        Attendance.status.in_(ATTENDED_STATUSES))
                .group_by(Attendance.session_id))


def attended_by_student(course_ids, student_ids=None):
    """{(student_id, course_id): held classes attended}. student_ids limits
    it to those students (one student's dashboard); None means everyone."""
    from models import db, Session as SessionModel, Attendance
    if not course_ids:
        return {}
    q = (db.session.query(Attendance.student_id, SessionModel.course_id, db.func.count(Attendance.id))
         .join(SessionModel, Attendance.session_id == SessionModel.id)
         .filter(SessionModel.course_id.in_(list(course_ids)),
                 SessionModel.is_active.is_(False),
                 Attendance.status.in_(ATTENDED_STATUSES)))
    if student_ids is not None:
        q = q.filter(Attendance.student_id.in_(list(student_ids)))
    return {(sid, cid): n for sid, cid, n in q.group_by(Attendance.student_id, SessionModel.course_id)}


def course_attendance(course_ids):
    """{course_id: {'enrolled', 'held', 'attended', 'pct'}} -- a course's
    average: attendances / (classes held x students enrolled). pct is 0
    before anything has been held or anyone has enrolled. Four grouped
    queries whatever the number of courses (Reports used to run three per
    course: 1,500 for 500 courses)."""
    from models import db, Enrollment
    course_ids = list(course_ids)
    if not course_ids:
        return {}
    enrolled = dict(db.session.query(Enrollment.course_id, db.func.count(Enrollment.id))
                    .filter(Enrollment.course_id.in_(course_ids))
                    .group_by(Enrollment.course_id))
    held = held_sessions(course_ids)
    attended = attended_by_course(course_ids)
    out = {}
    for cid in course_ids:
        e, h, a = enrolled.get(cid, 0), held.get(cid, 0), attended.get(cid, 0)
        out[cid] = {'enrolled': e, 'held': h, 'attended': a,
                    'pct': round(a / (h * e) * 100, 1) if h and e else 0}
    return out


def student_course_attendance(student):
    """[{'course', 'attended', 'total', 'pct'}, ...] for every course the
    student is registered for. Shared by the app dashboard (api/student.py)
    and the student web portal (blueprints/student.py), which each had a
    copy.

    PERF: both copies ran two counting queries per course (plus, on the web,
    one more to load each course's lecturer) -- about 13 trips to the
    database for six courses, on every dashboard open. Now three queries
    whatever the course count.

    Uses the attendance rule above (held = finished, attended = present or
    late), so a student sees the same percentage as their register. It used
    to count every session, a running one too, and every attendance row.
    """
    from sqlalchemy.orm import joinedload
    from models import Course, Enrollment

    # This semester's courses only (current_courses): the dashboards that
    # call this show "now", and old enrolments never expire.
    courses = (current_courses(Course.query
                               .join(Enrollment, Enrollment.course_id == Course.id)
                               .filter(Enrollment.student_id == student.id))
               .options(joinedload(Course.lecturer))
               .all())
    course_ids = [c.id for c in courses]
    if not course_ids:
        return []

    totals = held_sessions(course_ids)
    attended = attended_by_student(course_ids, [student.id])

    rows = []
    for course in courses:
        total = totals.get(course.id, 0)
        count = attended.get((student.id, course.id), 0)
        rows.append({
            'course': course,
            'attended': count,
            'total': total,
            'pct': round((count / total * 100) if total else 0, 1),
        })
    return rows


def teaches(lecturer):
    """SQL condition: the course is taught by this lecturer -- as its
    coordinator (courses.lecturer_id) or as a co-lecturer (course_lecturers).

    The ONE definition of "this lecturer's course". There used to be about
    thirty copies of `lecturer_id=lecturer.id` across the app and web routes;
    they all go through this now, so co-lecturers get the same access as the
    coordinator everywhere at once and the copies can't drift apart.
    """
    from sqlalchemy import or_, select
    from models import Course, course_lecturers
    return or_(
        Course.lecturer_id == lecturer.id,
        Course.id.in_(select(course_lecturers.c.course_id)
                      .where(course_lecturers.c.lecturer_id == lecturer.id)),
    )


# ---- the current semester -----------------------------------------------------
# Enrolments and published timetables never expire, so screens that show
# "now" -- a student's Today/Week/Dashboard, a lecturer's courses and week,
# an HOD's department figures -- must ask for the current semester
# explicitly, or after a changeover they mix last year with this year
# (two MCT401s, last year's classes in today's list). History screens
# (attendance history, session history, reports, exports) deliberately
# don't use these. (2026-10-18.)

def current_semester():
    """The active semester, or None."""
    from models import Semester
    return Semester.query.filter_by(is_active=True).first()


def current_course_filter(semester=None):
    """A Course filter for "this semester": its courses plus those with no
    semester, which belong to every semester (the timetable's rule).

    None when there is no active semester -- callers then don't filter at
    all. A missing active semester is an admin setup gap; showing everything,
    as before, beats blanking every student's and lecturer's app."""
    from models import Course
    from sqlalchemy import or_
    semester = semester or current_semester()
    if semester is None:
        return None
    return or_(Course.semester_id == semester.id, Course.semester_id.is_(None))


def in_current_semester(course, semester=None):
    """The same rule as current_course_filter, for one loaded course."""
    semester = semester or current_semester()
    return semester is None or course.semester_id is None or course.semester_id == semester.id


def current_courses(query, semester=None):
    """`query` (of Course) narrowed to the current semester, if there is one."""
    condition = current_course_filter(semester)
    return query if condition is None else query.filter(condition)


def current_slot_filter(semester=None):
    """A Timetable filter for this semester's slots, or None (no filter).

    Slots are matched on their OWN semester, not their course's: a course
    with no semester (GST212) has a separate set of slots each semester,
    and only the current ones are this week's classes."""
    from models import Timetable
    semester = semester or current_semester()
    return None if semester is None else (Timetable.semester_id == semester.id)


def courses_taught_by(lecturer):
    """Query of every course this lecturer teaches (coordinator or co-)."""
    from models import Course
    return Course.query.filter(teaches(lecturer))


def taught_course(lecturer, course_id):
    """The course if this lecturer teaches it, else None. The ownership
    check every lecturer route runs before showing or changing anything."""
    from models import Course
    return courses_taught_by(lecturer).filter(Course.id == course_id).first()


def _lock_owned_course(lecturer, course_id):
    """The lecturer's own course, row-locked until the caller commits, or None.

    The lock (SELECT ... FOR UPDATE on MySQL) is what makes "is a session
    already running?" and "start one" a single step. Two Start requests
    sent together -- a double tap on a slow connection -- used to both see
    no active session and both create one; ending the class then closed only
    the first, leaving the other open and accepting check-ins. Now the second
    request waits for the first to commit and then sees its session.
    (SQLite, used by the tests, ignores FOR UPDATE.)
    """
    from models import Course
    return (courses_taught_by(lecturer)
            .filter(Course.id == course_id)
            .with_for_update()
            .first())


# Sessions only end when a lecturer presses End. One forgotten on Monday
# stayed "active" into Tuesday: dashboards showed it live, Start refused
# ("already active"), check-in refused it (it isn't today's), and it never
# counted as held, so nobody's percentage included it. Ending leftovers
# from earlier days fixes all four in one place, instead of a date filter
# on every query that reads is_active.
_STALE_SWEEP_EVERY = timedelta(minutes=10)
_last_stale_sweep = None


def close_stale_sessions(force=False):
    """End every session still open from an earlier campus day. Returns how
    many were closed.

    Called before each request (app.py), but does real work at most every
    _STALE_SWEEP_EVERY per process -- one indexed UPDATE, usually matching
    nothing. Two threads racing past the time check just run the same
    harmless UPDATE twice. stop_time stays empty: nobody knows when the
    class really ended, and the session page then shows no "Ended" time.
    """
    global _last_stale_sweep
    from models import db, Session as SessionModel
    from campus_time import campus_today

    now = datetime.now(timezone.utc)
    if not force and _last_stale_sweep and now - _last_stale_sweep < _STALE_SWEEP_EVERY:
        return 0
    _last_stale_sweep = now

    closed = (SessionModel.query
              .filter(SessionModel.is_active.is_(True),
                      SessionModel.session_date < campus_today())
              .update({'is_active': False}, synchronize_session=False))
    db.session.commit()
    return closed


def start_class_session(lecturer, course_id, planned_start=None, planned_end=None, room=None):
    """Start a session for one of the lecturer's courses.

    Shared by the lecturer app (api/lecturer.py) and the web portal
    (blueprints/lecturer.py), which each had their own copy. Returns
    (outcome, session): 'started', 'already_active' (session = the running
    one), 'past_semester' (session = None; the course belongs to another
    semester) or 'not_found' (no such course, or not one they teach). Any
    of the course's lecturers can start it; the session records which one.

    With no planned times given, uses today's timetable slot, so the late
    cut-off still has a scheduled start to work from.

    `room` is where the class is actually held, when the lecturer says so
    (a last-minute change); otherwise the slot's room. Readers in another
    room are flagged or refused against it (terminal_rooms.py).
    """
    from models import db, Session as SessionModel
    from campus_time import campus_today

    course = _lock_owned_course(lecturer, course_id)
    if course is None:
        db.session.rollback()  # release the (empty) lock
        return 'not_found', None

    # Last year's MCT401 is still "a course they teach", but a class started
    # on it would take check-ins from last year's class list and file the
    # attendance under the wrong semester.
    if not in_current_semester(course):
        db.session.rollback()
        return 'past_semester', None

    # A leftover from an earlier day isn't "already running"; end it here,
    # in this transaction, so Start works even before the next sweep. (Not
    # close_stale_sessions(): its commit would release the course lock.)
    (SessionModel.query
     .filter(SessionModel.course_id == course_id, SessionModel.is_active.is_(True),
             SessionModel.session_date < campus_today())
     .update({'is_active': False}, synchronize_session=False))

    running = SessionModel.query.filter_by(course_id=course_id, is_active=True).first()
    if running:
        db.session.rollback()
        return 'already_active', running

    # Always find today's slot: it says which timetabled class this is
    # (timetable_id) and its room, even when times were typed. The web form
    # always sends times (pre-filled from the slot), so web-started classes
    # used to record no slot at all. Typed times still win over the slot's.
    slot = resolve_timetable_slot_for_course(course_id)
    if slot and planned_start is None and planned_end is None:
        planned_start, planned_end = slot.start_time, slot.end_time

    new_session = SessionModel(
        course_id=course_id,
        session_date=campus_today(),  # campus date; start_time stays UTC
        is_active=True,
        start_time=datetime.now(timezone.utc).time(),
        planned_start=planned_start,
        planned_end=planned_end,
        # Which timetable slot this class is, so the admin dashboard can
        # tell a course's lecture from its tutorial on the same day. None
        # for a class with no slot today.
        timetable_id=slot.id if slot else None,
        room=(room or '').strip()[:50] or (slot.room if slot else None),
        # Which of the course's lecturers ran this class.
        started_by=lecturer.user_id,
    )
    db.session.add(new_session)
    db.session.commit()
    return 'started', new_session


def end_class_session(lecturer, course_id):
    """End every running session for one of the lecturer's courses.

    Returns (outcome, session): 'ended' (session = the most recent one
    closed), 'none_active' or 'not_found'. Closes ALL running sessions, not
    just the first: if a duplicate ever exists (see _lock_owned_course), one
    End must not leave the other open.
    """
    from models import db, Session as SessionModel

    if _lock_owned_course(lecturer, course_id) is None:
        db.session.rollback()
        return 'not_found', None

    running = (SessionModel.query
               .filter_by(course_id=course_id, is_active=True)
               .order_by(SessionModel.id.desc())
               .all())
    if not running:
        db.session.rollback()
        return 'none_active', None

    stopped_at = datetime.now(timezone.utc).time()
    for s in running:
        s.is_active = False
        s.stop_time = stopped_at
    db.session.commit()
    return 'ended', running[0]


def mark_student_present(session, student_id, marker_user):
    """A lecturer marking a student present by hand. Shared by the mobile
    API and the web dashboard so both apply the same rules. The caller has
    already checked that `marker_user` owns the session's course.

    This is the fallback for a student whose phone can't check in (no NFC,
    no strong biometric, or a security key in its 24-hour wait), so it
    deliberately differs from a self check-in in three ways:
      * It works on ended sessions too, so a lecturer can correct the
        register after class.
      * Status is always 'present', never computed 'late': the lecturer
        often marks a student well after they actually arrived, and the
        time of marking says nothing about the time of arrival.
      * It records method='manual' and who marked it, because there is no
        device evidence behind it -- only the lecturer's word.

    Returns 'marked', 'already_marked', or 'not_enrolled'.
    """
    from sqlalchemy.exc import IntegrityError
    from models import db, Student, Enrollment, Attendance
    from push_notifications import send_push_notification

    enrolled = Enrollment.query.filter_by(
        student_id=student_id, course_id=session.course_id
    ).first()
    if not enrolled:
        return 'not_enrolled'

    if Attendance.query.filter_by(session_id=session.id, student_id=student_id).first():
        return 'already_marked'

    db.session.add(Attendance(
        student_id=student_id,
        session_id=session.id,
        status='present',
        method='manual',
        marked_by=marker_user.id,
    ))
    try:
        db.session.commit()
    except IntegrityError:
        # Lost a race with the student's own check-in (or a second click);
        # uq_attendance_student_session let exactly one row in, which is
        # the outcome we wanted anyway.
        db.session.rollback()
        if Attendance.query.filter_by(session_id=session.id, student_id=student_id).first():
            return 'already_marked'
        raise

    student = db.session.get(Student, student_id)
    course = session.course
    send_push_notification(
        student.user,
        'attendance_marked',
        'Attendance Recorded',
        f"Your lecturer marked you present for {course.course_code}." if course
        else "Your lecturer marked you present.",
        data={'session_id': session.id, 'course_id': session.course_id},
    )
    return 'marked'


def pending_offline_taps(session):
    """Offline taps for this session still waiting on the lecturer, oldest
    first. Leaves out students who already have attendance (they checked in
    live, or were marked by hand, after the tap was queued) -- accepting
    those would do nothing, so showing them would only be noise. The row
    itself is settled as 'superseded' if the lecturer acts on it anyway.
    """
    from models import OfflineCheckinLog, Attendance

    recorded = Attendance.query.with_entities(Attendance.student_id)\
        .filter(Attendance.session_id == session.id)
    return (
        OfflineCheckinLog.query
        .filter(OfflineCheckinLog.session_id == session.id,
                OfflineCheckinLog.status == 'pending_verification',
                ~OfflineCheckinLog.student_id.in_(recorded))
        .order_by(OfflineCheckinLog.captured_at)
        .all()
    )


def review_offline_tap(session, log_id, reviewer_user, accept, notify=True):
    """A lecturer accepting or rejecting one tap a terminal read while it was
    offline. Shared by the mobile API and the web dashboard. The caller has
    already checked that `reviewer_user` owns the session's course.

    Differences from mark_student_present, and why:
      * The time of the tap is known. The terminal read a signed beacon and
        the server derived captured_at from it, so time_in is that moment
        and status is computed present/late against it, exactly as a live
        tap would have been. A hand mark knows neither.
      * method='offline', not 'manual': a genuine signed read of the
        student's phone stands behind it, which is stronger evidence than a
        lecturer's word alone. marked_by still records who accepted it.

    `notify=False` lets accept_all_offline_taps skip the per-student push
    and send nothing until the batch is done.

    Returns 'accepted', 'rejected', 'already_marked' (attendance already
    exists; the row is settled as superseded), 'not_enrolled' (student
    dropped the course; the row is rejected), 'already_reviewed', or
    'not_found'.
    """
    from sqlalchemy.exc import IntegrityError
    from models import db, Enrollment, Attendance, OfflineCheckinLog, Terminal
    from campus_time import to_campus

    log = OfflineCheckinLog.query.filter_by(id=log_id, session_id=session.id).first()
    if not log:
        return 'not_found'
    if log.status != 'pending_verification':
        return 'already_reviewed'

    def settle(status, reason=None):
        log.status = status
        log.reason = reason
        log.reviewed_by = reviewer_user.id
        log.reviewed_at = datetime.now(timezone.utc)

    if not accept:
        settle('rejected', 'Rejected by lecturer')
        db.session.commit()
        return 'rejected'

    if Attendance.query.filter_by(session_id=session.id, student_id=log.student_id).first():
        settle('superseded', 'Already had attendance')
        db.session.commit()
        return 'already_marked'

    # Enrolment is checked now, not at sync time: a student who dropped the
    # course since the tap must not land on its register.
    if not Enrollment.query.filter_by(student_id=log.student_id,
                                      course_id=session.course_id).first():
        settle('rejected', 'Not enrolled in this course')
        db.session.commit()
        return 'not_enrolled'

    # captured_at is stored as naive UTC; compute_attendance_status compares
    # naive campus wall-clock time.
    tapped_campus = to_campus(log.captured_at).replace(tzinfo=None)
    db.session.add(Attendance(
        student_id=log.student_id,
        session_id=session.id,
        time_in=log.captured_at,
        status=compute_attendance_status(session, at=tapped_campus),
        method='offline',
        marked_by=reviewer_user.id,
        # The reader that uploaded it, and its room check from sync time.
        terminal_id=db.session.query(Terminal.id).filter_by(code=log.terminal_id).scalar(),
        wrong_room=log.wrong_room,
    ))
    settle('accepted')
    try:
        db.session.commit()
    except IntegrityError:
        # Lost a race with a live check-in or a hand mark for the same
        # student; uq_attendance_student_session kept exactly one row.
        db.session.rollback()
        log = db.session.get(OfflineCheckinLog, log_id)
        if log.status == 'pending_verification':
            settle('superseded', 'Already had attendance')
            db.session.commit()
        return 'already_marked'

    if notify:
        _notify_offline_tap_accepted(session, log.student)
    return 'accepted'


def _notify_offline_tap_accepted(session, student):
    from push_notifications import send_push_notification

    course = session.course
    send_push_notification(
        student.user,
        'attendance_marked',
        'Attendance Recorded',
        f"Your tap for {course.course_code} while the terminal was offline was accepted."
        if course else "Your tap while the terminal was offline was accepted.",
        data={'session_id': session.id, 'course_id': session.course_id},
    )


def accept_all_offline_taps(session, reviewer_user):
    """Accept every pending offline tap for the session in one go -- for a
    class whose terminal was offline, where checking 30+ taps one by one
    isn't realistic. Each tap still goes through review_offline_tap, so the
    enrolment and already-marked rules apply per student.

    Bulk acceptance is safe to offer because every tap is already a
    signature-verified read bound to this session: the beacon could only be
    minted while this session was live, after the student's own biometric
    check. The lecturer is confirming "the terminal was down", not vouching
    for each face.

    Returns a dict of outcome -> count.
    """
    counts = {}
    accepted_students = []
    for log in pending_offline_taps(session):
        student = log.student
        outcome = review_offline_tap(session, log.id, reviewer_user, accept=True, notify=False)
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == 'accepted':
            accepted_students.append(student)

    # Pushes go out after every row is committed, so a slow or failing
    # notification can't leave the batch half-applied.
    for student in accepted_students:
        _notify_offline_tap_accepted(session, student)
    return counts


def announcement_user_ids(announcement):
    """User ids of every student an Announcement applies to. Mirrors
    get_student_announcements() in api/student.py, which resolves the
    opposite direction (student -> which announcements apply to them); keep
    both in sync if this scoping rule ever changes.

    Selects only Student.user_id: the old version loaded every Student row
    and then each student's User one query at a time, just to get this id.
    """
    from models import db, Student, Enrollment

    query = db.session.query(Student.user_id)
    if announcement.scope == 'university':
        pass
    elif announcement.scope == 'department' and announcement.department_id is not None:
        query = query.filter(Student.department_id == announcement.department_id)
    elif announcement.scope == 'course' and announcement.course_id is not None:
        query = (query.join(Enrollment, Enrollment.student_id == Student.id)
                 .filter(Enrollment.course_id == announcement.course_id))
    else:
        return []
    return [user_id for (user_id,) in query]


def notify_announcement(announcement):
    """Notify every student an announcement reaches, in bulk. Called after
    the announcement is committed, by the admin dashboard, the lecturer web
    portal AND the lecturer app -- the app's route used to skip this
    entirely, so announcements posted from a phone reached nobody's
    notifications."""
    from push_notifications import notify_users

    body = announcement.body
    preview = body if len(body) <= 120 else body[:117] + '...'
    notify_users(announcement_user_ids(announcement), 'announcement',
                 announcement.title, preview,
                 data={'announcement_id': announcement.id})


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

    A course can meet more than once a day (a lecture at 09:00, a tutorial
    at 14:00). It used to return the day's FIRST slot regardless of the
    time, so starting the 14:00 tutorial gave the session 09:00 planned
    times -- and the late cut-off is worked out from planned_start. Now it
    returns the slot running at `on_date`'s time, else the next one today,
    else the last one (a class started after its slot ended).

    Returns the matching Timetable row, or None if there's no active
    semester or no slot for this course today.
    """
    from models import Timetable, Semester

    on_date = on_date or campus_now()

    if semester is None:
        semester = Semester.query.filter_by(is_active=True).first()
    if semester is None:
        return None

    slots = (
        Timetable.query
        .filter(
            Timetable.course_id == course_id,
            Timetable.semester_id == semester.id,
            Timetable.day_of_week == on_date.weekday(),
            Timetable.is_published.is_(True),  # drafts don't set planned times
        )
        .order_by(Timetable.start_time.asc(), Timetable.id.asc())
        .all()
    )
    if not slots:
        return None
    # A plain date (no time of day) can't choose between them: first slot.
    if not isinstance(on_date, datetime):
        return slots[0]
    now = on_date.time()
    return next((s for s in slots if s.end_time > now), slots[-1])



# Minimum attendance % to sit the exam. Single knob for the per-course
# register export (web + mobile API) -- change here, not in the routes.
EXAM_ELIGIBILITY_THRESHOLD = 75


def _csv_safe(value):
    """Neutralise spreadsheet formula injection: a name/matric starting with
    = + - @ (or tab/CR) would be executed by Excel when the CSV is opened, so
    prefix it with a quote to force it to plain text."""
    text = '' if value is None else str(value)
    if text and text[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + text
    return text


def build_course_register_csv(course):
    """
    Per-course attendance register as CSV text -- one row per enrolled
    student, one column per completed session, plus totals and an exam
    eligibility flag. Shared by the web route and the mobile API so the two
    downloads can't drift apart.

    Starts from Enrollment (not Attendance) so students who never tapped in
    still get a row, all-absent. Only completed sessions (is_active=False)
    count, matching the analytics endpoint -- an open session would
    otherwise make everyone look absent. Attended = present + late.
    Three bulk queries total, no per-student queries (connection safety).
    """
    import csv
    import io
    from models import Session as SessionModel, Attendance, Student, Enrollment

    sessions = (
        SessionModel.query
        .filter_by(course_id=course.id, is_active=False)
        .order_by(SessionModel.session_date.asc(), SessionModel.id.asc())
        .all()
    )
    students = (
        Student.query
        .join(Enrollment, Enrollment.student_id == Student.id)
        .filter(Enrollment.course_id == course.id)
        .order_by(Student.matric_number.asc())
        .all()
    )

    # (student_id, session_id) -> status
    status_by_key = {}
    if sessions:
        rows = (
            Attendance.query
            .filter(Attendance.session_id.in_([s.id for s in sessions]))
            .with_entities(Attendance.student_id, Attendance.session_id, Attendance.status)
            .all()
        )
        status_by_key = {(r[0], r[1]): r[2] for r in rows}

    symbol = {'present': 'P', 'late': 'L', 'excused': 'E', 'absent': 'A'}
    total = len(sessions)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f'{course.course_code} - {course.course_title}'])
    writer.writerow([f'Eligibility threshold: {EXAM_ELIGIBILITY_THRESHOLD}%',
                     'P=Present L=Late E=Excused A=Absent'])
    writer.writerow(
        ['S/N', 'Matric Number', 'Full Name', 'Level']
        + [s.session_date.strftime('%d-%b-%Y') if s.session_date else f'Session {s.id}' for s in sessions]
        + ['Attended', 'Total Sessions', 'Attendance (%)', 'Exam Eligible']
    )

    for index, student in enumerate(students, start=1):
        marks = []
        attended = 0
        for s in sessions:
            status = status_by_key.get((student.id, s.id))
            marks.append(symbol.get(status, 'A'))
            if status in ATTENDED_STATUSES:
                attended += 1
        pct = round(attended / total * 100, 1) if total else 0
        eligible = 'YES' if total and pct >= EXAM_ELIGIBILITY_THRESHOLD else 'NO'
        writer.writerow(
            [index, _csv_safe(student.matric_number), _csv_safe(student.full_name), _csv_safe(student.level)]
            + marks + [attended, total, pct, eligible]
        )

    return output.getvalue()
