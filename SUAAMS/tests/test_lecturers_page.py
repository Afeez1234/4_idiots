"""Tests for the admin Lecturers page (blueprints/admin.py::lecturers_page):

  * "Courses this semester" counts coordinated AND co-lectured courses, in
    the active semester only, each course once (it used to be
    len(lecturer.courses): coordinated only, every semester),
  * search (name or staff ID) and the department filter,
  * the page's query count doesn't grow with the number of lecturers.

Run with:  python tests/test_lecturers_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402
from sqlalchemy import event  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Course, Department, Faculty, Lecturer, Semester, User  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class LecturersPageTestCase(unittest.TestCase):

    def setUp(self):
        # The real templates and static folder: the page-cost test renders
        # the page for real rather than mocking render_template.
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.app = Flask(__name__, template_folder=os.path.join(root, 'templates'),
                         static_folder=os.path.join(root, 'static'))
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        for bp in (auth_bp, admin_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.mct = Department(name='Mechatronics', faculty_id=faculty.id)
        self.cpe = Department(name='Computer', faculty_id=faculty.id)
        self.sem = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        self.old = Semester(name='2025/2026 Second Semester', start_date=date(2026, 2, 1),
                            end_date=date(2026, 7, 1))
        db.session.add_all([self.mct, self.cpe, self.sem, self.old])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'], sess['username'], sess['role'] = self.admin.id, 'tunde', 'admin'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures ---------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role, is_active=True,
                 requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        return u

    def lecturer(self, name, staff_id, dept=None):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=(dept or self.mct).id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, coordinator, semester=None, co=()):
        c = Course(course_code=code, course_title=code, lecturer_id=coordinator.id,
                   department_id=self.mct.id, semester_id=(semester or self.sem).id)
        c.co_lecturers = list(co)
        db.session.add(c)
        db.session.flush()
        return c

    def page_context(self, **args):
        """The kwargs the route passed to render_template."""
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            response = self.client.get('/admin/lecturers', query_string=args)
        self.assertEqual(response.status_code, 200)
        return render.call_args.kwargs

    # ---- course count -------------------------------------------------------------

    def test_course_count_is_this_semesters_coordinated_and_co_lectured(self):
        lead = self.lecturer('Dr Lead', 'STF/1')
        co = self.lecturer('Dr Co', 'STF/2')
        self.course('MCT 401', lead, co=[co])
        self.course('MCT 403', lead, co=[lead])      # listed twice: counts once
        self.course('MCT 301', lead, semester=self.old)   # past semester: not counted
        db.session.commit()

        counts = self.page_context()['course_counts']
        self.assertEqual(counts.get(lead.id), 2)
        self.assertEqual(counts.get(co.id), 1)       # used to read 0

    def test_no_active_semester_counts_nothing(self):
        lead = self.lecturer('Dr Lead', 'STF/1')
        self.course('MCT 401', lead)
        self.sem.is_active = False
        db.session.commit()
        self.assertEqual(self.page_context()['course_counts'], {})

    # ---- search and filter --------------------------------------------------------

    def test_search_by_name_or_staff_id_and_filter_by_department(self):
        self.lecturer('Dr Zainab Bello', 'STF/10')
        self.lecturer('Dr Ade Okafor', 'CPE/22', dept=self.cpe)
        db.session.commit()

        names = lambda ctx: [l.full_name for l in ctx['lecturers']]   # noqa: E731
        # Sorted by name, not insertion order.
        self.assertEqual(names(self.page_context()), ['Dr Ade Okafor', 'Dr Zainab Bello'])
        self.assertEqual(names(self.page_context(q='bello')), ['Dr Zainab Bello'])
        self.assertEqual(names(self.page_context(q='CPE/2')), ['Dr Ade Okafor'])
        self.assertEqual(names(self.page_context(dept=self.cpe.id)), ['Dr Ade Okafor'])
        # LIKE wildcards in the search are literal.
        self.assertEqual(names(self.page_context(q='%')), [])
        ctx = self.page_context(q='bello', dept=self.mct.id)
        self.assertEqual(ctx['filter_args'], {'q': 'bello', 'dept': self.mct.id})
        self.assertTrue(ctx['is_filtered'])

    # ---- page cost ------------------------------------------------------------------

    def test_queries_do_not_grow_with_lecturers(self):
        def add(n, start):
            for i in range(n):
                dept = self.mct if i % 2 else self.cpe
                lect = self.lecturer(f'Dr {start + i}', f'STF/{start + i}', dept=dept)
                self.course(f'C{start + i}', lect)
            db.session.commit()
            db.session.expire_all()

        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                # Real render, so the template's own attribute reads
                # (department, user, status cell) are counted too.
                response = self.client.get('/admin/lecturers')
                self.assertEqual(response.status_code, 200)
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen)

        add(1, 0)
        few = queries()
        add(8, 100)
        self.assertEqual(few, queries())


if __name__ == '__main__':
    unittest.main()
