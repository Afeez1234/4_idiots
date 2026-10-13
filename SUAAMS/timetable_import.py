"""Turn uploaded Student Affairs timetable sheets into draft timetable slots.

Two steps, so nothing is saved before an admin has seen it:

  plan_sheets()   read each PDF, match every class to a course, and check it
                  -> a preview (errors, notes, what will change)
  apply_plan()    save an approved plan as DRAFT slots, in one transaction

The preview is sent back with the confirm form as JSON and re-checked from
scratch by plan_slots() on confirm, so a stale or edited preview can't save
anything the checks would reject.

Rules
-----
* A class must match a course by code (spaces and capitals ignored) in the
  chosen semester. Unknown codes are errors: create the course, re-upload.
* The same class can appear on several sheets -- a GST course on every
  department's sheet. Identical copies (same course, kind, day, time, room)
  are one class, not a room clash.
* Room clashes and lecturer clashes (any lecturer on both courses, co-
  lecturers included) are errors, against the other uploaded classes and
  against classes already stored for courses NOT in this upload.
* Re-importing replaces: for every course in the upload, its existing DRAFT
  slots for the semester are replaced. Its PUBLISHED slots stay visible to
  students until the drafts are published, so an import never leaves a
  course missing from anyone's timetable halfway through.
* All or nothing: any error blocks the whole upload.
"""
from dataclasses import dataclass, field
from datetime import time

from models import db, Course, Department, Session as SessionModel, Timetable
from timetable_pdf import KINDS, TimetablePdfError, normalize_code, parse_timetable_pdf

DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

MAX_FILES = 10                  # per upload; ~0.7s each to read (more on Render)
MAX_FILE_BYTES = 5 * 1024 * 1024


@dataclass
class PlannedSlot:
    code: str
    kind: str
    day: int
    start: time
    end: time
    room: str
    course: Course | None = None
    errors: list[str] = field(default_factory=list)
    shared_with: list[str] = field(default_factory=list)   # other sheets with the same class

    @property
    def key(self):
        """Identity of a class: two sheets printing this are the same class."""
        return (self.course.id if self.course else self.code, self.kind, self.day,
                self.start, self.end, self.room.upper())

    def describe(self):
        return (f"{self.code} {KINDS.get(self.kind, '')} {DAY_NAMES[self.day]} "
                f"{self.start:%H:%M}-{self.end:%H:%M}" + (f" in {self.room}" if self.room else ''))

    def to_json(self):
        return {'code': self.code, 'kind': self.kind, 'day': self.day,
                'start': f'{self.start:%H:%M}', 'end': f'{self.end:%H:%M}', 'room': self.room}


@dataclass
class SheetPlan:
    filename: str
    department: str | None = None
    level: int | None = None
    semester_label: str | None = None
    slots: list[PlannedSlot] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)     # sheet-level, e.g. can't read the PDF
    notes: list[str] = field(default_factory=list)      # worth a look, but not blocking

    @property
    def title(self):
        if self.department and self.level:
            return f"{self.department} · {self.level} level"
        return self.filename

    def to_json(self):
        return {'filename': self.filename, 'department': self.department, 'level': self.level,
                'semester_label': self.semester_label, 'slots': [s.to_json() for s in self.slots]}


@dataclass
class ImportPlan:
    semester_id: int
    sheets: list[SheetPlan]
    replaces_drafts: int = 0        # existing draft slots this import replaces

    @property
    def ok(self):
        return not any(sheet.errors or any(s.errors for s in sheet.slots) for sheet in self.sheets)

    @property
    def problem_count(self):
        """Sheet-level errors plus classes with at least one error."""
        return sum(len(sheet.errors) + sum(1 for s in sheet.slots if s.errors)
                   for sheet in self.sheets)

    @property
    def unique_slots(self):
        """Every class to save, each shared class once."""
        seen, out = set(), []
        for sheet in self.sheets:
            for s in sheet.slots:
                if s.key not in seen:
                    seen.add(s.key)
                    out.append(s)
        return out

    def to_json(self):
        return {'semester_id': self.semester_id, 'sheets': [s.to_json() for s in self.sheets]}


# ---- planning -------------------------------------------------------------------

def plan_sheets(files, semester):
    """files: [(filename, bytes)]. Read every PDF, then check the lot."""
    import io
    sheets = []
    for filename, data in files:
        plan = SheetPlan(filename=filename)
        try:
            parsed = parse_timetable_pdf(io.BytesIO(data))
        except TimetablePdfError as e:
            plan.errors.append(str(e))
            sheets.append(plan)
            continue
        plan.department, plan.level, plan.semester_label = parsed.department, parsed.level, parsed.semester
        plan.notes += parsed.warnings
        plan.slots = [PlannedSlot(s.code, s.kind, s.day, s.start, s.end, s.room) for s in parsed.slots]
        sheets.append(plan)
    return _check(ImportPlan(semester.id, sheets), semester)


def plan_slots(payload, semester):
    """Rebuild a plan from the preview's JSON (on confirm) and re-check it."""
    sheets = []
    for raw in payload.get('sheets', []):
        plan = SheetPlan(filename=str(raw.get('filename', '')), department=raw.get('department'),
                         level=raw.get('level'), semester_label=raw.get('semester_label'))
        for s in raw.get('slots', []):
            plan.slots.append(PlannedSlot(
                code=normalize_code(s['code']), kind=s['kind'], day=int(s['day']),
                start=time.fromisoformat(s['start']), end=time.fromisoformat(s['end']),
                room=str(s.get('room') or '')))
        sheets.append(plan)
    return _check(ImportPlan(semester.id, sheets), semester)


def _check(plan, semester):
    courses = _courses_by_code(semester)
    departments = {d.name.strip().lower() for d in Department.query.all()}

    for sheet in plan.sheets:
        if sheet.semester_label and not _same_semester(sheet.semester_label, semester.name):
            sheet.notes.append(f"The sheet says \"{sheet.semester_label}\" but you're importing "
                               f"into \"{semester.name}\". Check that's the right semester.")
        if sheet.department and sheet.department.lower() not in departments:
            sheet.notes.append(f"No department called \"{sheet.department}\" in SUAAMS. That's "
                               f"fine if its courses exist; the department name isn't used to save anything.")
        for s in sheet.slots:
            if s.kind not in KINDS or not (0 <= s.day <= 6) or s.start >= s.end:
                s.errors.append('Not a valid class (kind, day or times).')
                continue
            matches = courses.get(normalize_code(s.code), [])
            if not matches:
                s.errors.append(f"No course {s.code} in {semester.name}. Create it on the Courses page, then upload again.")
            elif len(matches) > 1:
                s.errors.append(f"More than one course is coded {s.code}; give them distinct codes first.")
            else:
                s.course = matches[0]

    # Identical classes on several sheets are one class (GST on every sheet).
    # Tracked by each sheet's position in the upload, not its title: the
    # same sheet uploaded twice has the same title twice.
    owners = {}
    for i, sheet in enumerate(plan.sheets):
        for s in sheet.slots:
            owners.setdefault(s.key, []).append(i)
    for i, sheet in enumerate(plan.sheets):
        for s in sheet.slots:
            s.shared_with = [plan.sheets[j].title for j in owners[s.key] if j != i]

    _check_clashes(plan, semester)

    uploaded_course_ids = {s.course.id for s in plan.unique_slots if s.course}
    if uploaded_course_ids:
        plan.replaces_drafts = Timetable.query.filter(
            Timetable.semester_id == semester.id,
            Timetable.course_id.in_(uploaded_course_ids),
            Timetable.is_published.is_(False),
        ).count()
    return plan


def _check_clashes(plan, semester):
    new = [s for s in plan.unique_slots if s.course]
    uploaded_course_ids = {s.course.id for s in new}
    # Stored classes this upload won't replace: other courses' slots,
    # published or draft (a draft still occupies its room).
    existing = [
        e for e in Timetable.query.filter(Timetable.semester_id == semester.id).all()
        if e.course_id not in uploaded_course_ids
    ]

    def lecturer_ids(course):
        return {l.id for l in course.all_lecturers}

    def overlaps(a_day, a_start, a_end, b_day, b_start, b_end):
        return a_day == b_day and a_start < b_end and b_start < a_end

    problems = {}   # slot key -> [error]
    for a in new:
        # Every other uploaded class, both ways round, so each side of a
        # clash shows what it clashes with in the preview.
        others = [(b.course, b.day, b.start, b.end, b.room, b.describe()) for b in new if b.key != a.key]
        others += [(e.course, e.day_of_week, e.start_time, e.end_time, e.room or '',
                    f"{e.course.course_code} {DAY_NAMES[e.day_of_week]} "
                    f"{e.start_time:%H:%M}-{e.end_time:%H:%M}" + (f" in {e.room}" if e.room else '')
                    + ' (already stored)')
                   for e in existing if e.course]
        for course, day, start, end, room, label in others:
            if not overlaps(a.day, a.start, a.end, day, start, end):
                continue
            if course.id == a.course.id:
                # The same course twice at overlapping times (e.g. its
                # lecture and tutorial both at 10:00): its students can't be
                # in both, whatever the rooms.
                problems.setdefault(a.key, []).append(f"{a.code} is also scheduled at an overlapping time: {label}.")
                continue
            if room and a.room and room.strip().upper() == a.room.strip().upper():
                problems.setdefault(a.key, []).append(f"Room {a.room} is also booked by {label}.")
            shared = lecturer_ids(a.course) & lecturer_ids(course)
            if shared:
                name = next(l.full_name for l in a.course.all_lecturers if l.id in shared)
                problems.setdefault(a.key, []).append(f"{name} also teaches {label}.")

    for sheet in plan.sheets:
        for s in sheet.slots:
            s.errors += problems.get(s.key, [])


def _courses_by_code(semester):
    """normalized code -> [course]: courses in this semester, or with no
    semester set (the semester field on a course is optional)."""
    out = {}
    for c in Course.query.filter((Course.semester_id == semester.id) | (Course.semester_id.is_(None))).all():
        out.setdefault(normalize_code(c.course_code), []).append(c)
    # A course set to this semester wins over an unassigned one with the same code.
    for code, matches in out.items():
        exact = [c for c in matches if c.semester_id == semester.id]
        if exact:
            out[code] = exact
    return out


def _same_semester(sheet_label, semester_name):
    """'Second Semester 2025/2026' vs '2025/2026 Second Semester': same words."""
    def words(text):
        return {w for w in text.lower().replace('-', ' ').split() if w not in ('semester', 'session')}
    return words(sheet_label) <= words(semester_name) or words(semester_name) <= words(sheet_label)


# ---- saving -----------------------------------------------------------------------

def apply_plan(plan, semester, created_by):
    """Save an approved plan as draft slots. Raises ValueError if it has
    errors. Not committed here: the caller commits with its audit entry."""
    if not plan.ok:
        raise ValueError('This import has errors and cannot be saved.')
    slots = plan.unique_slots
    course_ids = {s.course.id for s in slots}

    # Replace this upload's courses' previous DRAFTS; published slots stay
    # until publishing swaps them (see module docstring).
    old_drafts = Timetable.query.filter(
        Timetable.semester_id == semester.id,
        Timetable.course_id.in_(course_ids),
        Timetable.is_published.is_(False),
    ).all()
    old_ids = [t.id for t in old_drafts]
    if old_ids:
        # Nothing sets Session.timetable_id today, but if anything ever
        # does, a deleted slot must not take class history with it.
        SessionModel.query.filter(SessionModel.timetable_id.in_(old_ids)) \
            .update({SessionModel.timetable_id: None}, synchronize_session=False)
        for t in old_drafts:
            db.session.delete(t)

    for s in slots:
        db.session.add(Timetable(
            course_id=s.course.id, semester_id=semester.id, day_of_week=s.day,
            start_time=s.start, end_time=s.end, room=s.room or None, kind=s.kind,
            type='scheduled', is_published=False, created_by=created_by,
        ))
    return {'saved': len(slots), 'replaced_drafts': len(old_ids), 'courses': len(course_ids)}
