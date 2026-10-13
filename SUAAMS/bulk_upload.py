"""Bulk CSV upload of lecturers and courses, with a preview before saving.

Same two steps as the timetable import, so nothing is saved unseen:

  plan_lecturers() / plan_courses()   check every row -> a preview
  apply_lecturers() / apply_courses() save an approved plan, in one transaction

The preview travels back with the confirm form as JSON and is re-planned
from scratch on confirm (plan_from_json), so a stale or edited preview can't
save anything the checks would reject.

Rules
-----
* Any row with an error blocks the whole file: fix the CSV, upload again.
  (The student upload skips bad rows instead; for lecturers and courses a
  half-saved file is harder to repair than a rejected one.)
* A row that already exists -- a staff ID already registered, a course code
  already in that semester -- is SKIPPED, not an error, and never changed.
  So re-uploading the same file, or a file that overlaps an earlier one, is
  harmless.
* Courses name their lecturers by staff ID: the first is the coordinator,
  any others are co-lecturers ("STF/1; STF/7"). Lecturers must already
  exist -- upload the lecturers file first.
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

from models import db, Course, Department, Lecturer, User, course_lecturers
from timetable_pdf import normalize_code

MAX_ROWS = 1000         # same limit as the student upload
_CHUNK = 500            # rows per IN (...) lookup and per INSERT batch

# Same reasoning as BULK_DEFAULT_PASSWORD_ROUNDS in blueprints/admin.py: the
# default password is the staff ID itself, which is in the CSV, so a slow
# hash protects nothing; the forced change at first sign-in does, and that
# new password is hashed at full cost.
DEFAULT_PASSWORD_ROUNDS = 4

LECTURER_COLUMNS = ('staff_id', 'full_name', 'department')
COURSE_COLUMNS = ('course_code', 'course_title', 'department', 'credit_units', 'lecturers')
REQUIRED = {
    'lecturers': {'staff_id', 'full_name', 'department'},
    'courses': {'course_code', 'course_title', 'lecturers'},
}
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


@dataclass
class BulkPlan:
    kind: str                       # 'lecturers' | 'courses'
    filename: str
    rows: list[BulkRow]
    semester_id: int | None = None

    @property
    def ok(self):
        return not any(r.errors for r in self.rows)

    def count(self, status):
        return sum(1 for r in self.rows if r.status == status)

    @property
    def new_rows(self):
        return [r for r in self.rows if r.status == 'new']

    def to_json(self):
        return {'kind': self.kind, 'filename': self.filename, 'semester_id': self.semester_id,
                'rows': [{'line': r.line, **r.values} for r in self.rows]}


# ---- reading ---------------------------------------------------------------------

def read_csv(data, kind):
    """bytes -> [BulkRow] with cleaned values. Raises BulkCsvError."""
    try:
        # utf-8-sig: Excel's "CSV UTF-8" puts a byte-order mark in front of
        # the first header, which would otherwise read as "﻿staff_id".
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise BulkCsvError("The file isn't UTF-8 text. In Excel use Save As -> \"CSV UTF-8\".")
    reader = csv.DictReader(io.StringIO(text, newline=''))
    headers = {_header(h) for h in (reader.fieldnames or [])}
    missing = REQUIRED[kind] - headers
    if missing:
        raise BulkCsvError(f"Missing column(s): {', '.join(sorted(missing))}. "
                           f"Download the template to see the expected headers.")
    columns = LECTURER_COLUMNS if kind == 'lecturers' else COURSE_COLUMNS
    rows = []
    for i, raw in enumerate(reader, start=2):
        values = {c: '' for c in columns}
        for key, value in raw.items():
            name = _header(key)
            if name in values and value is not None:
                values[name] = ' '.join(str(value).split())    # trim, collapse spaces
        if any(values.values()):                                # skip blank lines
            rows.append(BulkRow(line=i, values=values))
    if not rows:
        raise BulkCsvError('The file has no rows under its headers.')
    if len(rows) > MAX_ROWS:
        raise BulkCsvError(f"The file has {len(rows)} rows. Upload at most {MAX_ROWS} at a time: "
                           f"split it into smaller files.")
    return rows


def _header(name):
    name = (name or '').strip().lower().replace(' ', '_')
    return ALIASES.get(name, name)


def plan_from_json(payload, semester=None):
    """Rebuild a plan from the preview's JSON (on confirm) and re-check it."""
    kind = payload.get('kind')
    columns = LECTURER_COLUMNS if kind == 'lecturers' else COURSE_COLUMNS
    rows = [BulkRow(line=int(r.get('line', 0)), values={c: str(r.get(c) or '') for c in columns})
            for r in payload.get('rows', [])]
    filename = str(payload.get('filename') or '')
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
                r.errors.append(f"{col} is empty.")
        if r.errors:
            continue
        key = v['staff_id'].lower()
        if key in seen:
            r.errors.append(f"Staff ID {v['staff_id']} is also on line {seen[key]}.")
            continue
        seen[key] = r.line
        if key in lecturers:
            r.status, r.note = 'exists', 'Already registered -- skipped, not changed.'
            continue
        if key in usernames:
            # A student or admin already signs in with this as a username.
            r.errors.append(f"{v['staff_id']} is already another account's login.")
            continue
        department = departments.get(v['department'].lower())
        if not department:
            r.errors.append(f"No department \"{v['department']}\". Create it on the Organization page first.")
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
                r.errors.append(f"{col} is empty.")
        if r.errors:
            continue
        v['course_code'] = v['course_code'].upper()
        code = normalize_code(v['course_code'])
        if code in seen:
            r.errors.append(f"{v['course_code']} is also on line {seen[code]}.")
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
                r.errors.append(f"No department \"{v['department']}\". Create it on the Organization page first.")
        else:
            r.resolved['department_id'] = None      # a general course (GST)

        if v['credit_units']:
            if v['credit_units'].isdigit() and 1 <= int(v['credit_units']) <= 10:
                r.resolved['credit_units'] = int(v['credit_units'])
            else:
                r.errors.append(f"credit_units \"{v['credit_units']}\" isn't a number from 1 to 10.")

        ids = list(dict.fromkeys(s for s in re.split(r'[;,]', v['lecturers']) if s.strip()))
        found = []
        for sid in (s.strip() for s in ids):
            lecturer = staff.get(sid.lower())
            if lecturer and lecturer.status != 'active':
                r.errors.append(f"{lecturer.full_name} ({sid}) is marked {lecturer.status.replace('_', ' ')} "
                                f"and can't be given a course.")
            elif lecturer:
                found.append(lecturer)
            else:
                r.errors.append(f"No lecturer with staff ID {sid}. Upload the lecturers file first.")
        if found and not r.errors:
            r.resolved['lecturer_ids'] = list(dict.fromkeys(l.id for l in found))
            r.resolved['lecturer_names'] = [l.full_name for l in found]

    for r in rows:
        if r.errors:
            r.status = 'error'
    return BulkPlan('courses', filename, rows, semester_id=semester.id)


# ---- saving ----------------------------------------------------------------------------
# Not committed here: the caller commits together with its audit entry.

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


def template_csv(kind):
    """A header row plus one example, for the "Download template" links."""
    if kind == 'lecturers':
        return 'staff_id,full_name,department\nSTF/0001,Dr Jane Doe,Mechatronics Engineering\n'
    return ('course_code,course_title,department,credit_units,lecturers\n'
            'MCT401,Control Systems,Mechatronics Engineering,3,STF/0001; STF/0002\n'
            'GST212,Philosophy and Logic,,2,STF/0003\n')
