"""Tests for the admin Reports page and its CSV (blueprints/admin.py),
2026-10-18:

  * one semester at a time -- the active one by default, another by
    ?semester= -- plus courses with no semester. It used to list every
    course ever, so each code appeared once per semester;
  * the CSV follows the same semester and is named after it.

Run with:  python tests/test_reports_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Course, Department, Faculty, Lecturer, Semester, User  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ReportsPageTestCase(unittest.TestCase):

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
        self.now = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        self.old = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2026, 1, 31))
        db.session.add_all([dept, self.now, self.old])
        db.session.flush()
        admin = User(username='tunde', password_hash='x', role='admin', is_active=True,
                     requires_password_change=False)
        lu = User(username='STF/1', password_hash='x', role='lecturer', is_active=True)
        db.session.add_all([admin, lu])
        db.session.flush()
        lect = Lecturer(full_name='Dr L', staff_id='STF/1', department_id=dept.id, user_id=lu.id)
        db.session.add(lect)
        db.session.flush()
        for code, sem in (('NEW401', self.now), ('OLD401', self.old), ('GST212', None)):
            db.session.add(Course(course_code=code, course_title=code, lecturer_id=lect.id,
                                  department_id=dept.id, semester_id=sem.id if sem else None))
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = admin.id, 'tunde', 'admin'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def test_default_is_the_active_semester(self):
        html = self.client.get('/admin/reports').get_data(as_text=True)
        self.assertIn('NEW401', html)
        self.assertIn('GST212', html)                    # no semester: every semester's
        self.assertNotIn('OLD401', html)
        self.assertIn(f'Course Attendance &middot; {self.now.name}', html)

    def test_another_semester_can_be_picked(self):
        html = self.client.get('/admin/reports', query_string={'semester': self.old.id}).get_data(as_text=True)
        self.assertIn('OLD401', html)
        self.assertNotIn('NEW401', html)
        self.assertIn(f'semester={self.old.id}', html)   # the Export link follows the picker

    def test_csv_follows_the_semester_and_is_named_after_it(self):
        resp = self.client.get('/admin/reports/export', query_string={'semester': self.old.id})
        text = resp.get_data(as_text=True)
        self.assertIn('OLD401', text)
        self.assertNotIn('NEW401', text)
        self.assertIn('filename=attendance_report_2025_2026_First_Semester.csv',
                      resp.headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main()
