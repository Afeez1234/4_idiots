"""Tests for several lecturers per course.

A course has one coordinator (courses.lecturer_id) and any number of
co-lecturers (course_lecturers), all with the same powers. These pin:

  * a co-lecturer can open the course, start a class (recorded as theirs),
    mark a student present and end it -- in the app's API,
  * a lecturer who doesn't teach the course still can't,
  * names show every lecturer, coordinator first,
  * the admin rules: add, remove, make coordinator (old one stays on as a
    lecturer), and the coordinator can't simply be removed,
  * the timetable treats a co-lecturer's double booking as a clash.

Run with:  python tests/test_course_lecturers.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, Semester, Timetable,
)
from api.lecturer import api_lecturer_bp  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp, _validate_timetable_slot  # noqa: E402
from utils import courses_taught_by  # noqa: E402


class CourseLecturersTestCase(unittest.TestCase):

    def setUp(self):
        mock.patch('push_notifications.send_push_notification').start()
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
        self.app.register_blueprint(auth_bp)
        self.app.register_blueprint(admin_bp)
        mock.patch('blueprints.auth.render_template', return_value='').start()
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='General Studies')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='GST', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.flush()
        self.coord = self.lecturer('Dr Opara', 'STF/001')
        self.co = self.lecturer('Dr Danladi', 'STF/002')
        self.outsider = self.lecturer('Dr Bala', 'STF/003')
        self.course = Course(course_title='Logic and Philosophy', course_code='GST212',
                             lecturer_id=self.coord.id, department_id=self.dept.id)
        db.session.add(self.course)
        db.session.flush()
        self.course.co_lecturers.append(self.co)

        su = User(username='GST/20/0001', password_hash='x', role='student')
        db.session.add(su)
        db.session.flush()
        self.student = Student(full_name='Ada', matric_number='GST/20/0001', level='200',
                               department_id=self.dept.id, user_id=su.id)
        db.session.add(self.student)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student.id, course_id=self.course.id))

        self.admin = User(username='tunde', password_hash='x', role='admin',
                          is_active=True, requires_password_change=False)
        db.session.add(self.admin)
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def lecturer(self, name, staff_id):
        u = User(username=staff_id, password_hash='x', role='lecturer')
        db.session.add(u)
        db.session.flush()
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id, user_id=u.id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def as_lecturer(self, lect):
        token = create_access_token(identity=str(lect.user_id), additional_claims={'role': 'lecturer'})
        return {'Authorization': f'Bearer {token}'}

    def api(self, method, path, lect, **kw):
        return getattr(self.client, method)(f'/api/v1/lecturer{path}', headers=self.as_lecturer(lect), **kw)

    # ---- powers --------------------------------------------------------------

    def test_co_lecturer_can_run_a_class(self):
        cid = self.course.id
        self.assertEqual(self.api('get', f'/course/{cid}', self.co).status_code, 200)
        self.assertEqual(self.api('post', f'/course/{cid}/start-session', self.co, json={}).status_code, 201)
        session = SessionModel.query.filter_by(course_id=cid, is_active=True).one()
        self.assertEqual(session.started_by, self.co.user_id)   # recorded as theirs

        resp = self.api('post', f'/course/{cid}/session/{session.id}/mark-present', self.co,
                        json={'student_id': self.student.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Attendance.query.filter_by(session_id=session.id).count(), 1)
        self.assertEqual(self.api('post', f'/course/{cid}/end-session', self.co).status_code, 200)

    def test_lecturer_not_on_the_course_still_cannot(self):
        cid = self.course.id
        self.assertEqual(self.api('get', f'/course/{cid}', self.outsider).status_code, 404)
        self.assertEqual(self.api('post', f'/course/{cid}/start-session', self.outsider,
                                  json={}).status_code, 404)

    def test_course_lists_include_co_taught_courses(self):
        self.assertEqual([c.id for c in courses_taught_by(self.co)], [self.course.id])
        self.assertEqual([c.id for c in courses_taught_by(self.coord)], [self.course.id])
        self.assertEqual(courses_taught_by(self.outsider).all(), [])

    def test_names_show_everyone_coordinator_first(self):
        self.assertEqual(self.course.lecturer_names, 'Dr Opara, Dr Danladi')
        self.assertEqual(self.course.lecturer_summary, 'Dr Opara + 1 more')

    # ---- admin rules ---------------------------------------------------------

    def manage(self, staff_id, change):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'
        self.client.post('/admin/courses', data={
            'action': 'manage_lecturer', 'course_id': self.course.id,
            'staff_id': staff_id, 'change': change})
        db.session.expire_all()
        return db.session.get(Course, self.course.id)

    def test_add_and_remove_a_lecturer(self):
        course = self.manage('stf/003', 'add')     # any capitals
        self.assertIn(self.outsider, course.co_lecturers)
        course = self.manage('STF/003', 'remove')
        self.assertNotIn(self.outsider, course.co_lecturers)
        actions = [e.action for e in AuditLog.query.order_by(AuditLog.id)]
        self.assertEqual(actions, ['course.lecturer_add', 'course.lecturer_remove'])

    def test_coordinator_cannot_simply_be_removed(self):
        course = self.manage('STF/001', 'remove')
        self.assertEqual(course.lecturer_id, self.coord.id)

    def test_new_coordinator_keeps_the_old_one_on_the_course(self):
        course = self.manage('STF/002', 'coordinator')
        self.assertEqual(course.lecturer_id, self.co.id)
        self.assertIn(self.coord, course.co_lecturers)
        self.assertNotIn(self.co, course.co_lecturers)

    # ---- timetable -----------------------------------------------------------

    def test_co_lecturer_double_booking_is_a_clash(self):
        sem = Semester(name='S', start_date=date(2026, 9, 1), end_date=date(2027, 1, 1))
        other = Course(course_title='Other', course_code='MCT 401',
                       lecturer_id=self.outsider.id, department_id=self.dept.id)
        db.session.add_all([sem, other])
        db.session.flush()
        other.co_lecturers.append(self.co)   # Dr Danladi teaches both
        db.session.add(Timetable(course_id=other.id, semester_id=sem.id, day_of_week=0,
                                 start_time=time(10), end_time=time(12), created_by=self.admin.id))
        db.session.commit()
        error = _validate_timetable_slot(self.course, sem.id, 0, time(11), time(13), 'LR 9')
        self.assertIn('Dr Danladi', error or '')


if __name__ == '__main__':
    unittest.main()
