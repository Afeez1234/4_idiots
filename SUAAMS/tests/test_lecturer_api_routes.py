"""The lecturer app's course routes: open a course, start a class, end it.

Regression test for a real outage. A bad automated edit (2026-10-12, the
"one start/end-session implementation" commit) deleted the app's
/start-session and /end-session routes and replaced the body of
"open course" with end-session code -- so opening a course in the lecturer
app ENDED its running class, and lecturers couldn't start or end classes
from the app at all. Nothing exercised these three routes, so every test
still passed. These do.

Run with:  python tests/test_lecturer_api_routes.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Faculty, Department, User, Lecturer, Course, Session as SessionModel  # noqa: E402
from api.lecturer import api_lecturer_bp  # noqa: E402


class LecturerApiRoutesTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(api_lecturer_bp)
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
        user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(user)
        db.session.flush()
        self.lecturer = Lecturer(full_name='Dr Ade', staff_id='S1', department_id=dept.id, user_id=user.id)
        db.session.add(self.lecturer)
        db.session.flush()
        self.course = Course(course_title='Control', course_code='MCT 401',
                             lecturer_id=self.lecturer.id, department_id=dept.id)
        db.session.add(self.course)
        db.session.commit()
        self.cid = self.course.id
        token = create_access_token(identity=str(user.id), additional_claims={'role': 'lecturer'})
        self.headers = {'Authorization': f'Bearer {token}'}

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def running(self):
        return SessionModel.query.filter_by(course_id=self.cid, is_active=True).count()

    def test_start_open_end(self):
        resp = self.client.post(f'/api/v1/lecturer/course/{self.cid}/start-session',
                                headers=self.headers, json={})
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.running(), 1)

        # Opening the course must SHOW the running class, not end it.
        resp = self.client.get(f'/api/v1/lecturer/course/{self.cid}', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()['data']
        self.assertEqual(data['course']['id'], self.cid)
        self.assertIsNotNone(data['active_session'])
        self.assertEqual(self.running(), 1)

        resp = self.client.post(f'/api/v1/lecturer/course/{self.cid}/end-session',
                                headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.running(), 0)

    def test_open_course_with_no_class_running(self):
        resp = self.client.get(f'/api/v1/lecturer/course/{self.cid}', headers=self.headers)
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.get_json()['data']['active_session'])


if __name__ == '__main__':
    unittest.main()
