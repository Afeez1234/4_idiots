"""Tests for student and lecturer status (people_status.py and the admin
routes /admin/<kind>/<id>/status and /admin/<kind>/status/bulk).

Pins:

  * anything but Active switches the login off and revokes the phone's
    refresh token; Active switches it back on;
  * a student's exit (graduated, ...) releases the phone binding; a
    suspension doesn't;
  * a reason is required; nothing is ever deleted;
  * a lecturer can't be marked Left while coordinating a running course;
    once they can, they come off running courses' co-lecturer lists but stay
    on finished ones;
  * the lecturer's "mark present" list leaves out non-active students;
  * the CSV route previews first, refuses unknown IDs, and applies to
    everyone at once with an audit entry each;
  * a signed-in web user whose account is switched off is signed out.

Run with:  python tests/test_people_status.py
(also collected by pytest if it is installed)
"""

import io
import os
import sys
import unittest
from datetime import date, datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import people_status as ps  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Semester, Session as SessionModel, DeviceToken,
)
from utils import students_not_checked_in  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class PeopleStatusTestCase(unittest.TestCase):

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
        for bp in (auth_bp, admin_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.past = Semester(name='2024/2025 Second Semester', start_date=date(2025, 1, 1),
                             end_date=date(2025, 6, 1))
        self.now = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2099, 6, 1), is_active=True)
        db.session.add_all([self.dept, self.past, self.now])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.ada = self.student('Ada', 'MCT/20/0001')
        self.bayo = self.student('Bayo', 'MCT/20/0002')
        self.lect = self.lecturer('Dr Lead', 'STF/1')
        self.helper = self.lecturer('Dr Helper', 'STF/2')
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role, is_active=True,
                 requires_password_change=False, current_refresh_jti='jti-123')
        db.session.add(u)
        db.session.flush()
        return u

    def student(self, name, matric):
        st = Student(full_name=name, matric_number=matric, level='400', department_id=self.dept.id,
                     user_id=self.user(matric, 'student').id, device_id=f'phone-{matric}')
        db.session.add(st)
        db.session.flush()
        return st

    def lecturer(self, name, staff_id):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, coordinator, semester, co=()):
        c = Course(course_code=code, course_title=code, lecturer_id=coordinator.id,
                   department_id=self.dept.id, semester_id=semester.id)
        c.co_lecturers = list(co)
        db.session.add(c)
        db.session.flush()
        return c

    # ---- rules ------------------------------------------------------------------

    def test_suspension_switches_login_off_but_keeps_the_phone(self):
        ps.set_student_status(self.ada, 'suspended', 'Disciplinary panel')
        self.assertFalse(self.ada.user.is_active)
        self.assertIsNone(self.ada.user.current_refresh_jti)
        self.assertEqual(self.ada.device_id, 'phone-MCT/20/0001')
        ps.set_student_status(self.ada, 'active', 'Suspension served')
        self.assertTrue(self.ada.user.is_active)

    def push_token(self, person):
        db.session.add(DeviceToken(user_id=person.user_id, fcm_token=f'fcm-{person.id}',
                                   platform='android'))
        db.session.commit()

    def test_switching_a_login_off_stops_pushes(self):
        self.push_token(self.ada)
        ps.set_student_status(self.ada, 'expelled', 'Disciplinary panel')
        self.assertEqual(DeviceToken.query.count(), 0)

    def test_admin_unbind_stops_pushes_to_the_old_phone(self):
        # A student reports their phone stolen; the thief's phone must stop
        # getting their notifications.
        self.push_token(self.ada)
        self.sign_in()
        with mock.patch('blueprints.admin.send_push_notification'):
            self.client.post(f'/admin/students/unbind/{self.ada.id}')
        self.assertIsNone(db.session.get(Student, self.ada.id).device_id)
        self.assertEqual(DeviceToken.query.count(), 0)

    def test_graduation_releases_the_phone(self):
        ps.set_student_status(self.ada, 'graduated', 'Class of 2026')
        self.assertIsNone(self.ada.device_id)
        self.assertEqual(Student.query.count(), 2)                     # nothing deleted

    def test_reason_and_status_are_checked(self):
        with self.assertRaises(ps.StatusError):
            ps.set_student_status(self.ada, 'graduated', '   ')
        with self.assertRaises(ps.StatusError):
            ps.set_student_status(self.ada, 'left', 'wrong list')
        self.assertIsNone(ps.set_student_status(self.ada, 'active', 'no change'))

    def test_lecturer_who_coordinates_a_running_course_cannot_leave(self):
        self.course('MCT401', self.lect, self.now)
        with self.assertRaises(ps.StatusError) as e:
            ps.set_lecturer_status(self.lect, 'left', 'Resigned')
        self.assertIn('MCT401', str(e.exception))
        self.assertTrue(self.lect.user.is_active)
        # A finished course doesn't block, and On leave never does.
        ps.set_lecturer_status(self.lect, 'on_leave', 'Sabbatical')
        self.assertFalse(self.lect.user.is_active)

    def test_leaving_removes_running_co_lecturer_places_only(self):
        running = self.course('MCT401', self.lect, self.now, co=[self.helper])
        finished = self.course('MCT301', self.lect, self.past, co=[self.helper])
        ps.set_lecturer_status(self.helper, 'left', 'Resigned')
        db.session.commit()
        self.assertEqual(running.co_lecturers, [])
        self.assertEqual(finished.co_lecturers, [self.helper])          # history kept

    def test_mark_present_list_leaves_out_non_active_students(self):
        c = self.course('MCT401', self.lect, self.now)
        db.session.add_all([Enrollment(student_id=self.ada.id, course_id=c.id),
                            Enrollment(student_id=self.bayo.id, course_id=c.id)])
        session = SessionModel(course_id=c.id, is_active=True, session_date=date.today(),
                               start_time=datetime.now().time())
        db.session.add(session)
        ps.set_student_status(self.bayo, 'expelled', 'Senate decision')
        db.session.commit()
        self.assertEqual([s.full_name for s in students_not_checked_in(session)], ['Ada'])

    # ---- routes -------------------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def test_single_change_is_audited(self):
        self.sign_in()
        self.client.post(f'/admin/students/{self.ada.id}/status',
                         data={'status': 'withdrawn', 'reason': 'Transferred'})
        self.assertEqual(db.session.get(Student, self.ada.id).status, 'withdrawn')
        [entry] = AuditLog.query.filter_by(action='student.status').all()
        self.assertIn('Active -> Withdrawn', entry.summary)

    def test_coordinator_leaving_is_refused_by_the_route(self):
        self.sign_in()
        self.course('MCT401', self.lect, self.now)
        db.session.commit()
        self.client.post(f'/admin/lecturers/{self.lect.id}/status', data={'status': 'left', 'reason': 'x'})
        self.assertEqual(db.session.get(Lecturer, self.lect.id).status, 'active')

    def bulk(self, data, **form):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post('/admin/students/status/bulk', content_type='multipart/form-data',
                             data={'file': (io.BytesIO(data), 'grads.csv'), **form})
        return render.call_args.kwargs

    def test_bulk_previews_then_applies(self):
        kwargs = self.bulk(b'matric_number\nmct/20/0001\nMCT/20/0002\n', status='graduated', reason='Class of 2026')
        self.assertEqual(len(kwargs['changing']), 2)
        self.assertEqual(Student.query.filter_by(status='graduated').count(), 0)   # preview only

        self.client.post('/admin/students/status/bulk', data={
            'confirm': '1', 'ids': kwargs['ids_json'], 'status': 'graduated', 'reason': 'Class of 2026'})
        self.assertEqual(Student.query.filter_by(status='graduated').count(), 2)
        self.assertEqual(AuditLog.query.filter_by(action='student.status').count(), 2)
        self.assertEqual(AuditLog.query.filter_by(action='student.bulk_status').count(), 1)

    def test_bulk_with_an_unknown_id_changes_nobody(self):
        kwargs = self.bulk(b'MCT/20/0001\nMCT/99/9999\n', status='graduated', reason='x')
        self.assertEqual(kwargs['missing'], ['MCT/99/9999'])
        with mock.patch('blueprints.admin.render_template', return_value=''):
            self.client.post('/admin/students/status/bulk', data={
                'confirm': '1', 'ids': kwargs['ids_json'], 'status': 'graduated', 'reason': 'x'})
        self.assertEqual(Student.query.filter_by(status='graduated').count(), 0)

    def test_switched_off_web_user_is_signed_out(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.lect.user_id, 'STF/1', 'lecturer'
        ps.set_lecturer_status(self.lect, 'on_leave', 'Sabbatical')
        db.session.commit()
        resp = self.client.get('/admin/dashboard')
        self.assertEqual(resp.status_code, 302)
        with self.client.session_transaction() as s:
            self.assertNotIn('user_id', s)


    def test_filtered_roster_is_in_matric_order(self):
        # Lives here because this fixture already has students and an admin.
        # Added out of order; a department/level list reads like a register.
        self.student('Zainab', 'MCT/20/0000')
        db.session.commit()
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.get('/admin/students', query_string={'dept': self.dept.id, 'level': '400'})
            filtered = [st.matric_number for st in render.call_args.kwargs['students']]
            self.client.get('/admin/students')
            unfiltered = [st.matric_number for st in render.call_args.kwargs['students']]
        self.assertEqual(filtered, ['MCT/20/0000', 'MCT/20/0001', 'MCT/20/0002'])
        self.assertEqual(unfiltered[0], 'MCT/20/0000')            # newest first when unfiltered


if __name__ == '__main__':
    unittest.main()
