"""Tests for the lecturer web portal fixes (blueprints/lecturer.py), 2026-10-19:

  * the course page no longer reloads itself every 5 seconds; a JSON route
    (live_attendance) gives the live rows and count for an in-place refresh,
    and only to a lecturer who teaches the course;
  * a running class links to its session page (Mark present, offline taps),
    and End Session asks first;
  * Session History rows carry a real link, not only an onclick;
  * Reports has a semester picker -- since the "now" screens were scoped it
    could show only the current semester -- and the CSV follows it.

Run with:  python tests/test_lecturer_portal.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, Course, Department, Enrollment, Faculty, Lecturer, Semester,
    Session as SessionModel, Student, User,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.lecturer import lecturer_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LecturerPortalTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                         static_folder=os.path.join(ROOT, 'static'))
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        from campus_time import campus_fmt
        self.app.jinja_env.filters['campus'] = campus_fmt
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        for bp in (auth_bp, lecturer_bp):
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
        self.lect = self.lecturer('STF/1', dept)
        self.other = self.lecturer('STF/2', dept)
        self.new401 = self.course('NEW401', self.now, self.lect, dept)
        self.old401 = self.course('OLD401', self.old, self.lect, dept)
        self.theirs = self.course('THR101', self.now, self.other, dept)

        su = User(username='MCT/20/0001', password_hash='x', role='student', is_active=True)
        db.session.add(su)
        db.session.flush()
        self.student = Student(full_name='Ada Obi', matric_number='MCT/20/0001', level='400',
                               department_id=dept.id, user_id=su.id)
        db.session.add(self.student)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student.id, course_id=self.new401.id))
        self.live = SessionModel(course_id=self.new401.id, session_date=date(2026, 10, 19), is_active=True)
        db.session.add(self.live)
        db.session.flush()
        db.session.add(Attendance(student_id=self.student.id, session_id=self.live.id, status='late',
                                  time_in=datetime(2026, 10, 19, 9, 5, tzinfo=timezone.utc)))
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.lect.user_id, 'STF/1', 'lecturer'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def lecturer(self, staff_id, dept):
        u = User(username=staff_id, password_hash='x', role='lecturer', is_active=True,
                 requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        lect = Lecturer(full_name=f'Dr {staff_id}', staff_id=staff_id, department_id=dept.id, user_id=u.id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, semester, lecturer, dept):
        c = Course(course_code=code, course_title=code, lecturer_id=lecturer.id,
                   department_id=dept.id, semester_id=semester.id)
        db.session.add(c)
        db.session.flush()
        return c

    # ---- the live course page -------------------------------------------------------

    def test_course_page_no_longer_reloads_itself(self):
        html = self.client.get(f'/lecturer/course/{self.new401.id}').get_data(as_text=True)
        self.assertNotIn('http-equiv="refresh"', html)
        # The live refresh, the link to the session page, and End asks first.
        self.assertIn(f'/lecturer/course/{self.new401.id}/live', html)
        self.assertIn(f'/lecturer/course/{self.new401.id}/session/{self.live.id}', html)
        self.assertIn('class="end-session-form"', html)
        self.assertIn('Ada Obi', html)

    def test_live_route_gives_rows_and_count(self):
        data = self.client.get(f'/lecturer/course/{self.new401.id}/live').get_json()
        self.assertTrue(data['active'])
        self.assertEqual(data['present'], 1)
        self.assertIn('Ada Obi', data['rows_html'])
        self.assertIn('data-tone="warning"', data['rows_html'])        # late = amber, the shared map

    def test_live_route_is_for_the_courses_own_lecturer_only(self):
        self.assertEqual(self.client.get(f'/lecturer/course/{self.theirs.id}/live').status_code, 404)

    def test_live_route_says_when_the_class_has_ended(self):
        self.live.is_active = False
        db.session.commit()
        self.assertEqual(self.client.get(f'/lecturer/course/{self.new401.id}/live').get_json(),
                         {'active': False})

    # ---- session history ----------------------------------------------------------------

    def test_history_rows_are_real_links(self):
        self.live.is_active = False
        db.session.commit()
        html = self.client.get('/lecturer/sessions/history').get_data(as_text=True)
        self.assertIn(f'<a href="/lecturer/course/{self.new401.id}/session/{self.live.id}"', html)

    # ---- reports ---------------------------------------------------------------------------

    def test_reports_pick_a_semester_and_the_csv_follows(self):
        html = self.client.get('/lecturer/reports').get_data(as_text=True)
        self.assertIn('NEW401', html)
        self.assertNotIn('OLD401', html)
        html = self.client.get('/lecturer/reports', query_string={'semester': self.old.id}).get_data(as_text=True)
        self.assertIn('OLD401', html)
        self.assertNotIn('NEW401', html)
        resp = self.client.get('/lecturer/reports/export', query_string={'semester': self.old.id})
        self.assertIn('OLD401', resp.get_data(as_text=True))
        self.assertIn('attendance_report_2025_2026_First_Semester.csv', resp.headers['Content-Disposition'])


if __name__ == '__main__':
    unittest.main()
