"""The semester changeover checklist (admin, 2026-10-26).

Getting a new semester ready spans five pages: create it, get its courses
in, make sure each has an active coordinator, import and publish the
timetable, make it active -- and in a new academic year also graduate the
final years, promote everyone, and upload the new intake. This module says
where each of those stands, read from the data, so the checklist page and
the door board's banner tell the admin what's left and what's next.

Two steps can't be read from data, so an admin ticks them (ChangeoverTick):
  * graduating the final years -- the system never decides someone has
    graduated (carry-overs are common; see promotion.py);
  * uploading the new intake -- nothing marks a student as this year's.

Nothing here changes data except tick() / untick(); every step's action is
an existing page. A fixed number of queries per checklist.
"""
from dataclasses import dataclass
from datetime import timedelta

from campus_time import campus_today
from models import db, ChangeoverTick, Course, Lecturer, PromotionRun, Semester, Student, Timetable
import promotion

# Steps an admin ticks; the rest are read from data.
MANUAL = ('graduate', 'intake')
# The door board's banner: a semester starting within this many days that
# isn't active yet, or an active one this young with steps still open.
BANNER_BEFORE = timedelta(days=21)
BANNER_AFTER = timedelta(days=14)


@dataclass
class Step:
    key: str
    title: str
    fact: str
    done: bool
    note: str = ''
    blocked: bool = False   # can't be done yet (promotion before activation)
    tick: object = None     # the ChangeoverTick, for a manual step


def previous_semester(semester):
    return (Semester.query.filter(Semester.start_date < semester.start_date)
            .order_by(Semester.start_date.desc()).first())


def is_new_year(semester):
    """The first semester of an academic year: its year ('2026/2027')
    differs from the semester before it. False for the very first semester
    on record (nobody to graduate or promote)."""
    year = promotion.academic_year(semester)
    prev = previous_semester(semester)
    return bool(year and prev and promotion.academic_year(prev) != year)


def _plural(n, word, plural=None):
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def checklist(semester):
    """The steps for this semester, in order, plus the first open one."""
    courses = Course.query.filter_by(semester_id=semester.id).count()
    no_coordinator = [code for (code,) in (
        db.session.query(Course.course_code).join(Lecturer, Course.lecturer_id == Lecturer.id)
        .filter(Course.semester_id == semester.id, Lecturer.status != 'active')
        .order_by(Course.course_code))]
    published = Timetable.query.filter_by(semester_id=semester.id, is_published=True).count()
    drafts = Timetable.query.filter_by(semester_id=semester.id, is_published=False).count()
    ticks = {t.step: t for t in ChangeoverTick.query.filter_by(semester_id=semester.id)}

    steps = [
        Step('semester', 'Create the semester',
             f"{semester.start_date.strftime('%d %b %Y')} to {semester.end_date.strftime('%d %b %Y')}", True),
        Step('courses', 'Get its courses in',
             f"{_plural(courses, 'course')} in {semester.name}" if courses else 'No courses yet',
             courses > 0),
    ]
    if not courses:
        coord_fact = 'Once its courses are in'
    elif no_coordinator:
        shown = ', '.join(no_coordinator[:5]) + (f" and {len(no_coordinator) - 5} more" if len(no_coordinator) > 5 else '')
        coord_fact = f"{_plural(len(no_coordinator), 'course')} without an active coordinator: {shown}"
    else:
        coord_fact = 'Every course has an active coordinator'
    steps.append(Step('coordinators', 'Give every course an active coordinator', coord_fact,
                      courses > 0 and not no_coordinator))
    if published or drafts:
        tt_fact = f"{_plural(published, 'class', 'classes')} published" + (f" · {_plural(drafts, 'draft')} waiting" if drafts else '')
    else:
        tt_fact = 'Not imported yet'
    steps.append(Step('timetable', 'Import and publish the timetable', tt_fact, published > 0 and not drafts,
                      note=("It doesn't hold up making the semester active: the Student Affairs "
                            "PDFs can arrive after classes start.") if not published else ''))
    steps.append(Step('active', 'Make it the active semester',
                      'Active: students and lecturers see its courses' if semester.is_active
                      else 'Not active yet', semester.is_active))

    if is_new_year(semester):
        year = promotion.academic_year(semester)
        due = len(promotion.due_to_graduate())
        promoted = PromotionRun.query.filter_by(academic_year=year).first()
        steps.append(Step('graduate', 'Graduate the final years',
                          f"{_plural(due, 'active student')} at or past their final level",
                          'graduate' in ticks, tick=ticks.get('graduate'),
                          note=("Promoting first puts last year's second-to-last level beside these students "
                                "on the due-to-graduate list.") if not promoted and 'graduate' not in ticks else ''))
        steps.append(Step('promote', f"Promote everyone for {year}",
                          f"{_plural(promoted.promoted, 'student')} promoted" if promoted
                          else ('Not run yet' if semester.is_active else 'Make the semester active first'),
                          promoted is not None, blocked=not semester.is_active and promoted is None))
        intake = Student.query.filter_by(status='active', level='100').count()
        steps.append(Step('intake', 'Upload the new intake',
                          f"{_plural(intake, 'active student')} at 100 level",
                          'intake' in ticks, tick=ticks.get('intake')))

    nxt = next((s for s in steps if not s.done and not s.blocked), None)
    return {'steps': steps, 'next': nxt.key if nxt else None,
            'done': sum(1 for s in steps if s.done), 'total': len(steps)}


def tick(semester, step, user_id):
    """Mark a manual step done. Returns False if it already was."""
    if step not in MANUAL:
        raise ValueError(step)
    if ChangeoverTick.query.filter_by(semester_id=semester.id, step=step).first():
        return False
    db.session.add(ChangeoverTick(semester_id=semester.id, step=step, done_by=user_id))
    return True


def untick(semester, step):
    """Not done after all. Returns False if it wasn't ticked."""
    row = ChangeoverTick.query.filter_by(semester_id=semester.id, step=step).first()
    if row is None:
        return False
    db.session.delete(row)
    return True


def banner(today=None):
    """For the door board: the semester whose changeover is under way, with
    its progress, or None. A semester starting within BANNER_BEFORE that
    isn't active yet; else the active one within BANNER_AFTER of its start
    while steps are still open."""
    today = today or campus_today()
    upcoming = (Semester.query.filter(Semester.is_active.is_(False),
                                      Semester.start_date >= today,
                                      Semester.start_date <= today + BANNER_BEFORE)
                .order_by(Semester.start_date).first())
    semester = upcoming or (Semester.query.filter(Semester.is_active.is_(True),
                                                  Semester.start_date <= today,
                                                  Semester.start_date >= today - BANNER_AFTER).first())
    if semester is None:
        return None
    state = checklist(semester)
    if state['done'] == state['total']:
        return None
    return {'semester': semester, 'done': state['done'], 'total': state['total'],
            'starts_in': (semester.start_date - today).days}
