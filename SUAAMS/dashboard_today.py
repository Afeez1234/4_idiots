"""What the admin dashboard shows: is today's teaching actually happening?

The dashboard used to show totals (students, lecturers, courses) and an
all-time department rate. None of that says whether the 10:00 class in LT 3
has started. This module answers that from data the system already has:
today's published timetable slots, the sessions lecturers started, and the
check-ins under them.

Every function here runs a FIXED number of queries (GROUP BY, never a query
per slot, course or department), so the page costs the same with 5 classes
or 500. tests/test_dashboard_today.py pins that.

Times: timetable columns are campus wall-clock times, compared with
campus_now(); stored moments (Attendance.time_in, AuditLog.created_at) are
UTC. See campus_time.py.
"""
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from campus_time import campus_now, campus_tz
from utils import ATTENDED_STATUSES, held_sessions, attended_by_course
from models import (
    db, Attendance, AuditLog, Course, Department, Enrollment, Session, Timetable,
)

# A class with no session this long after its start time is LATE: the
# dashboard raises a banner with a "Notify lecturer" button. Before that it
# is only "due" -- lecturers routinely open the terminal a few minutes in.
LATE_AFTER = timedelta(minutes=30)

# Attendance statuses that mean the student was there: the shared rule.
PRESENT = ATTENDED_STATUSES

# The reminder's audit action; the banner reads it back to show "Reminded
# 10:12", so two admins don't both send one.
REMIND_ACTION = 'timetable.remind'


def _utc_start_of(day):
    """Campus midnight of `day`, as naive UTC (how created_at is stored)."""
    local = datetime.combine(day, time.min, tzinfo=campus_tz())
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _count_by(column, ids, *filters):
    """{value of column: row count} for rows whose column is in ids."""
    if not ids:
        return {}
    return dict(db.session.query(column, func.count())
                .filter(column.in_(ids), *filters).group_by(column))


def _status(slot, session, now):
    if session is not None:
        return 'live' if session.is_active else 'ended'
    start = datetime.combine(now.date(), slot.start_time)
    end = datetime.combine(now.date(), slot.end_time)
    if now < start:
        return 'upcoming'
    if now >= end:
        return 'missed'
    return 'late' if now >= start + LATE_AFTER else 'due'


def _match_sessions(slots, sessions):
    """{slot.id: session}. A session belongs to at most one slot.

    Sessions started since the dashboard was built carry timetable_id.
    Older ones are matched on course + planned_start, which
    start_class_session copied from the slot."""
    matched, used = {}, set()
    for slot in slots:
        for s in sessions:
            if s.id not in used and s.timetable_id == slot.id:
                matched[slot.id] = s
                used.add(s.id)
                break
    for slot in slots:
        if slot.id in matched:
            continue
        for s in sessions:
            if (s.id not in used and s.timetable_id is None and s.course_id == slot.course_id
                    and s.planned_start == slot.start_time):
                matched[slot.id] = s
                used.add(s.id)
                break
    return matched


def today(semester, now=None):
    """Everything the dashboard's "today" parts need, in one dict.

    slots: one row per published timetable slot today, earliest first, each
      {slot, course, status, session, present, enrolled, reminded_at}.
    alerts: the late slots (no session 30+ minutes after the start).
    live: the sessions running now (timetabled or not).
    checkins: {count, expected, pct, by_method} for today.
    """
    now = now or campus_now()
    day = now.date()

    slots = []
    if semester is not None:
        # The coordinator is loaded with the course because the classes
        # table names the lecturer on every row; lazily that was one query
        # per lecturer. Co-lecturers are selectin on Course already.
        slots = (Timetable.query
                 .options(joinedload(Timetable.course).joinedload(Course.lecturer))
                 .filter(Timetable.semester_id == semester.id,
                         Timetable.day_of_week == day.weekday(),
                         Timetable.is_published.is_(True))
                 .order_by(Timetable.start_time, Timetable.id)
                 .all())

    # Every session today, not only timetabled ones: an ad hoc class still
    # counts as live and its check-ins still count.
    sessions = (Session.query.options(joinedload(Session.course))
                .filter(Session.session_date == day).order_by(Session.id).all())
    present = _count_by(Attendance.session_id, [s.id for s in sessions],
                        Attendance.status.in_(PRESENT))
    course_ids = {s.course_id for s in slots} | {s.course_id for s in sessions}
    enrolled = _count_by(Enrollment.course_id, list(course_ids))
    reminded = {}
    if slots:
        for entity_id, at in (db.session.query(AuditLog.entity_id, func.max(AuditLog.created_at))
                              .filter(AuditLog.action == REMIND_ACTION,
                                      AuditLog.entity_id.in_([str(s.id) for s in slots]),
                                      AuditLog.created_at >= _utc_start_of(day))
                              .group_by(AuditLog.entity_id)):
            reminded[int(entity_id)] = at

    matched = _match_sessions(slots, sessions)
    slot_of = {session.id: slot for slot in slots
               for session in [matched.get(slot.id)] if session is not None}
    rows = []
    for slot in slots:
        session = matched.get(slot.id)
        rows.append({
            'slot': slot,
            'course': slot.course,
            'status': _status(slot, session, now),
            'session': session,
            'present': present.get(session.id, 0) if session else None,
            'enrolled': enrolled.get(slot.course_id, 0),
            'reminded_at': reminded.get(slot.id),
        })

    count = sum(present.values())
    # Expected = everyone enrolled in each class that actually ran today.
    expected = sum(enrolled.get(s.course_id, 0) for s in sessions)
    by_method = dict(db.session.query(Attendance.method, func.count())
                     .join(Session, Attendance.session_id == Session.id)
                     .filter(Session.session_date == day, Attendance.status.in_(PRESENT))
                     .group_by(Attendance.method))
    return {
        'now': now,
        'slots': rows,
        'alerts': [r for r in rows if r['status'] == 'late'],
        # Room from the session, else from the slot it was matched to.
        'live': [{'session': s, 'room': s.room or (slot_of[s.id].room if s.id in slot_of else None)}
                 for s in sessions if s.is_active],
        'checkins': {
            'count': count,
            'expected': expected,
            'pct': round(count / expected * 100) if expected else None,
            # Method NULL = recorded before the column existed (see
            # Attendance.method): shown as "unknown", never guessed.
            'by_method': sorted(((m or 'unknown', n) for m, n in by_method.items()),
                                key=lambda pair: -pair[1]),
        },
    }


def department_rates(semester):
    """[{name, percentage}] for the active semester, best first.

    Per course: expected check-ins = its sessions x its enrolled students;
    a department's rate = its courses' check-ins / their expected, summed.
    The old version multiplied the DEPARTMENT's total sessions by its total
    enrollments, which counts every student in every course's sessions --
    a course with 10 sessions and 5 students next to one with 1 session and
    100 students expects 150 check-ins, not 11 x 105 = 1,155."""
    if semester is None:
        return []
    courses = (db.session.query(Course.id, Course.department_id, Department.name)
               .join(Department, Course.department_id == Department.id)
               .filter(Course.semester_id == semester.id).all())
    ids = [c.id for c in courses]
    # The shared attendance rule (utils): finished classes, present or late.
    # Counting today's running classes as held made every department dip
    # while classes were on.
    sessions = held_sessions(ids)
    enrolled = _count_by(Enrollment.course_id, ids)
    attended = attended_by_course(ids)
    totals = {}
    for course_id, _dept_id, name in courses:
        got, want = totals.get(name, (0, 0))
        totals[name] = (got + attended.get(course_id, 0),
                        want + sessions.get(course_id, 0) * enrolled.get(course_id, 0))
    rates = [{'name': name, 'percentage': round(got / want * 100, 1)}
             for name, (got, want) in totals.items() if want]
    return sorted(rates, key=lambda r: -r['percentage'])


def recent_checkins(limit=8):
    """The latest check-ins, with student, course and session loaded up
    front (the old feed ran two extra queries per row)."""
    return (Attendance.query
            .options(joinedload(Attendance.student),
                     joinedload(Attendance.session).joinedload(Session.course))
            .order_by(Attendance.time_in.desc(), Attendance.id.desc())
            .limit(limit).all())
