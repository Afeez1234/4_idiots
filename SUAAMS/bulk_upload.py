"""Bulk CSV upload of students, lecturers and courses, with a preview
before saving.

Same two steps as the timetable import, so nothing is saved unseen:

  plan_students() / plan_lecturers() / plan_courses()     check every row -> a preview
  apply_students() / apply_lecturers() / apply_courses()  save an approved plan

The preview travels back with the confirm form as JSON and is re-planned
from scratch on confirm (plan_from_json), so a stale or edited preview can't
save anything the checks would reject.

Rules
-----
* For lecturers and courses, any row with an error blocks the whole file:
  fix the CSV, upload again -- a half-saved file is harder to repair than a
  rejected one. Students are different (SKIPS_BAD_ROWS): a 900-row class
  list shouldn't wait on one typo, so bad rows are shown in the preview as
  skipped, with the reason, and the rest are saved. Until 2026-10-17 the
  student upload had no preview at all: it saved on submit and reported
  skipped rows only as "View logs" -- the server logs, out of an admin's
  reach.
* A row that already exists -- a staff ID already registered, a course code
  already in that semester -- is SKIPPED, not an error, and never changed.
  So re-uploading the same file, or a file that overlaps an earlier one, is
  harmless.
* Courses name their lecturers by staff ID: the first is the coordinator,
  any others are co-lecturers ("STF/1; STF/7"). Lecturers must already
  exist -- upload the lecturers file first.
* "Copy courses from another semester" (plan_course_copy) builds course
  rows from a past semester's courses and runs them through the same
  plan_courses checks, preview and save -- a CSV the admin didn't have to
  write. Lecturers no longer active are left out rather than blocking it.
* An Excel workbook (.xlsx) is accepted as well as CSV (read_upload,
  2026-10-19): the first sheet's first row is the header, read through the
  same checks. Excel's plain "CSV" turns letters like ẹ, ọ and ṣ into "?"
  and older Excel has no "CSV UTF-8", so uploading the workbook itself is
  the easy, lossless path.
* Saving uses multi-row INSERTs in chunks, like the student upload: an ORM
  object per row is one round trip each to the remote MySQL, which is what
  made the old student upload time out on Render.
"""
import csv
import io
import re
from dataclasses import dataclass, field

import bcrypt
from sqlalchemy import insert as sa_insert

from models import db, Course, Department, Lecturer, Student, User, course_lecturers
from timetable_pdf import normalize_code
from utils import normalize_level

MAX_ROWS = 1000         # same limit as the student upload
_CHUNK = 500            # rows per IN (...) lookup and per INSERT batch

# bcrypt cost for DEFAULT passwords. The default password is the matric
# number or staff ID itself -- in the CSV, and on a student's ID card -- so a
# slow hash protects nothing (cost 12 was ~3s per row on Render's free tier,
# which timed uploads out; 4 is ~1ms); the forced change at first sign-in does, and that
# new password is hashed at full cost.
DEFAULT_PASSWORD_ROUNDS = 4

# No rfid_uid since 2026-10-23: the RFID reader was retired on 2026-10-12.
# Old sheets that still have the column upload fine; it's ignored.
STUDENT_COLUMNS = ('matric_number', 'full_name', 'level', 'department')
LECTURER_COLUMNS = ('staff_id', 'full_name', 'department')
COURSE_COLUMNS = ('course_code', 'course_title', 'department', 'credit_units', 'lecturers')
COLUMNS = {'students': STUDENT_COLUMNS, 'lecturers': LECTURER_COLUMNS, 'courses': COURSE_COLUMNS}
REQUIRED = {
    'students': {'matric_number', 'full_name', 'level', 'department'},
    'lecturers': {'staff_id', 'full_name', 'department'},
    'courses': {'course_code', 'course_title', 'lecturers'},
}
# Kinds whose bad rows are skipped rather than blocking the file (see Rules).
SKIPS_BAD_ROWS = {'students'}

# A course copy's plan is named after its source semester; the prefix is how
# the preview and the audit entry tell a copy from an uploaded file.
COPY_PREFIX = 'Copied from '


def _status_name(status):
    return status.replace('_', ' ')
# Header spellings accepted as the same column: the student CSV says
# department_name, so colleagues will reuse it.
ALIASES = {'department_name': 'department', 'code': 'course_code', 'title': 'course_title',
           'name': 'full_name', 'units': 'credit_units', 'lecturer': 'lecturers'}


class BulkCsvError(ValueError):
    """The file as a whole can't be used (encoding, headers, size)."""


@dataclass
class BulkRow:
    line: int                       # line in the CSV, header = line 1
    values: dict
    status: str = 'new'             # new | exists | error
    errors: list[str] = field(default_factory=list)
    note: str = ''                  # e.g. why it's skipped
    resolved: dict = field(default_factory=dict)   # ids found while checking
    # Which cells are wrong, so the preview can mark them (2026-10-26):
    # the reason alone said "credit_units isn't a number" with nothing on
    # the row pointing at the cell.
    bad_fields: set = field(default_factory=set)

    def fail(self, column, message):
        self.errors.append(message)
        self.bad_fields.add(column)


@dataclass
class BulkPlan:
    kind: str                       # 'students' | 'lecturers' | 'courses'
    filename: str
    rows: list[BulkRow]
    semester_id: int | None = None

    @property
    def ok(self):
        """Can this plan be saved? Always, for a kind that skips bad rows."""
        return self.kind in SKIPS_BAD_ROWS or not any(r.errors for r in self.rows)

    def count(self, status):
        return sum(1 for r in self.rows if r.status == status)

    @property
    def is_copy(self):
        return self.filename.startswith(COPY_PREFIX)

    @property
    def new_rows(self):
        return [r for r in self.rows if r.status == 'new']

    def to_json(self):
        return {'kind': self.kind, 'filename': self.filename, 'semester_id': self.semester_id,
                'rows': [{'line': r.line, **r.values} for r in self.rows]}


# ---- reading ---------------------------------------------------------------------

def read_upload(data, filename, kind):
    """An uploaded file -> [BulkRow]: an Excel workbook (.xlsx) or a CSV,
    told apart by name and by content (an .xlsx is a zip, starting "PK").
    Raises BulkCsvError."""
    name = (filename or '').lower()
    if name.endswith('.xls'):
        raise BulkCsvError("Old Excel files (.xls) can't be read. In Excel use Save As -> "
                           "\"Excel Workbook (.xlsx)\", or upload a CSV.")
    if name.endswith('.xlsx') or data[:4] == b'PK\x03\x04':
        return read_xlsx(data, kind)
    return read_csv(data, kind)


def read_csv(data, kind):
    """CSV bytes -> [BulkRow] with cleaned values. Raises BulkCsvError."""
    try:
        # utf-8-sig: Excel's "CSV UTF-8" puts a byte-order mark in front of
        # the first header, which would otherwise read as "﻿staff_id".
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        # Strict on purpose: a file from Excel's plain "CSV" has already
        # turned letters like ẹ and ọ into "?", and guessing another
        # encoding would save those damaged names.
        raise BulkCsvError("The file isn't UTF-8 text. Upload the Excel file (.xlsx) itself, "
                           "or in Excel use Save As -> \"CSV UTF-8\".")
    reader = csv.reader(io.StringIO(text, newline=''))
    return _table_rows(next(reader, []), reader, kind)


def read_xlsx(data, kind):
    """Excel workbook bytes -> [BulkRow], from the first sheet: its first
    row is the header. Read-only and values-only (a formula gives its last
    computed value). Raises BulkCsvError."""
    from openpyxl import load_workbook
    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise BulkCsvError("That isn't a readable Excel workbook (.xlsx). Open it in Excel and save it "
                           "again, or upload a CSV.")
    try:
        if not book.worksheets:
            raise BulkCsvError('The workbook has no sheets.')
        rows = book.worksheets[0].iter_rows(values_only=True)
        header = next(rows, ())
        return _table_rows([_cell(v) for v in header], ([_cell(v) for v in r] for r in rows), kind)
    finally:
        book.close()


def _cell(value):
    """An Excel cell as the text a CSV would hold. Whole numbers lose the
    ".0" Excel stores them with (a staff ID typed as 1001 is "1001", credit
    units 3 is "3"); a date is its ISO date; empty is ""."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if hasattr(value, 'date') and hasattr(value, 'isoformat'):
        return value.date().isoformat() if hasattr(value, 'hour') else value.isoformat()
    return str(value)


def _table_rows(header, rows, kind):
    """A header row and the rows under it (lists of text) -> [BulkRow] with
    cleaned values, for CSV and Excel alike. Line numbers count the header
    as line 1, as a spreadsheet shows them. Stops reading past MAX_ROWS, so
    a huge sheet is refused without being loaded whole."""
    names = [_header(h) for h in header]
    missing = REQUIRED[kind] - set(names)
    if missing:
        raise BulkCsvError(f"Missing column(s): {', '.join(sorted(missing))}. "
                           f"Download the template to see the expected headers.")
    columns = COLUMNS[kind]
    out = []
    for i, raw in enumerate(rows, start=2):
        values = {c: '' for c in columns}
        for index, name in enumerate(names):
            if name in values and index < len(raw) and raw[index] is not None:
                values[name] = ' '.join(str(raw[index]).split())    # trim, collapse spaces
        if any(values.values()):                                     # skip blank lines
            out.append(BulkRow(line=i, values=values))
            if len(out) > MAX_ROWS:
                raise BulkCsvError(f"The file has more than {MAX_ROWS} rows. Upload at most {MAX_ROWS} "
                                   f"at a time: split it into smaller files.")
    if not out:
        raise BulkCsvError('The file has no rows under its headers.')
    return out


def _header(name):
    name = (name or '').strip().lower().replace(' ', '_')
    return ALIASES.get(name, name)


def plan_from_json(payload, semester=None):
    """Rebuild a plan from the preview's JSON (on confirm) and re-check it."""
    kind = payload.get('kind')
    if kind not in COLUMNS:
        raise BulkCsvError('That preview is no longer valid.')
    rows = [BulkRow(line=int(r.get('line', 0)), values={c: str(r.get(c) or '') for c in COLUMNS[kind]})
            for r in payload.get('rows', [])]
    filename = str(payload.get('filename') or '')
    if kind == 'students':
        return plan_students(rows, filename)
    if kind == 'lecturers':
        return plan_lecturers(rows, filename)
    if kind == 'courses' and semester is not None:
        return plan_courses(rows, filename, semester)
    raise BulkCsvError('That preview is no longer valid.')


# ---- checking ------------------------------------------------------------------------

def _departments():
    return {d.name.strip().lower(): d for d in Department.query.all()}


def _existing(column, values):
    """Which of `values` exist in `column`, lower-cased. Compared case-
    insensitively in the query itself: MySQL's default collation would make
    "stf/1" collide with "STF/1" at INSERT time, so the check must agree
    with it -- and not depend on the database's collation to do so."""
    found = set()
    unique = list(dict.fromkeys(v.lower() for v in values if v))
    for i in range(0, len(unique), _CHUNK):
        found.update(v.lower() for (v,) in db.session.query(column)
                     .filter(db.func.lower(column).in_(unique[i:i + _CHUNK])))
    return found


def plan_students(rows, filename):
    """The same rules the student upload always had: level 100-500 ("400"
    or "400L"), an existing department, a matric number used once. A matric
    number already registered is skipped, not changed."""
    departments = _departments()
    matrics = [r.values['matric_number'] for r in rows]
    students = _existing(Student.matric_number, matrics)
    usernames = _existing(User.username, matrics)
    seen_matric = {}

    for r in rows:
        v = r.values
        for col in STUDENT_COLUMNS:
            if col in REQUIRED['students'] and not v[col]:
                r.fail(col, f"{col} is empty.")
        if r.errors:
            continue
        key = v['matric_number'].lower()
        if key in seen_matric:
            r.fail('matric_number', f"Matric number {v['matric_number']} is also on line {seen_matric[key]}.")
            continue
        seen_matric[key] = r.line
        if key in students:
            r.status, r.note = 'exists', 'Already registered -- skipped, not changed.'
            continue
        if key in usernames:
            # A lecturer or admin already signs in with this as a username.
            r.fail('matric_number', f"{v['matric_number']} is already another account's login.")
            continue
        level = normalize_level(v['level'])
        if level is None:
            r.fail('level', f"Level \"{v['level']}\" isn't 100-500.")
            continue
        department = departments.get(v['department'].lower())
        if not department:
            r.fail('department', f"No department \"{v['department']}\". Create it on the Organization page first.")
            continue
        r.resolved.update(level=level, department_id=department.id)

    for r in rows:
        if r.errors:
            r.status = 'error'
    return BulkPlan('students', filename, rows)


def plan_lecturers(rows, filename):
    departments = _departments()
    staff_ids = [r.values['staff_id'] for r in rows]
    lecturers = _existing(Lecturer.staff_id, staff_ids)
    usernames = _existing(User.username, staff_ids)
    seen = {}

    for r in rows:
        v = r.values
        for col in LECTURER_COLUMNS:
            if not v[col]:
                r.fail(col, f"{col} is empty.")
        if r.errors:
            continue
        key = v['staff_id'].lower()
        if key in seen:
            r.fail('staff_id', f"Staff ID {v['staff_id']} is also on line {seen[key]}.")
            continue
        seen[key] = r.line
        if key in lecturers:
            r.status, r.note = 'exists', 'Already registered -- skipped, not changed.'
            continue
        if key in usernames:
            # A student or admin already signs in with this as a username.
            r.fail('staff_id', f"{v['staff_id']} is already another account's login.")
            continue
        department = departments.get(v['department'].lower())
        if not department:
            r.fail('department', f"No department \"{v['department']}\". Create it on the Organization page first.")
            continue
        r.resolved['department_id'] = department.id

    for r in rows:
        if r.errors:
            r.status = 'error'
    return BulkPlan('lecturers', filename, rows)


def plan_courses(rows, filename, semester):
    departments = _departments()
    staff = {l.staff_id.lower(): l for l in Lecturer.query.all()}
    # A course already in this semester -- or one with no semester set, which
    # the timetable already treats as belonging to every semester.
    existing = {normalize_code(c.course_code) for c in Course.query.filter(
        (Course.semester_id == semester.id) | (Course.semester_id.is_(None))).all()}
    seen = {}

    for r in rows:
        v = r.values
        for col in REQUIRED['courses']:
            if not v[col]:
                r.fail(col, f"{col} is empty.")
        if r.errors:
            continue
        v['course_code'] = v['course_code'].upper()
        code = normalize_code(v['course_code'])
        if code in seen:
            r.fail('course_code', f"{v['course_code']} is also on line {seen[code]}.")
            continue
        seen[code] = r.line
        if code in existing:
            r.status, r.note = 'exists', f'Already in {semester.name} -- skipped, not changed.'
            continue

        if v['department']:
            department = departments.get(v['department'].lower())
            if department:
                r.resolved['department_id'] = department.id
            else:
                r.fail('department', f"No department \"{v['department']}\". Create it on the Organization page first.")
        else:
            r.resolved['department_id'] = None      # a general course (GST)

        if v['credit_units']:
            if v['credit_units'].isdigit() and 1 <= int(v['credit_units']) <= 10:
                r.resolved['credit_units'] = int(v['credit_units'])
            else:
                r.fail('credit_units', f"credit_units \"{v['credit_units']}\" isn't a number from 1 to 10.")

        ids = list(dict.fromkeys(s for s in re.split(r'[;,]', v['lecturers']) if s.strip()))
        found = []
        for sid in (s.strip() for s in ids):
            lecturer = staff.get(sid.lower())
            if lecturer and lecturer.status != 'active':
                r.fail('lecturers', f"{lecturer.full_name} ({sid}) is marked {lecturer.status.replace('_', ' ')} "
                                f"and can't be given a course.")
            elif lecturer:
                found.append(lecturer)
            else:
                r.fail('lecturers', f"No lecturer with staff ID {sid}. Upload the lecturers file first.")
        if found and not r.errors:
            r.resolved['lecturer_ids'] = list(dict.fromkeys(l.id for l in found))
            r.resolved['lecturer_names'] = [l.full_name for l in found]

    for r in rows:
        if r.errors:
            r.status = 'error'
    return BulkPlan('courses', filename, rows, semester_id=semester.id)


def plan_course_copy(source, target):
    """Copy `source` semester's courses into `target`, as a course plan.

    Copies code, title, department, credit units, the coordinator and the
    co-lecturers. Not enrolments (students register each semester), not the
    timetable (Timetable has its own copy) and not courses with no semester
    (they belong to every semester already). None if `source` has no courses.

    A year on, some lecturers will be on leave or gone, and plan_courses
    refuses a course with an inactive lecturer -- one such row would block
    the whole copy. So: inactive co-lecturers are left out, an inactive
    coordinator is replaced by the next active lecturer on the course, and
    the preview says so on that row. Only a course with no active lecturer
    at all is refused, with the reason.
    """
    courses = (Course.query.filter(Course.semester_id == source.id)
               .order_by(Course.course_code, Course.id).all())
    if not courses:
        return None
    rows, notes, no_active = [], {}, {}
    for line, course in enumerate(courses, start=1):
        everyone = course.all_lecturers                     # coordinator first
        active = [l for l in everyone if l.status == 'active']
        gone = [l for l in everyone if l.status != 'active']
        row = BulkRow(line=line, values={
            'course_code': course.course_code,
            'course_title': course.course_title,
            'department': course.department.name if course.department else '',
            'credit_units': str(course.credit_units) if course.credit_units else '',
            'lecturers': '; '.join(l.staff_id for l in active),
        })
        rows.append(row)
        said = [f"{l.full_name} ({_status_name(l.status)}) not copied" for l in gone]
        if active and course.lecturer is not None and course.lecturer.status != 'active':
            said.append(f"{active[0].full_name} becomes coordinator")
        if said:
            notes[line] = '; '.join(said)
        if not active:
            no_active[line] = ', '.join(f"{l.full_name} ({_status_name(l.status)})" for l in gone) or 'none'

    plan = plan_courses(rows, COPY_PREFIX + source.name, target)
    for r in plan.rows:
        if r.line in no_active:
            # plan_courses says "lecturers is empty."; say why, and what to do.
            r.errors = [f"No active lecturer to copy ({no_active[r.line]}). Add an active lecturer to "
                        f"{r.values['course_code']} in {source.name} with Course Lecturers, then copy again."]
            r.bad_fields = {'lecturers'}
            r.status = 'error'
        elif r.status == 'new' and r.line in notes:
            # Upper-case the first letter only: str.capitalize() would also
            # lower-case the rest, turning "Dr Gone" into "Dr gone".
            text = notes[r.line]
            r.note = text[:1].upper() + text[1:] + '.'
    return plan


# ---- saving ----------------------------------------------------------------------------
# Not committed here: the caller commits together with its audit entry.

def apply_students(plan):
    """Saves the plan's new rows; its error rows are the skipped ones."""
    rows = plan.new_rows
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i:i + _CHUNK]
        db.session.execute(sa_insert(User), [{
            'username': r.values['matric_number'],
            # Default password = the matric number, as for one-at-a-time creation.
            'password_hash': bcrypt.hashpw(r.values['matric_number'].encode('utf-8'),
                                           bcrypt.gensalt(DEFAULT_PASSWORD_ROUNDS)).decode('utf-8'),
            'role': 'student', 'is_active': True, 'requires_password_change': True,
        } for r in chunk])
        # MySQL can't return ids from a multi-row INSERT: read them back.
        user_ids = {u.lower(): uid for u, uid in db.session.query(User.username, User.id)
                    .filter(User.username.in_([r.values['matric_number'] for r in chunk]))}
        db.session.execute(sa_insert(Student), [{
            'full_name': r.values['full_name'], 'matric_number': r.values['matric_number'],
            'level': r.resolved['level'], 'department_id': r.resolved['department_id'],
            'user_id': user_ids[r.values['matric_number'].lower()],
        } for r in chunk])
    return len(rows)


def apply_lecturers(plan):
    if not plan.ok:
        raise ValueError('This upload has errors and cannot be saved.')
    rows = plan.new_rows
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i:i + _CHUNK]
        db.session.execute(sa_insert(User), [{
            'username': r.values['staff_id'],
            # Default password = the staff ID, as for one-at-a-time creation.
            'password_hash': bcrypt.hashpw(r.values['staff_id'].encode('utf-8'),
                                           bcrypt.gensalt(DEFAULT_PASSWORD_ROUNDS)).decode('utf-8'),
            'role': 'lecturer', 'is_active': True, 'requires_password_change': True,
        } for r in chunk])
        # MySQL can't return ids from a multi-row INSERT: read them back.
        user_ids = {u.lower(): uid for u, uid in db.session.query(User.username, User.id)
                    .filter(User.username.in_([r.values['staff_id'] for r in chunk]))}
        db.session.execute(sa_insert(Lecturer), [{
            'full_name': r.values['full_name'], 'staff_id': r.values['staff_id'],
            'department_id': r.resolved['department_id'],
            'user_id': user_ids[r.values['staff_id'].lower()],
        } for r in chunk])
    return len(rows)


def apply_courses(plan, semester):
    if not plan.ok:
        raise ValueError('This upload has errors and cannot be saved.')
    rows = plan.new_rows
    for i in range(0, len(rows), _CHUNK):
        chunk = rows[i:i + _CHUNK]
        db.session.execute(sa_insert(Course), [{
            'course_code': r.values['course_code'], 'course_title': r.values['course_title'],
            'department_id': r.resolved['department_id'],
            'credit_units': r.resolved.get('credit_units'),
            'lecturer_id': r.resolved['lecturer_ids'][0],          # the coordinator
            'semester_id': semester.id,
        } for r in chunk])
        course_ids = {code.upper(): cid for code, cid in db.session.query(Course.course_code, Course.id)
                      .filter(Course.semester_id == semester.id,
                              Course.course_code.in_([r.values['course_code'] for r in chunk]))}
        links = [{'course_id': course_ids[r.values['course_code'].upper()], 'lecturer_id': lid}
                 for r in chunk for lid in r.resolved['lecturer_ids'][1:]]
        if links:
            db.session.execute(sa_insert(course_lecturers), links)
    return len(rows)


def courses_workbook(rows):
    """[{column: value}] -> an Excel workbook (bytes) in the Courses upload's
    format: the header row first, as read_xlsx expects, then the rows. Used
    for the timetable import's missing courses: the admin fills in what the
    timetable can't say (title, lecturers) and uploads it as it is."""
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.title = 'Courses'
    sheet.append(list(COURSE_COLUMNS))
    for row in rows:
        sheet.append([row.get(c, '') for c in COURSE_COLUMNS])
    for letter, width in zip('ABCDE', (14, 40, 32, 13, 28)):
        sheet.column_dimensions[letter].width = width
    sheet.freeze_panes = 'A2'
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def problem_rows_csv(plan):
    """The rows that can't be saved, as a CSV in the upload's own columns
    plus a `problem` column: fix those cells and upload just this file.
    Formula-safe (_csv_safe), like the register export."""
    from utils import _csv_safe
    out = io.StringIO()
    writer = csv.writer(out)
    columns = list(COLUMNS[plan.kind])
    writer.writerow(columns + ['problem'])
    for r in plan.rows:
        if r.errors:
            writer.writerow([_csv_safe(r.values.get(c, '')) for c in columns]
                            + [_csv_safe(' '.join(r.errors))])
    return out.getvalue()


def template_csv(kind):
    """A header row plus one example, for the "Download template" links."""
    if kind == 'students':
        return ('matric_number,full_name,level,department\n'
                'MCT/20/0001,Aisha Bello,400,Mechatronics Engineering\n')
    if kind == 'lecturers':
        return 'staff_id,full_name,department\nSTF/0001,Dr Jane Doe,Mechatronics Engineering\n'
    return ('course_code,course_title,department,credit_units,lecturers\n'
            'MCT401,Control Systems,Mechatronics Engineering,3,STF/0001; STF/0002\n'
            'GST212,Philosophy and Logic,,2,STF/0003\n')
