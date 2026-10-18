"""Tests for the admin Announcements page (blueprints/admin.py), 2026-10-18:

  * a department or course announcement without its department or course
    is refused -- one used to be saved with neither, reaching nobody;
  * the course list is this semester's courses (it was every semester's);
  * the page carries how many students each choice notifies, matching
    utils.announcement_user_ids, so posting can ask "notify N students?";
  * a good announcement still posts and notifies.

Run with:  python tests/test_announcements_page.py
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

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Announcement, Course, Department, Enrollment, Faculty, Lecturer, Semester, Student, User,
)
from utils import announcement_user_ids  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class AnnouncementsPageTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                         static_folder=os.path.join(ROOT, 'static'))
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        # The feed shows times through app.py's `campus` filter.
        from campus_time import campus_fmt
        self.app.jinja_env.filters['campus'] = campus_fmt
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
        self.now = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        self.old = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2026, 1, 31))
        db.session.add_all([self.mct, self.cpe, self.now, self.old])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        lect = Lecturer(full_name='Dr L', staff_id='STF/1', department_id=self.mct.id,
                        user_id=self.user('STF/1', 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        self.new401 = Course(course_code='NEW401', course_title='New', lecturer_id=lect.id,
                             department_id=self.mct.id, semester_id=self.now.id)
        self.old401 = Course(course_code='OLD401', course_title='Old', lecturer_id=lect.id,
                             department_id=self.mct.id, semester_id=self.old.id)
        db.session.add_all([self.new401, self.old401])
        db.session.flush()
        # Three Mechatronics students (two in NEW401), one Computer student.
        for i, dept in enumerate([self.mct, self.mct, self.mct, self.cpe]):
            st = Student(full_name=f'S{i}', matric_number=f'M/{i}', level='400', department_id=dept.id,
                         user_id=self.user(f'M/{i}', 'student').id)
            db.session.add(st)
            db.session.flush()
            if i < 2:
                db.session.add(Enrollment(student_id=st.id, course_id=self.new401.id))
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role, is_active=True,
                 requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        return u

    def post(self, **form):
        data = {'title': 'Exam timetable', 'body': 'Out now.', **form}
        with mock.patch('blueprints.admin.notify_announcement') as notify:
            self.client.post('/admin/announcements', data=data)
        return notify

    # ---- the missing-target bug -------------------------------------------------------------

    def test_department_scope_needs_a_department(self):
        notify = self.post(scope='department')
        self.assertEqual(Announcement.query.count(), 0)
        notify.assert_not_called()

    def test_course_scope_needs_a_course(self):
        self.post(scope='course', course_id='999')
        self.assertEqual(Announcement.query.count(), 0)

    def test_a_good_announcement_posts_and_notifies(self):
        notify = self.post(scope='course', course_id=str(self.new401.id))
        self.assertEqual(Announcement.query.one().course_id, self.new401.id)
        notify.assert_called_once()

    # ---- the page ---------------------------------------------------------------------------

    def test_page_lists_this_semesters_courses_with_audience_counts(self):
        html = self.client.get('/admin/announcements').get_data(as_text=True)
        self.assertIn('NEW401', html)
        self.assertNotIn('OLD401', html)
        self.assertIn('id="announcement-form" data-audience="4"', html)
        self.assertIn(f'<option value="{self.mct.id}" data-audience="3">Mechatronics</option>', html)
        self.assertIn(f'value="{self.new401.id}" data-audience="2"', html)

    def test_audience_counts_match_who_is_notified(self):
        # The page's numbers and utils.announcement_user_ids must agree.
        for scope, target, expected in (('university', {}, 4),
                                        ('department', {'department_id': self.mct.id}, 3),
                                        ('course', {'course_id': self.new401.id}, 2)):
            a = Announcement(title='t', body='b', sender_id=self.admin.id, scope=scope, **target)
            self.assertEqual(len(announcement_user_ids(a)), expected, scope)


if __name__ == '__main__':
    unittest.main()
