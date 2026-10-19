"""Render smoke tests for every page template.

Paired with test_templates.py, which checks the things that are cheap to
check statically. This one actually RENDERS each page with a synthetic
context, because the failures that matter most here are invisible to a parse
check:

  * a macro used but not imported  -- `{% from '_macros.html' import ... %}`
    missing an entry parses perfectly and blows up on the first request
  * a variable the template reads that the route never supplies
  * a data-tone value with no matching rule in input.css

The context for each page is written by hand rather than auto-generated. An
auto-vivifying mock would make every template "pass" while proving nothing,
since a permissive object answers every attribute access.

Run with:  python tests/render_check.py
(add a page with:  python tests/render_check.py --add <template>)
"""

import pathlib
import sys
import warnings
from types import SimpleNamespace
from datetime import date, datetime, time

warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as application  # noqa: E402

fa = application.app


class Dept:
    """Stand-in for a Department row, for pages that read `.name` off a single
    department object (the HOD portal). Jinja's attribute lookup falls back to
    getitem, so nested dicts work too -- this class exists so the HOD entries
    say "this is one object, and only .name is real" instead of looking like
    the rest of a department dict."""

    def __init__(self, name):
        self.name = name


def _dash_slot(slot_id, code, start, end, room, status, present, enrolled, reminded_at=None):
    """One row of the dashboard's today["slots"] (see dashboard_today.today)."""
    h1, m1 = map(int, start.split(":"))
    h2, m2 = map(int, end.split(":"))
    return {
        "slot": {"id": slot_id, "start_time": time(h1, m1), "end_time": time(h2, m2), "room": room},
        "course": {"course_code": code, "course_title": "Course " + code, "lecturer_names": "Dr. Amina Yusuf",
                   "lecturer_summary": "Dr. Amina Yusuf"},
        "status": status, "present": present, "enrolled": enrolled, "reminded_at": reminded_at,
    }


# The Courses catalog (admin/courses.html): one course with a coordinator and
# a co-lecturer, one general course with no semester and no lecturer.
_COURSES = [
    {
        "id": 1, "course_code": "CPE401", "course_title": "Embedded Systems",
        "department": {"name": "Computer Engineering"}, "department_id": 1, "semester_id": 1,
        "lecturer": {"full_name": "Dr. Jane Doe", "staff_id": "STF/1"},
        "all_lecturers": [{"full_name": "Dr. Jane Doe", "staff_id": "STF/1"},
                          {"full_name": "Dr. Ade Bello", "staff_id": "STF/7"}],
        "credit_units": 3,
    },
    {
        "id": 2, "course_code": "GST212", "course_title": "Philosophy and Logic",
        "department": None, "department_id": None, "semester_id": None,
        "lecturer": None, "all_lecturers": [], "credit_units": None,
    },
]


_DASH_SLOTS = [
    _dash_slot(1, "CSC 201", "08:00", "10:00", "LT 2", "ended", 142, 156),
    _dash_slot(2, "MCT 401", "09:00", "11:00", "LT 1", "live", 74, 88),
    _dash_slot(3, "MCT 405", "10:00", "12:00", "LT 3", "late", None, 66),
    _dash_slot(4, "EEE 305", "10:00", "11:00", None, "late", None, 40,
               reminded_at=datetime(2026, 10, 8, 9, 35)),
    _dash_slot(5, "PHY 101", "10:30", "12:00", "LT 4", "due", None, 200),
    _dash_slot(6, "MEE 307", "07:00", "09:00", "Lab B", "missed", None, 43),
    _dash_slot(7, "GST 211", "14:00", "16:00", "Main Hall", "upcoming", None, 312),
]


def _pagination(total, page, pages, per_page=50):
    """Stand-in for Flask-SQLAlchemy's Pagination: just the attributes the
    paginated admin pages (students, activity) read."""
    first = (page - 1) * per_page + 1
    return {
        "total": total, "page": page, "pages": pages,
        "first": first, "last": min(first + per_page - 1, total),
        "has_prev": page > 1, "has_next": page < pages,
        "prev_num": page - 1, "next_num": page + 1,
    }


def _timetable_import_plan():
    """A preview with one good class, one shared class and one with errors,
    built from the real dataclasses so the template is checked against them."""
    from types import SimpleNamespace
    from timetable_import import ImportPlan, SheetPlan, PlannedSlot
    course = SimpleNamespace(id=1, course_title="Control Systems", course_code="MCT401")
    ok = PlannedSlot("MCT401", "L", 0, time(8), time(10), "LR 1", course=course)
    shared = PlannedSlot("GST212", "L", 1, time(15), time(17), "MAIN HALL",
                         course=SimpleNamespace(id=2, course_title="Logic", course_code="GST212"),
                         shared_with=["Electrical · 200 level"])
    bad = PlannedSlot("NOPE999", "T", 3, time(9), time(10), "",
                      errors=["No course NOPE999 in 2025/2026 Second Semester. Create it on the Courses page, then upload again."])
    sheet = SheetPlan("acc200.pdf", "Accounting", 200, "Second Semester 2025/2026",
                      slots=[ok, shared, bad],
                      notes=["Mon 09:00: couldn't read \"X\" -- skipped."])
    broken = SheetPlan("scan.pdf", errors=["This PDF has 4 pages. The timetable must be on ONE landscape page."])
    return ImportPlan(semester_id=1, sheets=[sheet, broken])


def _bulk_course_plan():
    """A course-upload preview with a new row, an existing one and an error,
    built from the real dataclasses (bulk_upload.py)."""
    from bulk_upload import BulkPlan, BulkRow
    new = BulkRow(2, {"course_code": "MCT401", "course_title": "Control Systems",
                      "department": "Mechatronics", "credit_units": "3", "lecturers": "STF/1; STF/2"},
                  resolved={"lecturer_names": ["Dr Ade", "Dr Bola"]})
    exists = BulkRow(3, {"course_code": "GST212", "course_title": "Logic", "department": "",
                         "credit_units": "", "lecturers": "STF/3"},
                     status="exists", note="Already in 2025/2026 Second Semester -- skipped, not changed.")
    bad = BulkRow(4, {"course_code": "MCT405", "course_title": "Robotics", "department": "Mechatronics",
                      "credit_units": "x", "lecturers": "STF/9"},
                  status="error", errors=["No lecturer with staff ID STF/9. Upload the lecturers file first."])
    return BulkPlan("courses", "courses.csv", [new, exists, bad], semester_id=1)


def _promotion_plan():
    """A promotion preview with movers, a repeater and an odd level."""
    from collections import Counter
    from promotion import PromotionPlan
    return PromotionPlan(
        year="2026/2027", moves={"400": [1, 2]},
        groups=Counter({("Mechatronics", "300", "400"): 2}),
        due=[("MCT/21/0009", "Bola", "Mechatronics", "500")],
        excluded=[("MCT/22/0003", "Chidi", "Mechatronics", "300")],
        bad_levels=[("MCT/22/0004", "Dayo", "400L")],
    )


def _timetable_grid_with_a_draft():
    from types import SimpleNamespace
    entry = SimpleNamespace(
        id=1, course_id=1, day_of_week=0, start_time=time(8), end_time=time(10),
        room="LR 1", semester_id=1, semester=SimpleNamespace(name="2025/2026 Second Semester"),
        type="scheduled", is_published=False,
        course=SimpleNamespace(course_code="MCT401", course_title="Control Systems",
                               lecturer_names="Dr Ade, Dr Bola"))
    placed = {"entry": entry, "day_col": 2, "row_start": 1, "row_span": 4,
              "width_pct": 100, "left_pct": 0, "lane_count": 1, "today_status": None}
    grid = {"placed": [placed], "today_weekday": 0, "total_rows": 20,
            "hour_labels": [f"{h:02d}:00" for h in range(8, 18)]}
    return [entry], grid


def render(template, spec):
    """Render one template with a synthetic session + context."""
    from flask import session

    role = spec.get("role", "admin")
    with fa.test_request_context("/"):
        session["user_id"] = 1
        session["role"] = role
        session["username"] = "smoke"
        ctx = {k: v for k, v in spec.items() if k != "role"}
        return fa.jinja_env.get_template(template).render(**ctx)


# --------------------------------------------------------------------------
# One entry per page. `role` picks the session role so the right portal
# context (and therefore the right rail) is exercised.
# --------------------------------------------------------------------------
CONTEXTS = {
    # One slot in every status, so each pill, the late banner (with and
    # without a reminder already sent) and the progress cell all render.
    "admin/dashboard.html": dict(
        role="admin",
        active_page="dashboard",
        active_semester={"name": "2026/2027 First Semester"},
        today={
            "now": datetime(2026, 10, 8, 10, 40),
            "alerts": [r for r in _DASH_SLOTS if r["status"] == "late"],
            "slots": _DASH_SLOTS,
            "live": [{"room": "LT 1"}, {"room": None}],
            "checkins": {"count": 216, "expected": 244, "pct": 89,
                         "by_method": [("nfc", 170), ("ble", 30), ("manual", 10), ("unknown", 6)]},
        },
        department_attendance=[
            {"name": "Systems Eng", "percentage": 82.0},
            {"name": "Comp Sci", "percentage": 47.0},
        ],
        recent_checkins=[
            {"method": "nfc", "time_in": datetime(2026, 10, 8, 9, 39),
             "student": {"full_name": "Chinedu O'Brien"},
             "session": {"room": "LT 1", "course": {"course_code": "MCT 401"}}},
            {"method": None, "time_in": datetime(2026, 10, 8, 8, 10),
             "student": {"full_name": "Grace Akpan"},
             "session": {"room": None, "course": {"course_code": "CSC 201"}}},
        ],
        relative_time=lambda dt: "just now",
    ),

    # --- The light-theme redesign pages ---------------------------------
    # Plain dicts stand in for the SQLAlchemy rows: Jinja's attribute lookup
    # falls back to getitem, so `a.department.name` resolves against nested
    # dicts. Only `created_at` / `start_date` / `end_date` must be real
    # objects, because the templates call .strftime() on them -- a string
    # there would render the page but never exercise the date path.

    # Two students below the threshold (one in two courses, an apostrophe in
    # a name), both roll-ups, and a delivery table with a missed, a clean
    # and a general (no department) course.
    "admin/analytics.html": dict(
        role="admin",
        active_page="analytics",
        active_semester={"name": "2026/2027 First Semester"},
        # A PAST semester is picked, so the picker, the "(past semester)"
        # subtitle and the note under the filters all render.
        semester={"id": 1, "name": "2025/2026 Second Semester", "is_active": False},
        semesters=[{"id": 2, "name": "2026/2027 First Semester", "is_active": True},
                   {"id": 1, "name": "2025/2026 Second Semester", "is_active": False}],
        departments=[{"id": 1, "name": "Mechatronics"}, {"id": 2, "name": "Computer Science"}],
        valid_levels=["100", "200", "300", "400", "500"],
        filters={"dept": None, "level": ""},
        list_limit=1,
        eligibility={
            "threshold": 75, "min_sessions": 3, "pairs_below": 3,
            "students": [
                {"student": {"full_name": "Chinedu O'Brien", "matric_number": "MCT/22/0789", "level": "400",
                             "department": {"name": "Mechatronics"}},
                 "courses": [{"course": {"course_code": "MCT 401"}, "attended": 4, "held": 10, "pct": 40.0},
                             {"course": {"course_code": "MCT 405"}, "attended": 6, "held": 9, "pct": 66.7}]},
                {"student": {"full_name": "Grace Akpan", "matric_number": "CSC/23/0111", "level": "300",
                             "department": None},
                 "courses": [{"course": {"course_code": "CSC 301"}, "attended": 7, "held": 10, "pct": 70.0}]},
            ],
            "by_department": [{"name": "Mechatronics", "below": 1, "total": 40},
                              {"name": "Computer Science", "below": 12, "total": 30}],
            "by_level": [{"level": "300", "below": 1, "total": 25}, {"level": "400", "below": 1, "total": 45}],
        },
        delivery={
            "teaching_start": date(2026, 9, 14),
            "courses": [
                {"course": {"course_code": "MCT 401", "course_title": "Robotics", "department": {"name": "Mechatronics"}},
                 "timetabled": 10, "held": 6, "missed": 4, "extra": 1, "rate": 60},
                {"course": {"course_code": "GST 211", "course_title": "Entrepreneurship", "department": None},
                 "timetabled": 5, "held": 4, "missed": 1, "extra": 0, "rate": 80},
                {"course": {"course_code": "CSC 301", "course_title": "Algorithms", "department": {"name": "Computer Science"}},
                 "timetabled": 8, "held": 8, "missed": 0, "extra": 0, "rate": 100},
                # Added today: nothing due yet, so no rate (crashed the page
                # in production on 2026-10-15).
                {"course": {"course_code": "PHY 101", "course_title": "Physics", "department": {"name": "Physics"}},
                 "timetabled": 0, "held": 0, "missed": 0, "extra": 0, "rate": None},
            ],
            "by_department": [{"name": "Mechatronics", "timetabled": 10, "held": 6, "missed": 4, "rate": 60},
                              {"name": "Computer Science", "timetabled": 8, "held": 8, "missed": 0, "rate": 100},
                              {"name": "Physics", "timetabled": 0, "held": 0, "missed": 0, "rate": None}],
        },
    ),

    # A just-created reader (so the one-time secret banner renders), one
    # online, one disabled, one never seen.
    "admin/terminals.html": dict(
        role="admin",
        active_page="terminals",
        active_semester=None,
        terminals=[
            {"id": 1, "code": "T-01", "name": "LT 1 front door", "room": "LT 1", "ble_number": 1,
             "is_active": True, "last_seen_at": datetime(2026, 10, 16, 9, 30)},
            {"id": 2, "code": "T-02", "name": "Main Hall", "room": None, "ble_number": None,
             "is_active": False, "last_seen_at": None},
            {"id": 3, "code": "T-03", "name": "Lab B", "room": "Eng. Lab B", "ble_number": 3,
             "is_active": True, "last_seen_at": datetime(2026, 10, 15, 16, 0)},
        ],
        online={1},
        # admin._secret_fingerprint per reader, for the New secret forms.
        fingerprints={1: "a1b2c3d4e5f60718", 2: "0f1e2d3c4b5a6978", 3: "1122334455667788"},
        rooms=["Eng. Lab B", "LT 1", "LT 2"],
        room_check_mode="flag",
        shared_secret_set=True,
        new_secret="x" * 43,
        new_secret_for={"code": "T-01", "ble_number": 1},
        relative_time=lambda dt: "2 min ago",
    ),

    "admin/announcements.html": dict(
        role="admin",
        active_page="announcements",
        active_semester=None,
        announcements=[
            {
                "id": 1,
                "title": "Midterm Examination Schedule",
                "body": "Timetable published. Candidates report 30 minutes early.",
                "created_at": datetime(2026, 9, 28, 9, 15),
                "scope": "university",
                "department": None,
                "course": None,
                "is_active": True,
            },
            {
                "id": 2,
                "title": "Lab rescheduled",
                "body": "Moved to the new lab block.",
                "created_at": datetime(2026, 9, 20, 14, 0),
                "scope": "department",
                "department": {"name": "Systems Engineering"},
                "course": None,
                "is_active": True,
            },
            {
                "id": 3,
                "title": "Grading scale clarification",
                "body": "Withdrawn from the notice board.",
                "created_at": datetime(2026, 8, 2, 11, 30),
                "scope": "course",
                "department": None,
                "course": {"course_code": "CPE401"},
                "is_active": False,
            },
        ],
        departments=[{"id": 1, "name": "Systems Engineering"}],
        courses=[{"id": 1, "course_code": "CPE401", "course_title": "Embedded Systems"}],
        # Students each choice would notify (admin.announcements_page).
        audience={"university": 6240, "departments": {1: 812}, "courses": {1: 156}},
    ),

    "admin/courses.html": dict(
        role="admin",
        active_page="courses",
        active_semester=None,
        courses=_COURSES,
        semester_courses=_COURSES,
        # Course 1 has two lecturers (coordinator + co-lecturer); course 2,
        # a general course with no semester, has none.
        enrolled={1: 2},
        view_semester={"id": 1, "name": "2025/2026 First Semester"},
        filters={"q": "", "dept": 1},
        filter_args={"semester": 1, "dept": 1},
        is_filtered=True,
        departments=[
            {"id": 1, "name": "Computer Engineering"},
            {"id": 2, "name": "Systems Engineering"},
        ],
        lecturers=[{"id": 1, "full_name": "Dr. Jane Doe"}],
        # Two semesters, so the copy card renders with its default source.
        semesters=[{"id": 1, "name": "2025/2026 First Semester", "is_active": True},
                   {"id": 2, "name": "2024/2025 First Semester", "is_active": False}],
        copy_source={"id": 2, "name": "2024/2025 First Semester"},
        # Course 1 can't be deleted (greyed out); course 2 can.
        delete_blockers={1: "Has 12 class sessions."},
    ),

    "admin/hods.html": dict(
        role="admin",
        active_page="hods",
        active_semester=None,
        # One row per department: an HOD with a set password, a promoted
        # lecturer now on leave (sign-in off), one pending setup, and a
        # department with no HOD at all.
        rows=[
            {"department": {"id": 1, "name": "Systems Engineering"},
             "hod": {"id": 1, "full_name": "Prof. Adaeze Nwosu", "staff_id": "HOD-2001", "department_id": 1,
                     "user_id": 11, "user": {"requires_password_change": False, "is_active": True}}},
            {"department": {"id": 2, "name": "Computer Engineering"},
             "hod": {"id": 2, "full_name": "Dr. Emeka Obi", "staff_id": "HOD-2002", "department_id": 2,
                     "user_id": 12, "user": {"requires_password_change": True, "is_active": True}}},
            {"department": {"id": 3, "name": "Mechatronics"},
             "hod": {"id": 3, "full_name": "Dr. Tunde Cole", "staff_id": "LECT-1007", "department_id": 3,
                     "user_id": 13, "user": {"requires_password_change": False, "is_active": False}}},
            {"department": {"id": 4, "name": "Aerospace"}, "hod": None},
        ],
        hod_count=3,
        free_departments=[{"id": 4, "name": "Aerospace"}],
        departments=[
            {"id": 1, "name": "Systems Engineering"},
            {"id": 2, "name": "Computer Engineering"},
            {"id": 3, "name": "Mechatronics"},
            {"id": 4, "name": "Aerospace"},
        ],
        # HODs 1 and 3 are promoted lecturers: their dialogs get the per-row
        # note, and HOD 3's lecturer is on leave, so its login is off.
        hod_lecturers={11: {"status": "active"}, 13: {"status": "on_leave"}},
        lecturer_statuses={"active": "Active", "on_leave": "On leave", "left": "Left"},
        # Deliberately non-empty: the promote branch renders a `<select>` whose
        # options dereference .department.name, which an empty list would skip.
        promotable_lecturers=[
            {
                "id": 7,
                "full_name": "Dr. Ade Bello",
                "staff_id": "LECT-1009",
                "department": {"name": "Systems Engineering"},
            }
        ],
    ),

    "admin/lecturers.html": dict(
        role="admin",
        active_page="lecturers",
        lecturer_statuses={"active": "Active", "on_leave": "On leave", "left": "Left"},
        delete_blockers={1: "Coordinates CPE401. Make someone else coordinator first."},
        active_semester=None,
        lecturers=[
            {
                "id": 1,
                "full_name": "Dr. Jane Doe",
                "staff_id": "LECT-1002",
                "status": "on_leave",
                "department": {"name": "Computer Engineering"},
                "department_id": 1,
                "user": {"requires_password_change": False},
            },
            {
                "id": 2,
                "full_name": "Dr. Tunde Cole",
                "staff_id": "LECT-1007",
                "status": "active",
                "department": None,
                "department_id": None,
                "user": {"requires_password_change": True},
            },
        ],
        departments=[{"id": 1, "name": "Computer Engineering"}],
        # Filtered, so the selected department and the Clear link render.
        course_counts={1: 3},
        filters={"q": "", "dept": 1},
        filter_args={"dept": 1},
        is_filtered=True,
    ),

    # The two signed-out pages (STANDALONE: no rail). The login page with a
    # username kept from a failed attempt.
    "auth/login.html": dict(role="admin", username="CPE/20/1123"),
    "auth/change_password.html": dict(role="admin"),

    "admin/organization.html": dict(
        role="admin",
        active_page="organization",
        active_semester=None,
        # Counts come precomputed from _organization_counts() (GROUP BY
        # queries), not from the relationship lists, so the rows only need
        # ids and names.
        # One faculty and department in use (no delete button: "In use"),
        # one empty of each (delete button + modal).
        faculties=[{"id": 1, "name": "Faculty of Engineering"}, {"id": 2, "name": "Faculty of Arts"}],
        faculty_counts={1: {"departments": 1, "students": 3, "lecturers": 2, "courses": 5, "hods": 1}},
        programme_years=(4, 5),
        departments=[
            {"id": 1, "name": "Computer Engineering", "programme_years": None,
             "faculty": {"name": "Faculty of Engineering"}},
            {"id": 2, "name": "History", "programme_years": 4, "faculty": {"name": "Faculty of Arts"}},
        ],
        dept_counts={1: {"students": 3, "lecturers": 2, "courses": 5, "hods": 1},
                     2: {"students": 0, "lecturers": 0, "courses": 0, "hods": 0}},
    ),

    "admin/reports.html": dict(
        role="admin",
        active_page="reports",
        active_semester=None,
        # Three values chosen to land in each tier of grade_tone() -- success,
        # warning and error -- so a colour-mapping regression shows up here.
        course_reports=[
            {
                "course": {"course_code": "CPE401", "course_title": "Embedded Systems"},
                "lecturer_name": "Dr. Jane Doe",
                "department_name": "Computer Engineering",
                "enrolled_count": 48,
                "session_count": 12,
                "average_attendance": 88.0,
            },
            {
                "course": {"course_code": "SEE310", "course_title": "Control Systems"},
                "lecturer_name": "Dr. Tunde Cole",
                "department_name": "Systems Engineering",
                "enrolled_count": 61,
                "session_count": 9,
                "average_attendance": 62.5,
            },
            {
                "course": {"course_code": "MEE205", "course_title": "Thermodynamics"},
                "lecturer_name": "Engr. Sam Kalu",
                "department_name": "Mechanical Engineering",
                "enrolled_count": 40,
                "session_count": 7,
                "average_attendance": 34.0,
            },
        ],
        semester={"id": 1, "name": "2025/2026 First Semester"},
        semesters=[{"id": 1, "name": "2025/2026 First Semester", "is_active": True},
                   {"id": 2, "name": "2024/2025 First Semester", "is_active": False}],
    ),

    "admin/semesters.html": dict(
        role="admin",
        active_page="semesters",
        active_semester=None,
        semesters=[
            {
                "id": 1,
                "name": "2025/2026 First Semester",
                "start_date": date(2025, 9, 1),
                "end_date": date(2026, 1, 30),
                "is_active": True,
            },
            {
                "id": 2,
                "name": "2025/2026 Second Semester",
                "start_date": date(2026, 2, 9),
                "end_date": date(2026, 7, 31),
                "is_active": False,
            },
        ],
        # Semester 2 is empty: its Set Active form carries 0 / 0 for the warning.
        course_counts={1: 10},
        slot_counts={1: 42},
    ),

    "admin/students.html": dict(
        role="admin",
        active_page="students",
        active_semester=None,
        students=[
            {
                "id": 1,
                "full_name": "Aisha Bello",
                "matric_number": "CPE/20/1123",
                "level": "400L",
                "department": {"name": "Computer Engineering"},
                "department_id": 1,
                "rfid_uid": "04A1B2C3",
                "device_id": "android-abc123",
                "status": "active",
                "user": {"requires_password_change": False},
            },
            {
                "id": 2,
                # An apostrophe on purpose: students.html's unbind confirm()
                # reads the name from data-student-name specifically because
                # an inline onsubmit handler would mis-parse this string.
                "full_name": "Chinedu O'Brien",
                "matric_number": "SEE/21/0044",
                "level": "300L",
                "status": "graduated",
                "department": {"name": "Systems Engineering"},
                "department_id": 2,
                "rfid_uid": None,
                "device_id": None,
                "user": {"requires_password_change": True},
            },
        ],
        departments=[
            {"id": 1, "name": "Computer Engineering"},
            {"id": 2, "name": "Systems Engineering"},
        ],
        # Added when the roster gained search, filters and pages -- this
        # entry was never updated, so the page failed to render here.
        # pages=2 so the Previous/Next footer is exercised too.
        pagination=_pagination(total=60, page=1, pages=2),
        levels=["100", "200", "300", "400", "500"],
        valid_levels=["100", "200", "300", "400", "500"],
        filters={"q": "", "dept": None, "level": "", "device": "", "status": ""},
        student_statuses={"active": "Active", "suspended": "Suspended", "graduated": "Graduated"},
        delete_blockers={1: "Has 4 attendance records. Use Status instead."},
        filter_args={},
        is_filtered=False,
    ),

    # Yearly promotion page, at the preview step (promotion.py).
    "admin/promotion.html": dict(
        role="admin",
        active_page="students",
        semester={"id": 1, "name": "2026/2027 First Semester"},
        year="2026/2027",
        run=None,
        missing_years=[],
        plan=_promotion_plan(),
        excluded_json='["MCT/22/0003"]',
    ),

    # CSV status change preview (bulk_status in blueprints/admin.py), with an
    # unknown ID and a blocked lecturer so the warning branch renders.
    "admin/status_preview.html": dict(
        role="admin",
        active_page="lecturers",
        kind="lecturers",
        names={"active": "Active", "on_leave": "On leave", "left": "Left"},
        status="left",
        reason="Resigned",
        changing=[{"id": 1, "full_name": "Dr Ade", "staff_id": "STF/1", "status": "active"}],
        unchanged=0,
        missing=["STF/404"],
        blocked={1: "MCT401"},
        ids_json="[]",
        back_url="/admin/lecturers",
    ),

    # Lecturer/course CSV upload preview (bulk_upload.py).
    "admin/bulk_preview.html": dict(
        role="admin",
        active_page="courses",
        plan=_bulk_course_plan(),
        semester={"id": 1, "name": "2025/2026 Second Semester"},
        plan_json="{}",
        back_url="/admin/courses",
    ),

    "admin/timetable_import.html": dict(
        role="admin",
        active_page="timetable",
        active_semester=None,
        plan=_timetable_import_plan(),
        semester={"id": 1, "name": "2025/2026 Second Semester"},
        plan_json="{}",
        day_names=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        kind_names={"L": "Lecture", "T": "Tutorial", "P": "Practical"},
    ),

    # Added with the PDF import: the import card and the "Draft" label on
    # grid chips. The page had no render check before.
    "admin/timetable.html": dict(
        role="admin",
        active_page="timetable",
        active_semester={"id": 1, "name": "2025/2026 Second Semester"},
        timetable_entries=_timetable_grid_with_a_draft()[0],
        grid=_timetable_grid_with_a_draft()[1],
        courses=[{"id": 1, "course_code": "MCT401", "course_title": "Control Systems"}],
        # Two semesters, so the "Copy a previous timetable" card renders.
        semesters=[{"id": 1, "name": "2025/2026 Second Semester"},
                   {"id": 2, "name": "2024/2025 Second Semester"}],
        copy_source={"id": 2, "name": "2024/2025 Second Semester"},
        weekday_names=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        # The grid view (one department + level). The coverage view is
        # rendered for real by tests/test_timetable_view.py.
        view={"is_grid": True, "semester_id": 1, "semester": {"id": 1, "name": "2025/2026 Second Semester"},
              "dept": "1", "level": "400", "dept_name": "Mechatronics",
              "args": {"semester": 1, "dept": "1", "level": "400"}},
        departments=[{"id": 1, "name": "Mechatronics"}],
        levels=("100", "200", "300", "400", "500"),
        draft_count=1,
        draft_semesters=[(SimpleNamespace(id=1, name="2025/2026 Second Semester"), 1, 1)],
        import_max_files=10,
    ),

    "admin/activity.html": dict(
        role="admin",
        active_page="activity",
        active_semester=None,
        # (entry, tone) pairs, as activity_page() builds them. One of each
        # pill tone the page uses, so a missing data-tone rule shows up.
        entries=[
            ({"actor_label": "tunde", "created_at": datetime(2026, 10, 12, 9, 5),
              "summary": "Created student Ada Obi (MCT/19/0001)",
              "action": "student.create"}, "success"),
            ({"actor_label": "amaka", "created_at": datetime(2026, 10, 12, 8, 40),
              "summary": "Deleted department Physics and everything under it (3 students)",
              "action": "department.delete"}, "error"),
            ({"actor_label": "cli:N9ne", "created_at": datetime(2026, 10, 11, 18, 0),
              "summary": "Failed sign-in attempt for tunde",
              "action": "auth.login_failed"}, "warning"),
            ({"actor_label": "tunde", "created_at": datetime(2026, 10, 11, 17, 0),
              "summary": "tunde set a new password",
              "action": "auth.password_change"}, "neutral"),
        ],
        pagination=_pagination(total=120, page=2, pages=3),
        people=["amaka", "cli:N9ne", "tunde"],
        categories={"auth": "Sign-ins & passwords", "student": "Students"},
        filters={"who": "tunde", "what": ""},
        filter_args={"who": "tunde"},
        is_filtered=True,
    ),

    # ---- HOD portal (blueprints/hod.py) ---------------------------------
    # hod_department and the has_* flags come from inject_portal_context,
    # which app.py registers app-wide. sidebar_courses and active_semester
    # are read by base_portal.html's rail even on HOD pages, so they have to
    # be present or the rail is what fails -- not the page.
    "hod/dashboard.html": dict(
        role="hod",
        active_page="dashboard",
        active_semester=None,
        has_hod_profile=True,
        has_lecturer_profile=False,
        hod_department=Dept("Systems Engineering"),
        sidebar_courses=[],
        department=Dept("Systems Engineering"),
        active_sessions=[
            {"course": {"course_code": "SEN 301"}},
            {"course": {"course_code": "SEN 411"}},
        ],
        lecturer_count=4,
        student_count=218,
        course_count=17,
        flagged_count=11,
    ),

    "hod/levels.html": dict(
        role="hod",
        active_page="levels",
        active_semester=None,
        has_hod_profile=True,
        has_lecturer_profile=False,
        hod_department=Dept("Systems Engineering"),
        sidebar_courses=[],
        department=Dept("Systems Engineering"),
        level_sections=[
            {
                "level": 100,
                "lecturer_count": 2,
                "course_count": 2,
                "student_count": 46,
                "courses": [
                    {"code": "SEN 101", "title": "Intro to Programming",
                     "units": 3, "lecturer": "Dr. A. Bello"},
                    # units is nullable on Course, so exercise the em-dash
                    # branch alongside the normal one.
                    {"code": "SEN 102", "title": "Discrete Maths",
                     "units": None, "lecturer": "Unassigned"},
                ],
            },
            {
                # A level with students but zero courses -- the other half of
                # the {% if lvl.courses %} else branch.
                "level": 300,
                "lecturer_count": 0,
                "course_count": 0,
                "student_count": 30,
                "courses": [],
            },
        ],
    ),

    "hod/students.html": dict(
        role="hod",
        active_page="students",
        active_semester=None,
        has_hod_profile=True,
        has_lecturer_profile=False,
        hod_department=Dept("Systems Engineering"),
        sidebar_courses=[],
        department=Dept("Systems Engineering"),
        levels_present=[100, 300, 500],
        selected_level=300,
        flagged_count=1,
        roster=[
            {
                "name": "Chioma Okafor",
                "matric": "SEN/2021/0007",
                "initial": "C",
                "overall": 71.4,
                "courses": [
                    # One value either side of the 75% at-risk threshold.
                    {"code": "SEN 301", "pct": 62.0},
                    {"code": "SEN 311", "pct": 88.0},
                ],
            },
            {
                # overall is None in the route whenever the student has no
                # sessions held anywhere; the template must not compare it.
                "name": "Bayo Ade",
                "matric": "SEN/2021/0012",
                "initial": "B",
                "overall": None,
                "courses": [],
            },
        ],
    ),

    "hod/signoffs.html": dict(
        role="hod",
        active_page="signoffs",
        active_semester=None,
        has_hod_profile=True,
        has_lecturer_profile=False,
        hod_department=Dept("Systems Engineering"),
        sidebar_courses=[],
        # Taken by the route but never read by the template; passed anyway so
        # the entry matches what hod.signoffs() actually supplies.
        department=Dept("Systems Engineering"),
    ),

    # ---- Student portal (blueprints/student.py) --------------------------
    # student_profile is a plain dict on the route, not a row -- see the
    # `_student_profile` construction in blueprints/student.py::dashboard.
    "student/dashboard.html": dict(
        role="student",
        active_page="dashboard",
        active_semester=None,
        student_profile={
            "full_name": "Nneka Obi",
            "matric_number": "SEN/2021/0042",
            "department": "Systems Engineering",
            "level": "300",
            "rfid_uid": "04A1B2C3",
        },
        enrollment_count=2,
        attendance_count=19,
        overall_rate=76.0,
        at_risk_count=1,
        courses=[
            {"code": "SEN 301", "name": "Signals & Systems", "pct": 92.0,
             "lecturer_name": "Dr. A. Bello", "credit_units": 3,
             "attended": 11, "total": 12},
            {"code": "SEN 311", "name": "Embedded Systems", "pct": 61.5,
             "lecturer_name": "Mr. T. Lawal", "credit_units": 4,
             "attended": 8, "total": 13},
        ],
        # All four statuses, so every branch of attendance_status_pill renders
        # (excused was the one the old copies showed red, like absent).
        recent_attendance=[
            {"course": "SEN 301", "course_title": "Signals & Systems",
             "date": "14 Sep 2026", "time": "09:00", "status": "present"},
            {"course": "SEN 311", "course_title": "Embedded Systems",
             "date": "13 Sep 2026", "time": "14:00", "status": "late"},
            {"course": "SEN 311", "course_title": "Embedded Systems",
             "date": "12 Sep 2026", "time": "14:00", "status": "absent"},
            {"course": "SEN 301", "course_title": "Signals & Systems",
             "date": "11 Sep 2026", "time": "09:00", "status": "excused"},
        ],
    ),

    "student/my_courses.html": dict(
        role="student",
        active_page="my_courses",
        active_semester=None,
        courses=[
            {"code": "SEN 301", "name": "Signals & Systems", "pct": 92.0,
             "lecturer_name": "Dr. A. Bello", "credit_units": 3,
             "attended": 11, "total": 12},
            # lecturer_name and credit_units are both nullable on the route
            # (unassigned course), so the meta row has to cope with neither.
            {"code": "SEN 311", "name": "Embedded Systems", "pct": 61.5,
             "lecturer_name": None, "credit_units": None,
             "attended": 8, "total": 13},
        ],
    ),

    "student/attendance_history.html": dict(
        role="student",
        active_page="attendance_history",
        active_semester=None,
        attendance_log=[
            {"course_code": "SEN 301", "course_title": "Signals & Systems",
             "date": "14 Sep 2026", "time": "09:00", "status": "present"},
            {"course_code": "SEN 311", "course_title": "Embedded Systems",
             "date": "13 Sep 2026", "time": "14:00", "status": "absent"},
        ],
    ),

    "student/announcements.html": dict(
        role="student",
        active_page="announcements",
        active_semester=None,
        announcements=[
            {"title": "Mid-semester exam timetable is up",
             "body": "Report to your assigned hall 30 minutes early.",
             "created_at": datetime(2026, 9, 28, 9, 15),
             "scope": "course",
             "course": {"course_code": "SEN 301"}},
            # A course-scoped notice whose course row is gone: scope.course
            # may be absent, so the template has to fall back to a label.
            {"title": "Lab slot moved",
             "body": "Venue changed for next week.",
             "created_at": datetime(2026, 9, 26, 11, 0),
             "scope": "course",
             "course": None},
            {"title": "Registration opens Monday",
             "body": "Course registration for the next semester opens Monday.",
             "created_at": datetime(2026, 9, 20, 12, 0),
             "scope": "university",
             "course": None},
        ],
    ),

    # ---- Lecturer portal (blueprints/lecturer.py) ------------------------
    # base_portal.html's rail reads has_hod_profile / has_lecturer_profile /
    # hod_department / sidebar_courses / active_semester / active_course_id on
    # EVERY page, and those come from inject_portal_context in app.py rather
    # than from the lecturer routes. Missing them fails the rail, not the page,
    # so they are repeated in each entry -- see the HOD block above.

    "lecturer/dashboard.html": dict(
        role="lecturer",
        active_page="dashboard",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
            {"id": 2, "course_code": "CSC 405", "course_title": "Compiler Design"},
        ],
        # One live session so the live banner branch renders rather than the
        # page quietly testing only the idle path.
        active_sessions=[
            {"course_id": 1, "course": {"id": 1, "course_code": "CSC 401",
                                        "course_title": "Artificial Intelligence"}},
        ],
        today_checkins=34,
        course_cards=[
            {"course": {"id": 1, "course_code": "CSC 401",
                        "course_title": "Artificial Intelligence"},
             "enrolled_count": 48, "session_count": 9, "is_live": True},
            # is_live False exercises the other branch of the status cell.
            {"course": {"id": 2, "course_code": "CSC 405",
                        "course_title": "Compiler Design"},
             "enrolled_count": 32, "session_count": 7, "is_live": False},
        ],
    ),

    "lecturer/course_workspace.html": dict(
        role="lecturer",
        active_page="course_workspace",
        active_course_id=1,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        course={"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        # Non-null -> the End Session form AND the 5s <meta http-equiv="refresh">
        # render, which is the branch carrying the most DOM contract (#live-search
        # and #live-table-body) to break.
        active_session={"id": 7, "course_id": 1},
        # A POSITIONAL 6-tuple, not an object or a dict -- (full_name, level,
        # department, matric, status, time_in), built that way in the route. A
        # dict would render here and still fail against the real endpoint.
        attendance_records=[
            ("Adebayo Oluwaseun", 400, "Computer Science", "CSC/2021/0451",
             "Present", datetime(2026, 9, 30, 9, 3, 12)),
            ("Chidinma Eze", 400, "Computer Science", "CSC/2021/0452",
             "Late", datetime(2026, 9, 30, 9, 7, 41)),
            ("Ibrahim Musa", 400, "Computer Science", "CSC/2021/0453",
             "Present", datetime(2026, 9, 30, 9, 2, 5)),
            # time_in None exercises the em-dash branch.
            ("Tunde Bakare", 400, "Computer Science", "CSC/2021/0454",
             "Absent", None),
            ("Zainab Bello", 400, "Computer Science", "CSC/2021/0455",
             "Present", datetime(2026, 9, 30, 9, 4, 58)),
        ],
        stats={
            "total_enrolled_students": 48,
            "total_sessions_this_semester": 9,
            "average_attendance": 81.3,
            "present_in_current_session": 4,
        },
        # .start_time / .end_time are read with .strftime('%H:%M'). Left None
        # here so the Start Session form's `if timetable_slot` else-branch is
        # what renders; setting a slot would flip to the pre-filled branch.
        timetable_slot=None,
    ),

    "lecturer/active_sessions.html": dict(
        role="lecturer",
        active_page="active_sessions",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        live_sessions=[
            # started_at_iso set: the inline script ticks this .elapsed-cell.
            {"session_id": 7,
             "course": {"id": 1, "course_code": "CSC 401",
                        "course_title": "Artificial Intelligence"},
             "session_date": date(2026, 9, 30),
             "start_time": time(9, 2),
             "started_at_iso": "2026-09-30T09:02:00+00:00",
             "present_count": 41, "enrolled_count": 48},
            # started_at_iso None: the em-dash branch the script skips over.
            {"session_id": 8,
             "course": {"id": 2, "course_code": "CSC 405",
                        "course_title": "Compiler Design"},
             "session_date": date(2026, 9, 30),
             "start_time": None,
             "started_at_iso": None,
             "present_count": 12, "enrolled_count": 32},
        ],
    ),

    "lecturer/session_history.html": dict(
        role="lecturer",
        active_page="session_history",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        history_sessions=[
            {"session_id": 6,
             "course": {"id": 1, "course_code": "CSC 401",
                        "course_title": "Artificial Intelligence"},
             "date": date(2026, 9, 27), "start_time": time(9, 1),
             "present_count": 44, "absent_count": 4},
            # start_time None -- a legacy session that predates the field.
            {"session_id": 5,
             "course": {"id": 2, "course_code": "CSC 405",
                        "course_title": "Compiler Design"},
             "date": date(2026, 9, 26), "start_time": None,
             "present_count": 27, "absent_count": 5},
        ],
    ),

    "lecturer/session_detail.html": dict(
        role="lecturer",
        active_page="course_workspace",
        active_course_id=1,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        course={"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        session_info={
            "id": 3,  # the mark-present form's action URL needs it
            "session_date": date(2026, 9, 27),
            "start_time": time(9, 1),
            # planned_start None so the nested fallback in the "Started:" line
            # is reachable; stop_time set so the "Ended:" chip renders.
            "planned_start": None,
            "stop_time": time(10, 30),
        },
        # Positional 7-tuples: course_workspace's 6 plus Attendance.method at
        # index 6. This page renders the records TWICE (mobile card list +
        # desktop table) and its search input drives both halves, so a shape
        # error here is the DOM contract's fault. One of each method, so the
        # "Marked by lecturer" / "Via Bluetooth" labels both render.
        attendance_records=[
            ("Adebayo Oluwaseun", 400, "Computer Science", "CSC/2021/0451",
             "Present", datetime(2026, 9, 27, 9, 3, 12), "nfc"),
            ("Chidinma Eze", 400, "Computer Science", "CSC/2021/0452",
             "Late", datetime(2026, 9, 27, 9, 7, 41), "ble"),
            ("Ibrahim Musa", 400, "Computer Science", "CSC/2021/0453",
             "Present", datetime(2026, 9, 27, 9, 2, 5), "manual"),
            ("Tunde Bakare", 400, "Computer Science", "CSC/2021/0454",
             "Absent", None, None),
            ("Zainab Bello", 400, "Computer Science", "CSC/2021/0455",
             "Present", datetime(2026, 9, 27, 9, 4, 58), "nfc"),
            ("Musa Danjuma", 400, "Computer Science", "CSC/2021/0456",
             "Present", datetime(2026, 9, 27, 9, 5, 30), "offline"),
        ],
        enrolled_count=48,
        # The manual-marking list. The apostrophe is deliberate: the confirm
        # prompt reads the name from data-student-name for exactly this case.
        not_checked_in=[
            {"id": 7, "full_name": "Kelechi O'Neil", "matric_number": "CSC/2021/0460"},
        ],
        # Two pending offline taps, so the "Accept all" form (shown only for
        # more than one) renders too. captured_at is naive UTC, as MySQL
        # returns it; the template converts it with the campus filter.
        offline_taps=[
            {"id": 11, "captured_at": datetime(2026, 9, 27, 8, 4, 10),
             "student": {"full_name": "Kelechi O'Neil", "matric_number": "CSC/2021/0460"}},
            {"id": 12, "captured_at": datetime(2026, 9, 27, 8, 6, 2),
             "student": {"full_name": "Amaka Obi", "matric_number": "CSC/2021/0461"}},
        ],
    ),

    "lecturer/reports.html": dict(
        role="lecturer",
        active_page="reports",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        # Two courses either side of the 75% line, so the page's own At Risk
        # count (`selectattr('average_attendance', 'lt', 75)`) is 1 rather than
        # 0 -- the arithmetic in the stat strip actually gets exercised.
        course_reports=[
            {"course": {"id": 1, "course_code": "CSC 401",
                        "course_title": "Artificial Intelligence"},
             "enrolled_count": 48, "session_count": 9, "average_attendance": 81.3},
            {"course": {"id": 2, "course_code": "CSC 405",
                        "course_title": "Compiler Design"},
             "enrolled_count": 32, "session_count": 7, "average_attendance": 64.2},
        ],
        semester={"id": 1, "name": "2025/2026 First Semester"},
        semesters=[{"id": 1, "name": "2025/2026 First Semester", "is_active": True},
                   {"id": 2, "name": "2024/2025 First Semester", "is_active": False}],
    ),

    "lecturer/announcements.html": dict(
        role="lecturer",
        active_page="announcements",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        # sidebar_courses is what the compose form's <select> is built from. It
        # is NOT passed by lecturer.announcements() -- it comes from
        # inject_portal_context -- so this entry would render an empty dropdown
        # without it.
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
            {"id": 2, "course_code": "CSC 405", "course_title": "Compiler Design"},
        ],
        announcements=[
            {"id": 12,
             "title": "Midterm Rescheduled",
             "body": "The CSC 401 midterm moves to Friday 09:00 in Lab B.",
             "created_at": datetime(2026, 9, 29, 14, 5),
             "course": {"id": 1, "course_code": "CSC 401",
                        "course_title": "Artificial Intelligence"},
             "is_active": True},
            # is_active False renders the "Inactive" pill INSTEAD of the delete
            # form, so both branches of that conditional get built.
            {"id": 11,
             "title": "Old notice",
             "body": "Archived notice.",
             "created_at": datetime(2026, 9, 20, 10, 0),
             # .course is nullable on the model -- exercises the fallback
             # branch where no chip renders at all.
             "course": None,
             "is_active": False},
        ],
    ),

    "lecturer/analytics.html": dict(
        role="lecturer",
        active_page="analytics",
        active_course_id=None,
        active_semester=None,
        has_hod_profile=False,
        has_lecturer_profile=True,
        hod_department=None,
        sidebar_courses=[
            {"id": 1, "course_code": "CSC 401", "course_title": "Artificial Intelligence"},
        ],
        overall_avg=72.8,
        best_course={"course": {"id": 1, "course_code": "CSC 401",
                                "course_title": "Artificial Intelligence"},
                      "average_attendance": 81.3},
        worst_course={"course": {"id": 2, "course_code": "CSC 405",
                                 "course_title": "Compiler Design"},
                       "average_attendance": 64.2},
        # .color must be a real hex: the inline script writes it straight into
        # an SVG stroke/fill, so a tone NAME would paint an invisible series.
        # Values match the current ANALYTICS_PALETTE in blueprints/lecturer.py.
        trend_series=[
            {"course_id": 1, "code": "CSC 401",
             "title": "Artificial Intelligence", "color": "#2F6BEE",
             "points": [{"date": "2026-09-06", "pct": 79.2},
                        {"date": "2026-09-13", "pct": 85.4},
                        {"date": "2026-09-20", "pct": 77.1}]},
            # Fewer points and a different date range: exercises the shared
            # x-scale (minT/maxT across series) and the end-label de-collision.
            {"course_id": 2, "code": "CSC 405",
             "title": "Compiler Design", "color": "#A8420F",
             "points": [{"date": "2026-09-08", "pct": 71.9},
                        {"date": "2026-09-15", "pct": 62.5}]},
        ],
        comparison_data=[
            {"course_id": 1, "code": "CSC 401",
             "title": "Artificial Intelligence", "pct": 81.3, "color": "#2F6BEE"},
            {"course_id": 2, "code": "CSC 405",
             "title": "Compiler Design", "pct": 64.2, "color": "#A8420F"},
        ],
    ),
}


def test_all_registered_pages_render():
    failures = []
    for template, spec in CONTEXTS.items():
        try:
            html = render(template, spec)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{template}: {type(exc).__name__}: {exc}")
            continue
        if len(html) < 2000:
            failures.append(
                f"{template}: rendered only {len(html)} chars -- shell missing?"
            )
    assert not failures, "Render failures:\n  " + "\n  ".join(failures)


# Signed-out pages with their own <head> and no rail, on purpose.
STANDALONE = {"auth/login.html", "auth/change_password.html"}


def test_shell_present_on_every_page():
    """Every page must come out wrapped in the shared shell, or the rail and
    topbar silently vanish from that one page."""
    for template, spec in CONTEXTS.items():
        if template in STANDALONE:
            continue
        html = render(template, spec)
        for hook in ('id="shell"', 'id="sidebar"', 'id="sidebar-toggle"'):
            assert hook in html, f"{template} rendered without {hook}"


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list":
        for name in CONTEXTS:
            print(name)
        sys.exit(0)

    failed = 0
    for test in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {test.__name__}\n      {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")

    print()
    print(f"{len(CONTEXTS)} page(s) registered")
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)
