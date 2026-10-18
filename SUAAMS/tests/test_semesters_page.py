"""Tests for the admin Semesters page (blueprints/admin.py::semesters_page),
2026-10-18:

  * each semester shows its course and published-class counts, and its Set
    Active form carries them so the page can warn before switching to an
    empty one -- since the "now" screens follow the active semester, that
    empties every student's and lecturer's app;
  * creating a semester checks the dates (end after start) and names each
    failure -- every error used to read "Semester name must be unique";
  * Set Active still switches, one active semester at a time.

Run with:  python tests/test_semesters_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Course, Department, Faculty, Lecturer, Semester, Timetable, User  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SemestersPageTestCase(unittest.TestCase):

    def setUp(self):
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
        dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.old = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2026, 1, 31), is_active=True)
        self.new = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31))
        db.session.add_all([dept, self.old, self.new])
        db.session.flush()
        self.admin = User(username='tunde', password_hash='x', role='admin', is_active=True,
                          requires_password_change=False)
        lect_user = User(username='STF/1', password_hash='x', role='lecturer', is_active=True)
        db.session.add_all([self.admin, lect_user])
        db.session.flush()
        lect = Lecturer(full_name='Dr L', staff_id='STF/1', department_id=dept.id, user_id=lect_user.id)
        db.session.add(lect)
        db.session.flush()
        # The old semester has two courses and one published class; the new one nothing.
        for code in ('MCT401', 'MCT403'):
            db.session.add(Course(course_code=code, course_title=code, lecturer_id=lect.id,
                                  department_id=dept.id, semester_id=self.old.id))
        db.session.flush()
        first = Course.query.filter_by(course_code='MCT401').one()
        db.session.add(Timetable(course_id=first.id, semester_id=self.old.id, day_of_week=0,
                                 start_time=time(8), end_time=time(10), is_published=True,
                                 created_by=self.admin.id))
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def create(self, name, start, end):
        return self.client.post('/admin/semesters', data={'name': name, 'start_date': start, 'end_date': end},
                                follow_redirects=True).get_data(as_text=True)

    # ---- counts and the activate warning ------------------------------------------------

    def test_rows_show_what_each_semester_holds(self):
        html = self.client.get('/admin/semesters').get_data(as_text=True)
        self.assertIn('2 courses', html)
        self.assertIn('1 published class', html)
        # The empty semester's Set Active form carries 0 / 0 for the warning.
        self.assertIn(f'data-name="{self.new.name}" data-courses="0" data-slots="0"', html)
        self.assertIn('has no courses yet', html)          # the warning text is on the page

    def test_set_active_still_switches(self):
        self.client.post('/admin/semesters', data={'action': 'activate', 'semester_id': self.new.id})
        self.assertTrue(db.session.get(Semester, self.new.id).is_active)
        self.assertFalse(db.session.get(Semester, self.old.id).is_active)

    # ---- creating a semester ---------------------------------------------------------------

    def test_end_before_start_is_refused(self):
        html = self.create('2027/2028 First Semester', '2027-09-01', '2027-08-01')
        self.assertIn('The end date must be after the start date.', html)
        self.assertEqual(Semester.query.count(), 2)

    def test_duplicate_name_says_so(self):
        html = self.create('2025/2026 first semester', '2027-09-01', '2028-01-31')   # case differs
        self.assertIn('already exists', html)
        self.assertEqual(Semester.query.count(), 2)

    def test_missing_date_says_so(self):
        html = self.create('2027/2028 First Semester', '', '2028-01-31')
        self.assertIn('Name, start date and end date are all required.', html)

    def test_a_good_semester_is_created_inactive(self):
        self.create('2027/2028 First Semester', '2027-09-01', '2028-01-31')
        made = Semester.query.filter_by(name='2027/2028 First Semester').one()
        self.assertFalse(made.is_active)


if __name__ == '__main__':
    unittest.main()
