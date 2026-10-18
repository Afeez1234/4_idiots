"""The "now" screens show the current semester only (utils.current_courses
and friends, 2026-10-18).

Enrolments and published timetables never expire, so before this every
student and lecturer screen mixed last year with this year after a
changeover: last year's classes in a student's Today and Week, two MCT401s
in a lecturer's courses, several years blended in an HOD's figures -- and a
lecturer could start a class on last year's course, taking check-ins from
last year's class list. Pins:

  * student app Today, Week and Dashboard: this semester's courses and slots,
    plus courses with no semester, whose slots are matched on the SLOT's
    semester,
  * lecturer app dashboard and week, web dashboard: this semester only,
  * starting a class on a past-semester course is refused, app and web,
  * HOD dashboard counts this semester's courses,
  * no active semester: everything shows, as before,
  * history (a course's attendance history) still reaches past courses.

Run with:  python tests/test_current_semester.py
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
    db, Course, Department, Enrollment, Faculty, HOD, Lecturer, Semester,
    Session as SessionModel, Student, Timetable, User,
)
from api.student import api_student_bp  # noqa: E402
from api.lecturer import api_lecturer_bp  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.lecturer import lecturer_bp  # noqa: E402
from blueprints.hod import hod_bp  # noqa: E402

# A Thursday.
TODAY = date(2026, 10, 8)


class CurrentSemesterTestCase(unittest.TestCase):

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
        self.app.register_blueprint(api_student_bp, url_prefix='/api/student')
        self.app.register_blueprint(api_lecturer_bp, url_prefix='/api/lecturer')
        for bp in (auth_bp, lecturer_bp, hod_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.mct = Department(name='Mechatronics', faculty_id=faculty.id)
        self.now = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        self.old = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2026, 1, 31))
        db.session.add_all([self.mct, self.now, self.old])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lect = Lecturer(full_name='Dr Lead', staff_id='STF/1', department_id=self.mct.id,
                             user_id=self.user('STF/1', 'lecturer').id)
        db.session.add(self.lect)
        db.session.flush()

        # The same code last year and this year, plus a general course with
        # no semester that has slots in both semesters.
        self.new401 = self.course('NEW401', self.now)
        self.old401 = self.course('OLD401', self.old)
        self.gst = self.course('GST212', None)
        day = TODAY.weekday()
        self.slot(self.new401, self.now, day, 8)
        self.slot(self.old401, self.old, day, 10)          # last year, still published
        self.slot(self.gst, self.now, day, 12)
        self.slot(self.gst, self.old, day, 14)             # last year's GST slot

        self.student = Student(full_name='Ada', matric_number='MCT/20/0001', level='400',
                               department_id=self.mct.id, user_id=self.user('MCT/20/0001', 'student').id)
        db.session.add(self.student)
        db.session.flush()
        for c in (self.new401, self.old401, self.gst):
            db.session.add(Enrollment(student_id=self.student.id, course_id=c.id))
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures -----------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role, is_active=True,
                 requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        return u

    def course(self, code, semester):
        c = Course(course_code=code, course_title=code, lecturer_id=self.lect.id,
                   department_id=self.mct.id, semester_id=semester.id if semester else None)
        db.session.add(c)
        db.session.flush()
        return c

    def slot(self, course, semester, day, hour):
        db.session.add(Timetable(course_id=course.id, semester_id=semester.id, day_of_week=day,
                                 start_time=time(hour), end_time=time(hour + 1), room='LT 1',
                                 is_published=True, created_by=self.admin.id))

    def api(self, path, role, user_id, method='get'):
        token = create_access_token(identity=str(user_id), additional_claims={'role': role})
        # POSTs send a JSON body, as the app does (start-session reads JSON).
        extra = {'json': {}} if method == 'post' else {}
        with mock.patch('api.student.campus_today', return_value=TODAY):
            return getattr(self.client, method)(path, headers={'Authorization': f'Bearer {token}'}, **extra)

    def student_api(self, path):
        return self.api(path, 'student', self.student.user_id)

    def lecturer_api(self, path, method='get'):
        return self.api(path, 'lecturer', self.lect.user_id, method)

    def web_sign_in(self, user_id, role):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = user_id, 'x', role

    # ---- student app ------------------------------------------------------------------

    def test_student_today_is_this_semesters_classes_only(self):
        body = self.student_api('/api/student/schedule/today').get_json()
        codes = [e['course_code'] for e in body['today_protocol']]
        # NEW401 at 08:00 and GST212 at 12:00; not OLD401, not last year's
        # GST slot at 14:00.
        self.assertEqual(sorted(codes), ['GST212', 'NEW401'])

    def test_student_week_is_this_semesters_classes_only(self):
        week = self.student_api('/api/student/schedule/week').get_json()['week']
        self.assertEqual(sorted((e['course_code'], e['start_time'][:5]) for e in week),
                         [('GST212', '12:00'), ('NEW401', '08:00')])

    def test_student_dashboard_lists_this_semesters_courses(self):
        text = self.student_api('/api/student/dashboard').get_data(as_text=True)
        self.assertIn('NEW401', text)
        self.assertIn('GST212', text)
        self.assertNotIn('OLD401', text)

    def test_past_course_history_is_still_reachable(self):
        resp = self.student_api(f'/api/student/course/{self.old401.id}/history')
        self.assertEqual(resp.status_code, 200)

    # ---- lecturer app and web -------------------------------------------------------------

    def test_lecturer_dashboard_and_week_are_this_semester(self):
        text = self.lecturer_api('/api/lecturer/dashboard').get_data(as_text=True)
        self.assertIn('NEW401', text)
        self.assertNotIn('OLD401', text)
        week = self.lecturer_api('/api/lecturer/schedule/week').get_json()['week']
        self.assertEqual(sorted(e['course_code'] for e in week), ['GST212', 'NEW401'])

    def test_lecturer_web_dashboard_is_this_semester(self):
        self.web_sign_in(self.lect.user_id, 'lecturer')
        with mock.patch('blueprints.lecturer.render_template', return_value='') as render:
            self.client.get('/lecturer/dashboard')
        codes = {card['course'].course_code for card in render.call_args.kwargs['course_cards']}
        self.assertEqual(codes, {'NEW401', 'GST212'})

    def test_a_class_cant_be_started_on_a_past_course(self):
        resp = self.lecturer_api(f'/api/lecturer/course/{self.old401.id}/start-session', 'post')
        self.assertEqual(resp.status_code, 409)
        self.assertIn('2025/2026 First Semester', resp.get_json()['error'])
        # Web: refused too, with a message.
        self.web_sign_in(self.lect.user_id, 'lecturer')
        self.client.post(f'/lecturer/course/{self.old401.id}/start-session', data={})
        self.assertEqual(SessionModel.query.count(), 0)
        # This semester's course still starts.
        ok = self.lecturer_api(f'/api/lecturer/course/{self.new401.id}/start-session', 'post')
        self.assertEqual(ok.status_code, 201)

    # ---- HOD ------------------------------------------------------------------------------

    def test_hod_dashboard_counts_this_semesters_courses(self):
        hod_user = self.user('HOD/1', 'hod')
        db.session.add(HOD(full_name='Prof H', staff_id='HOD/1', department_id=self.mct.id,
                           user_id=hod_user.id))
        db.session.commit()
        self.web_sign_in(hod_user.id, 'hod')
        with mock.patch('blueprints.hod.render_template', return_value='') as render:
            self.client.get('/hod/dashboard')
        self.assertEqual(render.call_args.kwargs['course_count'], 2)   # NEW401, GST212

    # ---- no active semester -----------------------------------------------------------------

    def test_no_active_semester_shows_everything_as_before(self):
        self.now.is_active = False
        db.session.commit()
        codes = [e['course_code'] for e in
                 self.student_api('/api/student/schedule/today').get_json()['today_protocol']]
        self.assertEqual(sorted(codes), ['GST212', 'GST212', 'NEW401', 'OLD401'])


if __name__ == '__main__':
    unittest.main()
