"""Tests for the admin Courses page (blueprints/admin.py::courses_page):

  * the catalog is one semester at a time (the active one by default), plus
    the courses with no semester, which belong to every semester -- it used
    to list every semester's courses together, so MCT401 appeared once per
    semester, identically, in the table and in the Enroll Student and Course
    Lecturers dropdowns,
  * search and department narrow the catalog but not those dropdowns,
  * enrolment counts come from one GROUP BY,
  * every lecturer is shown with their staff ID, coordinator first,
  * forms and the edit dialog return to the same view,
  * the page's query count doesn't grow with the number of courses.

Run with:  python tests/test_courses_page.py
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
from models import (  # noqa: E402
    db, Course, Department, Enrollment, Faculty, Lecturer, Semester, Student, User,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class CoursesPageTestCase(unittest.TestCase):

    def setUp(self):
        # Real templates: some tests render the page rather than mocking it.
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                         static_folder=os.path.join(ROOT, 'static'))
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
        self.old = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2026, 1, 31))
        db.session.add_all([self.mct, self.cpe, self.sem, self.old])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lead = self.lecturer('Dr Lead', 'STF/1')
        self.co = self.lecturer('Dr Co', 'STF/2')
        # The same code in two semesters, as every running course has.
        self.mct401 = self.course('MCT401', 'Control Systems', self.sem, co=[self.co])
        self.mct401_old = self.course('MCT401', 'Control Systems', self.old)
        self.cpe301 = self.course('CPE301', 'Digital Logic', self.sem, dept=self.cpe)
        self.gst212 = self.course('GST212', 'Philosophy', None, dept=None)   # every semester
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

    def lecturer(self, name, staff_id):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.mct.id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, title, semester, dept='mct', co=(), lead=None):
        c = Course(course_code=code, course_title=title, lecturer_id=(lead or self.lead).id,
                   department_id=(self.mct if dept == 'mct' else dept).id if dept else None,
                   semester_id=semester.id if semester else None)
        c.co_lecturers = list(co)
        db.session.add(c)
        db.session.flush()
        return c

    def student(self, matric):
        st = Student(full_name=matric, matric_number=matric, level='400',
                     department_id=self.mct.id, user_id=self.user(matric, 'student').id)
        db.session.add(st)
        db.session.flush()
        return st

    def context(self, **args):
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            response = self.client.get('/admin/courses', query_string=args)
        self.assertEqual(response.status_code, 200)
        return render.call_args.kwargs

    @staticmethod
    def ids(courses):
        return {c.id for c in courses}

    # ---- one semester at a time ---------------------------------------------------

    def test_default_is_the_active_semester_plus_courses_with_none(self):
        ctx = self.context()
        self.assertEqual(ctx['view_semester'].id, self.sem.id)
        self.assertEqual(self.ids(ctx['courses']), {self.mct401.id, self.cpe301.id, self.gst212.id})
        # The dropdowns get the same semester: last year's MCT401 isn't offered.
        self.assertNotIn(self.mct401_old.id, self.ids(ctx['semester_courses']))

    def test_another_semester_can_be_picked(self):
        ctx = self.context(semester=self.old.id)
        self.assertEqual(self.ids(ctx['courses']), {self.mct401_old.id, self.gst212.id})

    def test_search_and_department_narrow_the_catalog_not_the_dropdowns(self):
        ctx = self.context(q='logic')
        self.assertEqual(self.ids(ctx['courses']), {self.cpe301.id})
        self.assertEqual(len(ctx['semester_courses']), 3)            # still the whole semester
        self.assertTrue(ctx['is_filtered'])
        self.assertEqual(self.ids(self.context(q='mct4')['courses']), {self.mct401.id})
        self.assertEqual(self.ids(self.context(dept=self.cpe.id)['courses']), {self.cpe301.id})

    def test_enrolment_counts(self):
        for m in ('A/1', 'A/2'):
            db.session.add(Enrollment(student_id=self.student(m).id, course_id=self.mct401.id))
        db.session.commit()
        self.assertEqual(self.context()['enrolled'], {self.mct401.id: 2})

    # ---- the real page --------------------------------------------------------------

    def test_page_shows_every_lecturer_with_staff_id_and_defaults_add_course(self):
        html = self.client.get('/admin/courses').get_data(as_text=True)
        # Coordinator first and marked, co-lecturer too, both with staff IDs.
        self.assertRegex(html, r'Dr Lead <span class="mono text-2xs">\(STF/1\)</span>'
                               r' <span class="text-2xs text-muted">&middot; coordinator</span>')
        self.assertIn('Dr Co <span class="mono text-2xs">(STF/2)</span>', html)
        self.assertIn('All semesters', html)                         # GST212
        # Add Course defaults to the semester being viewed.
        self.assertIn(f'<option value="{self.sem.id}" selected>{self.sem.name}</option>', html)

    def test_forms_and_edit_return_to_the_same_view(self):
        st = self.student('MCT/20/0001')
        db.session.commit()
        resp = self.client.post(f'/admin/courses?semester={self.old.id}&q=mct', data={
            'action': 'enroll_student', 'matric_number': 'MCT/20/0001', 'course_id': self.mct401_old.id})
        self.assertIn(f'semester={self.old.id}', resp.headers['Location'])
        self.assertIn('q=mct', resp.headers['Location'])
        self.assertEqual([c.id for c in db.session.get(Student, st.id).courses], [self.mct401_old.id])

        resp = self.client.post(f'/admin/courses/{self.cpe301.id}/edit?semester={self.old.id}', data={
            'code': 'CPE301', 'title': 'Digital Logic II', 'department_id': self.cpe.id,
            'semester_id': self.sem.id, 'credit_units': ''})
        self.assertIn(f'semester={self.old.id}', resp.headers['Location'])

    def test_queries_do_not_grow_with_courses(self):
        def add(n, start):
            for i in range(n):
                # Its own coordinator and co-lecturer, so the identity map
                # can't hide a per-lecturer query.
                lead = self.lecturer(f'Dr L{start + i}', f'STF/L{start + i}')
                co = self.lecturer(f'Dr C{start + i}', f'STF/C{start + i}')
                c = self.course(f'X{start + i}', 'Title', self.sem, co=[co], lead=lead)
                db.session.add(Enrollment(student_id=self.student(f'S/{start + i}').id, course_id=c.id))
            db.session.commit()
            db.session.expire_all()

        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                self.assertEqual(self.client.get('/admin/courses').status_code, 200)
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen)

        add(1, 0)
        few = queries()
        add(8, 100)
        self.assertEqual(few, queries())


if __name__ == '__main__':
    unittest.main()
