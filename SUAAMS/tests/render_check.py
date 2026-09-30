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
    "admin/dashboard.html": dict(
        role="admin",
        active_page="dashboard",
        active_semester=None,
        total_faculties=3,
        total_lecturers=2,
        total_students=1,
        live_sessions=0,
        department_attendance=[
            {"name": "Systems Eng", "percentage": 82.0},
            {"name": "Comp Sci", "percentage": 47.0},
        ],
        recent_activity=[
            {"icon": "check", "color": "success", "message": "ok", "time": "now"}
        ],
    ),

    # --- The light-theme redesign pages ---------------------------------
    # Plain dicts stand in for the SQLAlchemy rows: Jinja's attribute lookup
    # falls back to getitem, so `a.department.name` resolves against nested
    # dicts. Only `created_at` / `start_date` / `end_date` must be real
    # objects, because the templates call .strftime() on them -- a string
    # there would render the page but never exercise the date path.

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
    ),

    "admin/courses.html": dict(
        role="admin",
        active_page="courses",
        active_semester=None,
        courses=[
            {
                "id": 1,
                "course_code": "CPE401",
                "course_title": "Embedded Systems",
                "department": {"name": "Computer Engineering"},
                "lecturer": {"full_name": "Dr. Jane Doe"},
                "credit_units": 3,
                "enrollments": [{}, {}],
            },
            {
                "id": 2,
                "course_code": "SEE310",
                "course_title": "Control Systems",
                "department": {"name": "Systems Engineering"},
                "lecturer": None,
                "credit_units": None,
                "enrollments": [],
            },
        ],
        departments=[
            {"id": 1, "name": "Computer Engineering"},
            {"id": 2, "name": "Systems Engineering"},
        ],
        lecturers=[{"id": 1, "full_name": "Dr. Jane Doe"}],
        semesters=[{"id": 1, "name": "2025/2026 First Semester"}],
        students=[{"id": 1, "full_name": "Aisha Bello", "matric_number": "CPE/20/1123"}],
    ),

    "admin/hods.html": dict(
        role="admin",
        active_page="hods",
        active_semester=None,
        hods=[
            {
                "id": 1,
                "full_name": "Prof. Adaeze Nwosu",
                "staff_id": "HOD-2001",
                "department": {"name": "Systems Engineering"},
                "user": {"requires_password_change": False},
            },
            {
                "id": 2,
                "full_name": "Dr. Emeka Obi",
                "staff_id": "HOD-2002",
                "department": {"name": "Computer Engineering"},
                "user": {"requires_password_change": True},
            },
        ],
        departments=[
            {"id": 1, "name": "Systems Engineering"},
            {"id": 2, "name": "Computer Engineering"},
        ],
        # Deliberately non-empty: the promote branch renders a `<select>` whose
        # options dereference .department.name, which an empty list would skip.
        promotable_lecturers=[
            {
                "id": 7,
                "full_name": "Dr. Tunde Cole",
                "staff_id": "LECT-1007",
                "department": {"name": "Systems Engineering"},
            }
        ],
    ),

    "admin/lecturers.html": dict(
        role="admin",
        active_page="lecturers",
        active_semester=None,
        lecturers=[
            {
                "id": 1,
                "full_name": "Dr. Jane Doe",
                "staff_id": "LECT-1002",
                "department": {"name": "Computer Engineering"},
                "courses": [{}, {}, {}],
                "user": {"requires_password_change": False},
            },
            {
                "id": 2,
                "full_name": "Dr. Tunde Cole",
                "staff_id": "LECT-1007",
                "department": None,
                "courses": [],
                "user": {"requires_password_change": True},
            },
        ],
        departments=[{"id": 1, "name": "Computer Engineering"}],
    ),

    "admin/organization.html": dict(
        role="admin",
        active_page="organization",
        active_semester=None,
        # The faculty row builds its cascade totals in-template with
        # `departments|map(attribute='students')|map('length')|sum`, so each
        # nested department dict must actually carry those three lists or the
        # sum silently collapses to 0.
        faculties=[
            {
                "id": 1,
                "name": "Faculty of Engineering",
                "departments": [
                    {
                        "students": [{}] * 3,
                        "lecturers": [{}, {}],
                        "courses": [{}] * 5,
                    }
                ],
            }
        ],
        departments=[
            {
                "id": 1,
                "name": "Computer Engineering",
                "faculty": {"name": "Faculty of Engineering"},
                "students": [{}] * 3,
                "lecturers": [{}, {}],
                "courses": [{}] * 5,
            }
        ],
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
                "device_id": "android-abc123",
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
                "department": {"name": "Systems Engineering"},
                "device_id": None,
                "user": {"requires_password_change": True},
            },
        ],
        departments=[
            {"id": 1, "name": "Computer Engineering"},
            {"id": 2, "name": "Systems Engineering"},
        ],
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
        # present / late / absent in one list: the status pill keys off exactly
        # this set, so all three must appear somewhere.
        recent_attendance=[
            {"course": "SEN 301", "course_title": "Signals & Systems",
             "date": "14 Sep 2026", "time": "09:00", "status": "present"},
            {"course": "SEN 311", "course_title": "Embedded Systems",
             "date": "13 Sep 2026", "time": "14:00", "status": "late"},
            {"course": "SEN 311", "course_title": "Embedded Systems",
             "date": "12 Sep 2026", "time": "14:00", "status": "absent"},
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
            "session_date": date(2026, 9, 27),
            "start_time": time(9, 1),
            # planned_start None so the nested fallback in the "Started:" line
            # is reachable; stop_time set so the "Ended:" chip renders.
            "planned_start": None,
            "stop_time": time(10, 30),
        },
        # Same positional 6-tuples as course_workspace -- this page renders the
        # records TWICE (mobile card list + desktop table) and its search input
        # drives both halves, so a shape error here is the DOM contract's fault.
        attendance_records=[
            ("Adebayo Oluwaseun", 400, "Computer Science", "CSC/2021/0451",
             "Present", datetime(2026, 9, 27, 9, 3, 12)),
            ("Chidinma Eze", 400, "Computer Science", "CSC/2021/0452",
             "Late", datetime(2026, 9, 27, 9, 7, 41)),
            ("Ibrahim Musa", 400, "Computer Science", "CSC/2021/0453",
             "Present", datetime(2026, 9, 27, 9, 2, 5)),
            ("Tunde Bakare", 400, "Computer Science", "CSC/2021/0454",
             "Absent", None),
            ("Zainab Bello", 400, "Computer Science", "CSC/2021/0455",
             "Present", datetime(2026, 9, 27, 9, 4, 58)),
        ],
        enrolled_count=48,
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


def test_shell_present_on_every_page():
    """Every page must come out wrapped in the shared shell, or the rail and
    topbar silently vanish from that one page."""
    for template, spec in CONTEXTS.items():
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
