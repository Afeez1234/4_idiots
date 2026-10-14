"""Moving every active student up one level at the start of a session.

One action for the whole school, run once per academic year after the new
session's first semester is made active:

  plan_promotion()   who moves, who stays, who is due to graduate -> preview
  apply_promotion()  do it, in one transaction, and record the run
  undo_promotion()   put the last run back (a mistake on 6,000 students
                     must be recoverable without a database restore)

Rules
-----
* Only ACTIVE students move. Suspended, rusticated, graduated, ... don't.
* A student in their department's final year (level = programme years x 100)
  or beyond (spill-over) doesn't move: they are listed as due to graduate.
  Graduating them is a separate, deliberate step (Change Status by CSV, from
  the list this page downloads) -- carry-overs are common, so the system
  never decides someone has graduated.
* Repeaters are excluded by a CSV of matric numbers.
* Refused while any department with active students has no programme
  length, since its final year would be a guess.
* The academic year comes from the active semester's name ("2026/2027 First
  Semester" -> "2026/2027"). PromotionRun.academic_year is unique, so the
  same year can't be promoted twice.
"""
import json
import re
from collections import Counter
from dataclasses import dataclass, field

from models import db, Department, PromotionRun, Student
from utils import VALID_LEVELS

_CHUNK = 500


class PromotionError(ValueError):
    pass


def academic_year(semester):
    """'2026/2027 First Semester' -> '2026/2027'; None without a year."""
    match = re.search(r'(\d{4})\s*/\s*(\d{4})', semester.name if semester else '')
    return f"{match.group(1)}/{match.group(2)}" if match else None


@dataclass
class PromotionPlan:
    year: str
    moves: dict = field(default_factory=dict)          # new level -> [student id]
    groups: Counter = field(default_factory=Counter)   # (dept, from, to) -> count
    due: list = field(default_factory=list)            # (matric, name, dept, level)
    excluded: list = field(default_factory=list)       # (matric, name, dept, level)
    unknown_exclusions: list = field(default_factory=list)
    missing_years: list = field(default_factory=list)  # department names
    bad_levels: list = field(default_factory=list)     # (matric, name, level)

    @property
    def moving(self):
        return sum(len(ids) for ids in self.moves.values())

    @property
    def ok(self):
        return not self.missing_years and not self.unknown_exclusions


def plan_promotion(semester, excluded_matrics=()):
    year = academic_year(semester)
    if not year:
        raise PromotionError('The active semester has no academic year in its name (like "2026/2027"). '
                             'Rename it on the Semesters page first.')
    plan = PromotionPlan(year=year)
    departments = {d.id: d for d in Department.query.all()}
    excluded = {m.strip().lower() for m in excluded_matrics if m.strip()}
    seen_excluded = set()

    # Plain columns, not ORM objects: 6,000 rows of five values is cheap;
    # 6,000 Student objects with relationships is not.
    rows = (db.session.query(Student.id, Student.matric_number, Student.full_name,
                             Student.level, Student.department_id)
            .filter(Student.status == 'active').order_by(Student.matric_number))
    missing = set()
    for sid, matric, name, level, dept_id in rows:
        dept = departments.get(dept_id)
        dept_name = dept.name if dept else '?'
        if level not in VALID_LEVELS:
            plan.bad_levels.append((matric, name, level))
            continue
        if matric.lower() in excluded:
            seen_excluded.add(matric.lower())
            plan.excluded.append((matric, name, dept_name, level))
            continue
        if not dept or not dept.programme_years:
            missing.add(dept_name)
            continue
        if int(level) >= dept.programme_years * 100:
            plan.due.append((matric, name, dept_name, level))
            continue
        new_level = str(int(level) + 100)
        plan.moves.setdefault(new_level, []).append(sid)
        plan.groups[(dept_name, level, new_level)] += 1

    plan.missing_years = sorted(missing)
    plan.unknown_exclusions = sorted(m for m in excluded if m not in seen_excluded)
    return plan


def current_run(year):
    return PromotionRun.query.filter_by(academic_year=year).first() if year else None


def apply_promotion(plan, run_by):
    """Not committed: the caller commits with its audit entry."""
    if not plan.ok:
        raise PromotionError('This promotion has problems and cannot be run.')
    if current_run(plan.year):
        raise PromotionError(f"Students were already promoted for {plan.year}. Undo that run first "
                             f"if it needs redoing.")
    # One UPDATE per (new level, chunk of 500 ids): a handful of statements
    # for the whole school, not 6,000.
    for new_level, ids in plan.moves.items():
        for i in range(0, len(ids), _CHUNK):
            Student.query.filter(Student.id.in_(ids[i:i + _CHUNK])) \
                .update({Student.level: new_level}, synchronize_session=False)
    db.session.add(PromotionRun(academic_year=plan.year, promoted=plan.moving,
                                moves=json.dumps(plan.moves), run_by=run_by))
    return plan.moving


def undo_promotion(run):
    """Move back everyone this run moved who is still at the level it gave
    them (a level edited since is left alone). Returns how many moved back.
    Not committed."""
    moved_back = 0
    for new_level, ids in json.loads(run.moves).items():
        old_level = str(int(new_level) - 100)
        for i in range(0, len(ids), _CHUNK):
            moved_back += Student.query.filter(Student.id.in_(ids[i:i + _CHUNK]),
                                               Student.level == new_level) \
                .update({Student.level: old_level}, synchronize_session=False)
    db.session.delete(run)
    return moved_back


def due_to_graduate():
    """Active students at or past their department's final level, for the
    "download the list" link -- ready to upload to Change Status (CSV)."""
    out = []
    for matric, name, level, years, dept_name in (
            db.session.query(Student.matric_number, Student.full_name, Student.level,
                             Department.programme_years, Department.name)
            .join(Department, Student.department_id == Department.id)
            .filter(Student.status == 'active', Department.programme_years.isnot(None))
            .order_by(Department.name, Student.matric_number)):
        if level in VALID_LEVELS and int(level) >= years * 100:
            out.append((matric, name, dept_name, level))
    return out
