"""Tests for the reader door-screen status (terminal_status.py and
GET /api/v1/terminal/status in api/terminal.py).

Pins:

  * "now" is the live session in the reader's room -- matched loosely,
    like the wrong-room check -- with present (present + late only) out of
    enrolled, and when it ends (planned end, else the slot's end);
  * a second live class in the same room shows as "more", not a swap;
  * "next" is today's earliest remaining published slot in that room, this
    semester only -- not another room's, not an unpublished or past one,
    not last semester's;
  * a reader with no room, or on the old shared secret, gets all nulls;
  * the route needs the reader's own signature.

Run with:  python tests/test_terminal_status.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, datetime, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

import terminal_rooms  # noqa: E402
from extensions import limiter  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, Course, Department, Enrollment, Faculty, Lecturer, Semester,
    Session as SessionModel, Student, Terminal, Timetable, User,
)
from terminal_status import status_for  # noqa: E402
from api.terminal import api_terminal_bp  # noqa: E402

# A Tuesday at 10:00 campus time.
NOW = datetime(2026, 10, 20, 10, 0)
TUESDAY = NOW.weekday()
SECRETS = {'TERMINAL_ID': 'shared-01', 'TERMINAL_SECRET': 'shared-secret'}


class TerminalStatusTestCase(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, SECRETS)
        self.env.start()
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                               TESTING=True, RATELIMIT_ENABLED=False)
        db.init_app(self.app)
        limiter.init_app(self.app)
        self.app.register_blueprint(api_terminal_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.sem = Semester(name='S1', start_date=date(2026, 9, 1), end_date=date(2099, 1, 1), is_active=True)
        self.old_sem = Semester(name='S0', start_date=date(2026, 1, 1), end_date=date(2026, 6, 1), is_active=False)
        db.session.add_all([self.dept, self.sem, self.old_sem])
        db.session.flush()
        self.admin = self.user('admin', 'admin')
        lu = self.user('STF/1', 'lecturer')
        lecturer = Lecturer(full_name='Dr Ade', staff_id='STF/1', department_id=self.dept.id, user_id=lu.id)
        db.session.add(lecturer)
        db.session.flush()
        self.lecturer = lecturer
        self.mct401 = self.course('MCT 401')
        self.mct405 = self.course('MCT 405')

        # Three enrolled students; the 10:00 class in LT 1 is live.
        self.students = [self.student(f'MCT/{i}', self.mct401) for i in range(3)]
        self.slot = self.add_slot(self.mct401, time(9, 0), time(11, 0), 'LT 1')
        self.live = SessionModel(course_id=self.mct401.id, session_date=NOW.date(),
                                 is_active=True, timetable_id=self.slot.id)
        db.session.add(self.live)
        db.session.flush()

        self.lt1 = self.reader('T-01', 'LT 1')
        self.lt2 = self.reader('T-02', 'LT 2')
        self.roomless = self.reader('T-03', None)
        db.session.commit()

    def tearDown(self):
        self.env.stop()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures -----------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, role=role, is_active=True, password_hash='x')
        db.session.add(u)
        db.session.flush()
        return u

    def course(self, code):
        c = Course(course_code=code, course_title=code, lecturer_id=self.lecturer.id,
                   department_id=self.dept.id, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        return c

    def student(self, matric, course):
        u = self.user(matric, 'student')
        s = Student(full_name=matric, matric_number=matric, level='400',
                    department_id=self.dept.id, user_id=u.id)
        db.session.add(s)
        db.session.flush()
        db.session.add(Enrollment(student_id=s.id, course_id=course.id))
        return s

    def add_slot(self, course, start, end, room, semester=None, published=True, day=TUESDAY):
        slot = Timetable(course_id=course.id, semester_id=(semester or self.sem).id,
                         day_of_week=day, start_time=start, end_time=end, room=room,
                         created_by=self.admin.id, is_published=published)
        db.session.add(slot)
        db.session.flush()
        return slot

    def reader(self, code, room):
        t = Terminal(code=code, name=code, room=room,
                     secret_hash=terminal_rooms.hash_secret(f'secret-{code}'))
        db.session.add(t)
        db.session.flush()
        return t

    def mark(self, student, status):
        db.session.add(Attendance(student_id=student.id, session_id=self.live.id,
                                  status=status, method='nfc'))
        db.session.commit()

    # ---- now ----------------------------------------------------------------------

    def test_live_class_in_the_readers_room(self):
        self.mark(self.students[0], 'present')
        self.mark(self.students[1], 'late')     # late still counts as attended
        self.mark(self.students[2], 'absent')   # absent doesn't
        status = status_for(self.lt1, now=NOW)
        self.assertEqual(status['room'], 'LT 1')
        self.assertEqual(status['now'], {
            'course_code': 'MCT 401', 'ends': '11:00',
            'present': 2, 'enrolled': 3, 'more': 0,
        })

    def test_planned_end_beats_the_slot(self):
        self.live.planned_end = time(10, 45)
        db.session.commit()
        self.assertEqual(status_for(self.lt1, now=NOW)['now']['ends'], '10:45')

    def test_room_given_at_start_beats_the_slot(self):
        # Moved to LT 2 for the day: LT 2's reader shows it, LT 1's doesn't.
        self.live.room = 'LT 2'
        db.session.commit()
        self.assertEqual(status_for(self.lt2, now=NOW)['now']['course_code'], 'MCT 401')
        self.assertIsNone(status_for(self.lt1, now=NOW)['now'])

    def test_rooms_match_loosely(self):
        self.lt1.room = 'lt-1'
        db.session.commit()
        self.assertEqual(status_for(self.lt1, now=NOW)['now']['course_code'], 'MCT 401')

    def test_other_room_sees_nothing_live(self):
        self.assertIsNone(status_for(self.lt2, now=NOW)['now'])

    def test_ended_session_isnt_live(self):
        self.live.is_active = False
        db.session.commit()
        self.assertIsNone(status_for(self.lt1, now=NOW)['now'])

    def test_second_live_class_in_the_room_is_more(self):
        db.session.add(SessionModel(course_id=self.mct405.id, session_date=NOW.date(),
                                    is_active=True, room='LT 1'))
        db.session.commit()
        status = status_for(self.lt1, now=NOW)['now']
        self.assertEqual((status['course_code'], status['more']), ('MCT 401', 1))

    # ---- next ---------------------------------------------------------------------

    def test_next_is_the_earliest_remaining_slot_in_the_room(self):
        self.add_slot(self.mct405, time(16, 0), time(17, 0), 'LT 1')
        self.add_slot(self.mct405, time(14, 0), time(15, 0), 'LT 1')
        self.add_slot(self.mct405, time(12, 0), time(13, 0), 'LT 2')   # other room
        self.add_slot(self.mct405, time(8, 0), time(8, 30), 'LT 1')    # already past
        db.session.commit()
        self.assertEqual(status_for(self.lt1, now=NOW)['next'],
                         {'course_code': 'MCT 405', 'starts': '14:00'})

    def test_next_ignores_unpublished_other_days_and_last_semester(self):
        self.add_slot(self.mct405, time(12, 0), time(13, 0), 'LT 1', published=False)
        self.add_slot(self.mct405, time(12, 0), time(13, 0), 'LT 1', day=(TUESDAY + 1) % 7)
        self.add_slot(self.mct405, time(12, 0), time(13, 0), 'LT 1', semester=self.old_sem)
        db.session.commit()
        self.assertIsNone(status_for(self.lt1, now=NOW)['next'])

    def test_no_class_now_but_one_later(self):
        self.live.is_active = False
        self.add_slot(self.mct405, time(14, 0), time(15, 0), 'LT 1')
        db.session.commit()
        status = status_for(self.lt1, now=NOW)
        self.assertIsNone(status['now'])
        self.assertEqual(status['next']['course_code'], 'MCT 405')

    # ---- due (timetabled now, not started) ----------------------------------------

    def test_timetabled_now_but_not_started_is_due(self):
        # The 09:00-11:00 slot is under way and nobody has started it.
        self.live.is_active = False
        db.session.commit()
        status = status_for(self.lt1, now=NOW)
        self.assertIsNone(status['now'])
        self.assertEqual(status['due'], {'course_code': 'MCT 401', 'starts': '09:00', 'ends': '11:00'})

    def test_due_is_dropped_once_the_class_is_live(self):
        self.assertIsNone(status_for(self.lt1, now=NOW)['due'])

    def test_finished_or_other_room_slot_isnt_due(self):
        self.live.is_active = False
        self.slot.end_time = time(9, 30)   # finished before 10:00
        self.add_slot(self.mct405, time(9, 30), time(10, 30), 'LT 2')
        db.session.commit()
        self.assertIsNone(status_for(self.lt1, now=NOW)['due'])

    def test_due_and_next_together(self):
        self.live.is_active = False
        self.add_slot(self.mct405, time(14, 0), time(15, 0), 'LT 1')
        db.session.commit()
        status = status_for(self.lt1, now=NOW)
        self.assertEqual(status['due']['course_code'], 'MCT 401')
        self.assertEqual(status['next']['course_code'], 'MCT 405')

    # ---- readers the server can't place ---------------------------------------------

    def test_reader_with_no_room_gets_nothing(self):
        self.assertEqual(status_for(self.roomless, now=NOW), {'room': None, 'now': None, 'due': None, 'next': None})

    def test_unregistered_shared_secret_reader_gets_nothing(self):
        self.assertEqual(status_for(None, now=NOW), {'room': None, 'now': None, 'due': None, 'next': None})

    # ---- the route ----------------------------------------------------------------

    def get(self, code, secret):
        return self.client.get('/api/v1/terminal/status',
                               headers={'X-Terminal-Id': code, 'X-Terminal-Secret': secret})

    def test_route_needs_the_readers_signature(self):
        self.assertEqual(self.client.get('/api/v1/terminal/status').status_code, 401)
        self.assertEqual(self.get('T-01', 'wrong').status_code, 401)

    def test_route_answers_for_the_signed_reader(self):
        resp = self.get('T-01', 'secret-T-01')
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body['room'], 'LT 1')
        self.assertEqual(body['now']['course_code'], 'MCT 401')

    def test_route_for_shared_secret_reader(self):
        resp = self.get('shared-01', 'shared-secret')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {'room': None, 'now': None, 'due': None, 'next': None})


if __name__ == '__main__':
    unittest.main(verbosity=2)
