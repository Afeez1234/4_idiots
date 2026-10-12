"""Tests for small account and registration rules fixed in the 2026-10-12
audit (findings 10, 19 and 21):

  * a disabled account can't get new app tokens,
  * a student can drop a current-semester course but not a past one,
  * the HOD pages accept the same levels as the admin pages.

Run with:  python tests/test_account_rules.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, decode_token  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment, Semester,
)
from api.auth import api_auth_bp  # noqa: E402
from api.student import api_student_bp  # noqa: E402
from blueprints.hod import _student_level  # noqa: E402


class AccountRulesTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(api_auth_bp)
        self.app.register_blueprint(api_student_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(dept)
        db.session.flush()
        self.old_sem = Semester(name='Last', start_date=date(2026, 1, 1),
                                end_date=date(2026, 6, 1), is_active=False)
        self.cur_sem = Semester(name='Now', start_date=date(2026, 9, 1),
                                end_date=date(2027, 1, 1), is_active=True)
        db.session.add_all([self.old_sem, self.cur_sem])
        lect_user = User(username='lect', password_hash='x', role='lecturer')
        self.user = User(username='MCT/20/0001', password_hash='x', role='student',
                         is_active=True, requires_password_change=False)
        db.session.add_all([lect_user, self.user])
        db.session.flush()
        lecturer = Lecturer(full_name='Dr Ade', staff_id='S1', department_id=dept.id,
                            user_id=lect_user.id)
        db.session.add(lecturer)
        db.session.flush()
        self.student = Student(full_name='Ada', matric_number='MCT/20/0001', level='400',
                               department_id=dept.id, user_id=self.user.id)
        db.session.add(self.student)
        db.session.flush()
        self.old_course = Course(course_title='Old', course_code='MCT 301', lecturer_id=lecturer.id,
                                 department_id=dept.id, semester_id=self.old_sem.id)
        self.cur_course = Course(course_title='Now', course_code='MCT 401', lecturer_id=lecturer.id,
                                 department_id=dept.id, semester_id=self.cur_sem.id)
        db.session.add_all([self.old_course, self.cur_course])
        db.session.flush()
        db.session.add_all([
            Enrollment(student_id=self.student.id, course_id=self.old_course.id),
            Enrollment(student_id=self.student.id, course_id=self.cur_course.id),
        ])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def auth(self):
        token = create_access_token(identity=str(self.user.id), additional_claims={'role': 'student'})
        return {'Authorization': f'Bearer {token}'}

    # ---- finding 10 ----------------------------------------------------------

    def test_disabled_account_cannot_refresh(self):
        refresh = create_refresh_token(identity=str(self.user.id))
        self.user.current_refresh_jti = decode_token(refresh)['jti']
        self.user.is_active = False
        db.session.commit()
        resp = self.client.post('/api/v1/auth/refresh',
                                headers={'Authorization': f'Bearer {refresh}'})
        self.assertEqual(resp.status_code, 401)

    # ---- finding 19 ----------------------------------------------------------

    def test_cannot_drop_a_past_semester_course(self):
        resp = self.client.post(f'/api/v1/student/courses/{self.old_course.id}/drop',
                                headers=self.auth())
        self.assertEqual(resp.status_code, 400)
        self.assertIsNotNone(Enrollment.query.filter_by(course_id=self.old_course.id).first())

    def test_can_drop_a_current_semester_course(self):
        resp = self.client.post(f'/api/v1/student/courses/{self.cur_course.id}/drop',
                                headers=self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(Enrollment.query.filter_by(course_id=self.cur_course.id).first())

    # ---- finding 21 ----------------------------------------------------------

    def test_hod_levels_follow_the_admin_rule(self):
        self.assertEqual(_student_level('400L'), 400)
        self.assertEqual(_student_level(' 300 '), 300)
        self.assertIsNone(_student_level('1000'))   # the old HOD copy said 1000
        self.assertIsNone(_student_level('Year 4'))


if __name__ == '__main__':
    unittest.main()
