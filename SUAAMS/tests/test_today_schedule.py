"""Tests for the student app's Today list (GET /api/v1/student/schedule/today).

Every open app polls this every 30 seconds. It used to run two queries per
class (the session, then the student's attendance); now it runs two for the
whole day (2026-10-23 audit, finding 8). These pin what each class shows,
so the rewrite keeps the old answers, and that the query count no longer
grows with the number of classes:

  * a slot with no session yet: PENDING, not live,
  * a running session not tapped into: PENDING and live (the check-in card
    arms on this),
  * attended: PRESENT; ended without attending: ABSENT,
  * two sessions for one course today: the newest decides,
  * an unscheduled running session is added, marked ad_hoc; an unscheduled
    ended one isn't.

Run with:  python tests/test_today_schedule.py
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
from sqlalchemy import event  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, Course, Department, Enrollment, Faculty, Lecturer, Semester,
    Session as SessionModel, Student, Timetable, User,
)
from api.student import api_student_bp  # noqa: E402

TODAY = date(2026, 10, 8)   # a Thursday, inside the semester below


class TodayScheduleTestCase(unittest.TestCase):

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
        self.app.register_blueprint(api_student_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.sem = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        db.session.add_all([self.dept, self.sem])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lect = Lecturer(full_name='Dr Lead', staff_id='STF/1', department_id=self.dept.id,
                             user_id=self.user('STF/1', 'lecturer').id)
        db.session.add(self.lect)
        db.session.flush()
        self.student = Student(full_name='Ada', matric_number='MCT/20/0001', level='400',
                               department_id=self.dept.id,
                               user_id=self.user('MCT/20/0001', 'student').id)
        db.session.add(self.student)
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

    def course(self, code, hour=None):
        """An enrolled course, with a published slot today at `hour` if given."""
        c = Course(course_code=code, course_title=code, lecturer_id=self.lect.id,
                   department_id=self.dept.id, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student.id, course_id=c.id))
        if hour is not None:
            db.session.add(Timetable(course_id=c.id, semester_id=self.sem.id,
                                     day_of_week=TODAY.weekday(), start_time=time(hour),
                                     end_time=time(hour + 1), room='LT 1',
                                     is_published=True, created_by=self.admin.id))
        db.session.flush()
        return c

    def session(self, course, active, attended=False, start=None):
        s = SessionModel(course_id=course.id, session_date=TODAY, is_active=active,
                         start_time=start)
        db.session.add(s)
        db.session.flush()
        if attended:
            db.session.add(Attendance(student_id=self.student.id, session_id=s.id,
                                      status='present', method='nfc'))
        db.session.commit()
        return s

    def today(self):
        token = create_access_token(identity=str(self.student.user_id),
                                    additional_claims={'role': 'student'})
        with mock.patch('api.student.campus_today', return_value=TODAY):
            resp = self.client.get('/api/v1/student/schedule/today',
                                   headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(resp.status_code, 200)
        return {e['course_code']: e for e in resp.get_json()['today_protocol']}

    def statuses(self):
        return {code: (e['status'], e['session_live'], e.get('ad_hoc', False))
                for code, e in self.today().items()}

    # ---- what each class shows --------------------------------------------------------

    def test_each_status(self):
        self.course('NOT401', hour=8)                                    # not started
        self.session(self.course('LIV402', hour=10), active=True)        # live
        self.session(self.course('PRE403', hour=12), active=True, attended=True)
        self.session(self.course('ABS404', hour=14), active=False)       # ended, missed
        self.session(self.course('HOC405'), active=True)                 # unscheduled, live
        self.session(self.course('OLD406'), active=False)                # unscheduled, ended
        self.assertEqual(self.statuses(), {
            'NOT401': ('PENDING', False, False),
            'LIV402': ('PENDING', True, False),
            'PRE403': ('PRESENT', False, False),
            'ABS404': ('ABSENT', False, False),
            'HOC405': ('PENDING', True, True),
        })

    def test_newest_session_of_the_day_decides(self):
        c = self.course('TWO401', hour=8)
        self.session(c, active=False, attended=True)     # morning class, attended
        self.session(c, active=True)                     # a second one, running now
        self.assertEqual(self.statuses()['TWO401'], ('PENDING', True, False))

    def test_unscheduled_sessions_are_listed_by_start_time(self):
        self.session(self.course('LATE401'), active=True, start=time(11))
        self.session(self.course('EARLY402'), active=True, start=time(9))
        self.assertEqual(list(self.today()), ['EARLY402', 'LATE401'])

    # ---- cost -------------------------------------------------------------------------

    def queries_for_today(self):
        seen = []
        listener = lambda *args: seen.append(args[2])          # noqa: E731
        event.listen(db.engine, 'before_cursor_execute', listener)
        try:
            self.today()
        finally:
            event.remove(db.engine, 'before_cursor_execute', listener)
        return len(seen)

    def test_query_count_does_not_grow_with_classes(self):
        for i in range(2):
            self.session(self.course(f'A{i}', hour=8 + i), active=True, attended=True)
        two = self.queries_for_today()
        for i in range(6):
            self.session(self.course(f'B{i}', hour=10 + i), active=False)
        self.session(self.course('HOC'), active=True)
        self.assertEqual(self.queries_for_today(), two)


if __name__ == '__main__':
    unittest.main()
