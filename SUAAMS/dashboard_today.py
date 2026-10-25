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
from terminal_rooms import class_room, normalize_room
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
    # timetable too: the door board reads a live class's slot for its end
    # time, which would otherwise be one lazy query per live class.
    sessions = (Session.query.options(joinedload(Session.course), joinedload(Session.timetable))
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
        # For door_board(): counts behind the rows, and the live sessions
        # no slot claimed (started outside the timetable).
        'present_by_session': present,
        'enrolled_by_course': enrolled,
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


# ---------------------------------------------------------------------------
# The door board (admin home, 2026-10-25): today's classes as rows, each
# with what its room's reader is showing. Built from today()'s dict and the
# list of readers, so it adds one query (the readers) to the page.
# ---------------------------------------------------------------------------

# Board groups, in the order they're shown.
BOARD_GROUPS = (
    ('needs', 'Needs you'),
    ('live', 'Live now'),
    ('due', 'Due now'),
    ('later', 'Later today'),
    ('ended', 'Ended'),
)


def _hhmm(t):
    return t.strftime('%H:%M') if t is not None else None


def _room_screens(data, now):
    """{normalized room: lines} for what each room's reader shows now,
    decided the way terminal_status.status_for() decides it (so the board
    and the door agree): the live class, else a timetabled class that
    hasn't started ("Not started yet"), else NO CLASS with the next one.
    Lines are the reader's own wording (oled_display.ino, oledDrawDoor)."""
    present, enrolled = data['present_by_session'], data['enrolled_by_course']
    live = {}
    for item in data['live']:
        s = item['session']
        live.setdefault(normalize_room(class_room(s) or item['room']), []).append(s)
    screens = {}
    rooms = set(live) | {normalize_room(r['slot'].room) for r in data['slots']}
    for room in rooms - {''}:
        if room in live:
            s = live[room][0]
            code = s.course.course_code if s.course else '?'
            more = len(live[room]) - 1
            end = s.planned_end or (s.timetable.end_time if s.timetable else None)
            lines = [code + (f'  +{more}' if more else ''),
                     f"{present.get(s.id, 0)} / {enrolled.get(s.course_id, 0)} checked in"]
            if end:
                lines.append(f'ends {_hhmm(end)}')
            screens[room] = {'state': 'lit', 'lines': lines}
            continue
        slots = [r for r in data['slots'] if normalize_room(r['slot'].room) == room]
        due = next((r for r in slots if r['session'] is None
                    and r['slot'].start_time <= now.time() < r['slot'].end_time), None)
        if due:
            screens[room] = {'state': 'dim', 'lines': [
                due['course'].course_code, 'Not started yet',
                f"{_hhmm(due['slot'].start_time)} - {_hhmm(due['slot'].end_time)}"]}
            continue
        nxt = next((r for r in slots if r['slot'].start_time > now.time()), None)
        screens[room] = {'state': 'dim', 'lines': (
            ['NO CLASS', f"Next: {nxt['course'].course_code} at {_hhmm(nxt['slot'].start_time)}"]
            if nxt else ['NO CLASS', 'Nothing else today'])}
    return screens


def _minutes(now, t):
    """Whole minutes from campus time-of-day t to now (negative if t is
    still to come)."""
    return int((datetime.combine(now.date(), now.time())
                - datetime.combine(now.date(), t)).total_seconds() // 60)


def door_board(data, terminals, online_within, now_utc=None):
    """Rows and groups for the door board.

    data: today()'s dict. terminals: every models.Terminal. online_within:
    how recently a reader must have been seen to count as online (the
    Terminals page's TERMINAL_ONLINE_WITHIN, so the two pages agree).

    Each row: {key, start, end, room, course, lecturer, status, session,
    present, enrolled, slot, reminded_at, reader, screen, group, reason}.
    reader is {'state': 'online'|'offline'|'disabled'|'none', 'terminal',
    'seen_ago'}; screen is _room_screens()'s entry or None (no reader).
    """
    now = data['now']
    now_utc = now_utc or datetime.now(timezone.utc).replace(tzinfo=None)

    readers = {}
    for t in terminals:
        room = normalize_room(t.room)
        # An active reader wins over a switched-off one in the same room.
        if room and (room not in readers or (t.is_active and not readers[room].is_active)):
            readers[room] = t

    def reader_for(room_key):
        t = readers.get(room_key)
        if t is None:
            return {'state': 'none', 'terminal': None, 'seen_ago': None}
        seen_ago = (now_utc - t.last_seen_at) if t.last_seen_at else None
        if not t.is_active:
            state = 'disabled'
        elif seen_ago is not None and seen_ago <= online_within:
            state = 'online'
        else:
            state = 'offline'
        return {'state': state, 'terminal': t, 'seen_ago': seen_ago}

    screens = _room_screens(data, now)
    present, enrolled = data['present_by_session'], data['enrolled_by_course']
    rows = []

    def add(key, start, end, room, course, status, session, slot=None, reminded_at=None, count=None):
        room_key = normalize_room(room)
        reader = reader_for(room_key) if room_key else {'state': 'none', 'terminal': None, 'seen_ago': None}
        happening = status in ('live', 'due', 'late')
        if status == 'late':
            group, reason = 'needs', 'late'
        elif happening and reader['state'] in ('offline', 'disabled'):
            group, reason = 'needs', 'reader'
        else:
            group = {'live': 'live', 'due': 'due', 'upcoming': 'later'}.get(status, 'ended')
            reason = None
        rows.append({
            'key': key, 'start': start, 'end': end, 'room': room, 'course': course,
            'lecturer': (course.lecturer_summary if course else None) or 'No lecturer assigned',
            'status': status, 'session': session, 'slot': slot, 'reminded_at': reminded_at,
            'present': count, 'enrolled': enrolled.get(course.id, 0) if course else 0,
            'reader': reader, 'screen': screens.get(room_key) if reader['terminal'] else None,
            'group': group, 'reason': reason,
            # Minutes, for the row's wording: how late, how soon, how long
            # since the reader was heard from.
            'late_by': _minutes(now, start) if status == 'late' and start else None,
            'starts_in': -_minutes(now, start) if status == 'upcoming' and start else None,
            'seen_min': int(reader['seen_ago'].total_seconds() // 60) if reader['seen_ago'] else None,
        })

    claimed = set()
    for r in data['slots']:
        s = r['session']
        if s is not None:
            claimed.add(s.id)
        add(f"slot-{r['slot'].id}", r['slot'].start_time, r['slot'].end_time, r['slot'].room,
            r['course'], r['status'], s, slot=r['slot'], reminded_at=r['reminded_at'],
            count=r['present'])
    # Live classes started outside the timetable still belong on the board.
    for item in data['live']:
        s = item['session']
        if s.id in claimed:
            continue
        add(f"session-{s.id}", s.planned_start or s.start_time, s.planned_end, class_room(s) or item['room'],
            s.course, 'live', s, count=present.get(s.id, 0))

    rows.sort(key=lambda r: (r['start'] is None, r['start'] or now.time()))
    groups = [(key, label, [r for r in rows if r['group'] == key]) for key, label in BOARD_GROUPS]
    active = [t for t in terminals if t.is_active]
    return {
        'now': now,
        'rows': rows,
        'groups': [g for g in groups if g[2]],
        'facts': {
            'needs': sum(1 for r in rows if r['group'] == 'needs'),
            'live': len(data['live']),
            # Every switched-on reader, with or without a room.
            'readers_online': sum(1 for t in active
                                  if t.last_seen_at and now_utc - t.last_seen_at <= online_within),
            'readers': len(active),
        },
    }


def recent_checkins(limit=8):
    """The latest check-ins, with student, course and session loaded up
    front (the old feed ran two extra queries per row)."""
    return (Attendance.query
            .options(joinedload(Attendance.student),
                     joinedload(Attendance.session).joinedload(Session.course))
            .order_by(Attendance.time_in.desc(), Attendance.id.desc())
            .limit(limit).all())
