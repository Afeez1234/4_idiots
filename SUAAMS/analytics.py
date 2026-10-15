"""Admin Analytics: patterns across the whole semester, not one day or course.

Two questions, for one semester (the active one unless the page picks another):

1. EXAM ELIGIBILITY -- which students are below EXAM_ELIGIBILITY_THRESHOLD
   in a course? Same rule as the course register CSV lecturers download
   (utils.build_course_register_csv), so the two can never disagree: only
   finished sessions count (an open one would make everyone look absent),
   and present or late counts as attended. A course must have held
   MIN_SESSIONS before anyone is flagged in it -- after one class, missing
   it is 0%, which says nothing yet.

2. CLASSES HELD VS TIMETABLED -- for each course, how many timetabled
   classes actually ran. Each published slot is due once a week, counted
   from TEACHING START (the first day any class ran this semester; lectures
   usually begin a week or two after the semester opens, and counting from
   the semester's start date would show those weeks as missed) up to today
   -- or from the slot's own effective_from, if it started later (a class
   added or moved mid-semester; see Timetable.effective_from).
   A session counts for a slot by timetable_id, or -- for sessions from
   before timetable_id was recorded -- by course, weekday and planned_start.
   Known gap: there is no record of public holidays or cancelled classes,
   so those show as missed.

Both are a fixed number of GROUP BY / column queries; the per-student and
per-slot work happens in Python over plain tuples. tests/test_analytics.py
pins the rules and the query count.
"""
from datetime import timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from campus_time import campus_now
from models import (
    db, Attendance, Course, Department, Enrollment, Session, Student, Timetable,
)
from utils import EXAM_ELIGIBILITY_THRESHOLD

# Sessions a course must have finished before a student can be flagged in it.
MIN_SESSIONS = 3

PRESENT = ('present', 'late')


# ---- 1. exam eligibility ----------------------------------------------------

def eligibility(semester, department_id=None, level=None):
    """Who is below the threshold in at least one course, in `semester`
    (any semester, not only the active one). The level filter is the
    student's level now, which for a past semester may be a year on.

    Returns {
      'threshold', 'min_sessions',
      'students': [{student, courses: [{course, attended, held, pct}]}],
          worst first (lowest pct in any course),
      'by_department': [{name, below, total}], 'by_level': [{level, below, total}],
          total = active students with at least one course that has held
          MIN_SESSIONS; below = those flagged,
      'pairs_below': number of (student, course) pairs below,
    }
    """
    out = {'threshold': EXAM_ELIGIBILITY_THRESHOLD, 'min_sessions': MIN_SESSIONS,
           'students': [], 'by_department': [], 'by_level': [], 'pairs_below': 0}
    if semester is None:
        return out

    courses = {c.id: c for c in Course.query.filter(Course.semester_id == semester.id)}
    if not courses:
        return out
    held = dict(db.session.query(Session.course_id, func.count())
                .filter(Session.course_id.in_(list(courses)), Session.is_active.is_(False))
                .group_by(Session.course_id))
    counted = [cid for cid, n in held.items() if n >= MIN_SESSIONS]
    if not counted:
        return out

    q = (db.session.query(Enrollment.student_id, Enrollment.course_id)
         .join(Student, Student.id == Enrollment.student_id)
         .filter(Enrollment.course_id.in_(counted)))
    # The active semester: only students still at the school. A past one:
    # everyone who was enrolled, including those who have since graduated
    # or left -- dropping them would rewrite that semester's record.
    if semester.is_active:
        q = q.filter(Student.status == 'active')
    if department_id:
        q = q.filter(Student.department_id == department_id)
    if level:
        q = q.filter(Student.level == level)
    pairs = q.all()

    attended = {}
    if pairs:
        rows = (db.session.query(Attendance.student_id, Session.course_id, func.count())
                .join(Session, Session.id == Attendance.session_id)
                .filter(Session.course_id.in_(counted), Session.is_active.is_(False),
                        Attendance.status.in_(PRESENT))
                .group_by(Attendance.student_id, Session.course_id))
        attended = {(sid, cid): n for sid, cid, n in rows}

    below = {}
    for sid, cid in pairs:
        got = attended.get((sid, cid), 0)
        pct = round(got / held[cid] * 100, 1)
        if pct < EXAM_ELIGIBILITY_THRESHOLD:
            below.setdefault(sid, []).append(
                {'course': courses[cid], 'attended': got, 'held': held[cid], 'pct': pct})
    out['pairs_below'] = sum(len(v) for v in below.values())

    # The people, with their department, for the list and both roll-ups.
    in_scope = {sid for sid, _ in pairs}
    people = {}
    if in_scope:
        people = {s.id: s for s in (Student.query
                                    .options(joinedload(Student.department))
                                    .filter(Student.id.in_(list(in_scope))))}

    for sid, rows in below.items():
        rows.sort(key=lambda r: r['pct'])
    out['students'] = sorted(
        ({'student': people[sid], 'courses': rows} for sid, rows in below.items()),
        key=lambda r: (r['courses'][0]['pct'], r['student'].matric_number))

    def rollup(key):
        totals = {}
        for sid, s in people.items():
            k = key(s)
            got_below, total = totals.get(k, (0, 0))
            totals[k] = (got_below + (sid in below), total + 1)
        return totals

    out['by_department'] = sorted(
        ({'name': name, 'below': b, 'total': t}
         for name, (b, t) in rollup(lambda s: s.department.name if s.department else 'No department').items()),
        key=lambda r: (-r['below'] / r['total'], r['name']))
    out['by_level'] = sorted(
        ({'level': lvl, 'below': b, 'total': t} for lvl, (b, t) in rollup(lambda s: s.level).items()),
        key=lambda r: r['level'])
    return out


# ---- 2. classes held vs timetabled -----------------------------------------

def _occurrences(weekday, start, end):
    """How many dates in [start, end] fall on `weekday` (0 = Monday)."""
    if end < start:
        return 0
    first = start + timedelta(days=(weekday - start.weekday()) % 7)
    return 0 if first > end else (end - first).days // 7 + 1


def delivery(semester, department_id=None, now=None):
    """Timetabled classes vs classes held, per course and per department.

    Returns {
      'teaching_start': date or None (None = nothing has run yet),
      'courses': [{course, timetabled, held, missed, extra, rate}], most missed first,
      'by_department': [{name, timetabled, held, missed, rate}],
    }
    `extra` = sessions that match no slot (an extra class, one started with
    typed times, or one held under a schedule that has since changed);
    they're shown, not counted against the timetable.
    """
    out = {'teaching_start': None, 'courses': [], 'by_department': []}
    if semester is None:
        return out
    now = now or campus_now()
    today = now.date()

    slot_q = (db.session.query(Timetable.id, Timetable.course_id, Timetable.day_of_week,
                               Timetable.start_time, Timetable.end_time, Timetable.effective_from)
              .join(Course, Course.id == Timetable.course_id)
              .filter(Timetable.semester_id == semester.id, Timetable.is_published.is_(True)))
    if department_id:
        slot_q = slot_q.filter(Course.department_id == department_id)
    slots = slot_q.all()

    # Teaching start is the whole semester's, not the filtered department's:
    # it's when the school started teaching.
    teaching_start = (db.session.query(func.min(Session.session_date))
                      .join(Course, Course.id == Session.course_id)
                      .filter(Course.semester_id == semester.id).scalar())
    out['teaching_start'] = teaching_start
    if not slots or teaching_start is None:
        return out
    start = max(teaching_start, semester.start_date) if semester.start_date else teaching_start
    end = min(today, semester.end_date) if semester.end_date else today

    course_ids = list({s.course_id for s in slots})
    sessions = (db.session.query(Session.id, Session.course_id, Session.timetable_id,
                                 Session.session_date, Session.planned_start)
                .filter(Session.course_id.in_(course_ids),
                        Session.session_date >= start, Session.session_date <= end).all())

    by_id = {s.id: s for s in slots}
    by_key = {(s.course_id, s.day_of_week, s.start_time): s.id for s in slots}
    # Each slot counts from teaching start, or from its own start date if
    # it was added or moved later (NULL = from teaching start).
    slot_start = {s.id: max(start, s.effective_from) if s.effective_from else start for s in slots}
    timetabled, held, extra = {}, {}, {}
    for slot in slots:
        n = _occurrences(slot.day_of_week, slot_start[slot.id], end)
        # Today's class only counts as due once it has ended.
        if end == today and today.weekday() == slot.day_of_week and now.time() < slot.end_time:
            n -= 1
        timetabled[slot.course_id] = timetabled.get(slot.course_id, 0) + max(n, 0)
    seen = set()       # (slot, date): one session per class, however many were opened
    for s in sessions:
        slot_id = s.timetable_id if s.timetable_id in by_id else by_key.get(
            (s.course_id, s.session_date.weekday(), s.planned_start))
        # A class held before its slot started is from the old schedule.
        if slot_id is not None and s.session_date < slot_start[slot_id]:
            slot_id = None
        if slot_id is None:
            extra[s.course_id] = extra.get(s.course_id, 0) + 1
        elif (slot_id, s.session_date) not in seen:
            seen.add((slot_id, s.session_date))
            held[s.course_id] = held.get(s.course_id, 0) + 1

    courses = {c.id: c for c in (Course.query.options(joinedload(Course.department))
                                 .filter(Course.id.in_(course_ids)))}
    rows, depts = [], {}
    for cid, due in timetabled.items():
        ran = min(held.get(cid, 0), due)
        course = courses[cid]
        rows.append({'course': course, 'timetabled': due, 'held': ran, 'missed': due - ran,
                     'extra': extra.get(cid, 0), 'rate': round(ran / due * 100) if due else None})
        name = course.department.name if course.department else 'General courses'
        d_due, d_ran = depts.get(name, (0, 0))
        depts[name] = (d_due + due, d_ran + ran)
    out['courses'] = sorted(rows, key=lambda r: (-r['missed'], r['course'].course_code))
    out['by_department'] = sorted(
        ({'name': n, 'timetabled': due, 'held': ran, 'missed': due - ran,
          'rate': round(ran / due * 100) if due else None} for n, (due, ran) in depts.items()),
        key=lambda r: (r['rate'] if r['rate'] is not None else 101, r['name']))
    return out
