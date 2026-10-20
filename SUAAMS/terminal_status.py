"""What a reader's door screen shows: the class in its room right now.

A reader knows nothing about classes on its own. It asks
GET /api/v1/terminal/status (api/terminal.py) once a minute, and that
answers from data the server already has: the reader's room (Terminals
page), the sessions lecturers started, and today's published timetable.

    {"room": "LT 1",
     "now":  {"course_code": "MCT 401", "ends": "11:00",
              "present": 23, "enrolled": 40, "more": 0},
     "next": {"course_code": "MCT 405", "starts": "14:00"}}

  now   the live session whose room matches the reader's -- the same loose
        match the wrong-room check uses (terminal_rooms.normalize_room), so
        a class the screen shows is a class a tap here would not be flagged
        for. `more` counts any other live sessions in the same room.
  next  the earliest of today's remaining published slots in that room,
        this semester only (utils.current_slot_filter: published slots
        never expire, so without it last semester's timetable would show).

Either is null when there's nothing to show, and all three are null for a
reader with no room set (or one still on the old shared secret, which the
server can't place in a room) -- the screen then shows its plain idle text.

Only course codes and counts: the screen is public, so no names.

Times: timetable and planned times are campus wall-clock times, compared
with campus_now(). See campus_time.py.
"""
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from campus_time import campus_now
from models import db, Attendance, Enrollment, Session, Timetable
from terminal_rooms import class_room, normalize_room
from utils import ATTENDED_STATUSES, current_slot_filter


def _hhmm(t):
    return t.strftime('%H:%M') if t is not None else None


def _session_end(session):
    """When the class is due to end: what the lecturer planned, else its
    timetable slot's end, else unknown."""
    if session.planned_end is not None:
        return session.planned_end
    slot = session.timetable
    return slot.end_time if slot is not None else None


def status_for(terminal, now=None):
    """The status dict for one reader (a models.Terminal, or None)."""
    room = normalize_room(terminal.room) if terminal is not None else ''
    if not room:
        return {"room": None, "now": None, "next": None}

    now = now or campus_now()

    # Live sessions are few (one per running class across the campus), so
    # matching rooms in Python is cheaper than teaching SQL the loose match.
    # The slot (for its room and end time) and course come in the same
    # query, rather than one lazy load per live session.
    live = [s for s in Session.query
                                    .options(joinedload(Session.timetable), joinedload(Session.course))
                                    .filter(Session.is_active.is_(True))
                                    .order_by(Session.id).all()
            if normalize_room(class_room(s)) == room]

    current = None
    if live:
        session = live[0]
        present = (db.session.query(func.count(Attendance.id))
                   .filter(Attendance.session_id == session.id,
                           Attendance.status.in_(ATTENDED_STATUSES))
                   .scalar())
        enrolled = Enrollment.query.filter_by(course_id=session.course_id).count()
        current = {
            "course_code": session.course.course_code if session.course else None,
            "ends": _hhmm(_session_end(session)),
            "present": present,
            "enrolled": enrolled,
            "more": len(live) - 1,
        }

    upcoming = None
    semester_filter = current_slot_filter()
    if semester_filter is not None:
        slots = (Timetable.query
                 .filter(semester_filter,
                         Timetable.is_published.is_(True),
                         Timetable.day_of_week == now.weekday(),
                         Timetable.start_time > now.time())
                 .order_by(Timetable.start_time, Timetable.id)
                 .all())
        for slot in slots:
            if normalize_room(slot.room) == room:
                upcoming = {
                    "course_code": slot.course.course_code if slot.course else None,
                    "starts": _hhmm(slot.start_time),
                }
                break

    return {"room": terminal.room, "now": current, "next": upcoming}
