"""Tests for starting and ending a class session (utils.start_class_session
/ end_class_session), now shared by the lecturer app and web portal.

These pin the rules both copies used to implement separately, plus the fix
for double sessions:

  * only the course's own lecturer can start or end it,
  * a second Start while one is running is refused,
  * End closes EVERY running session for the course, so a duplicate can't
    be left open accepting check-ins,
  * a session nobody ended on an earlier day doesn't block Start, and the
    sweep (close_stale_sessions) ends it so it counts as held.

(The row lock that stops two simultaneous Starts needs MySQL; SQLite, used
here, ignores it. What's tested is that End cleans up even if a duplicate
exists.)

Run with:  python tests/test_class_sessions.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

from models import (  # noqa: E402
    db, Faculty, Department, User, Lecturer, Course, Session as SessionModel,
)
from datetime import timedelta  # noqa: E402

from campus_time import campus_today  # noqa: E402
from utils import (  # noqa: E402
    start_class_session, end_class_session, close_stale_sessions, held_sessions,
)


class ClassSessionTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(dept)
        db.session.flush()

        def lecturer(name):
            u = User(username=name, password_hash='x', role='lecturer')
            db.session.add(u)
            db.session.flush()
            lect = Lecturer(full_name=name, staff_id=name, department_id=dept.id, user_id=u.id)
            db.session.add(lect)
            db.session.flush()
            return lect

        self.owner = lecturer('ade')
        self.other = lecturer('bola')
        self.course = Course(course_title='Control', course_code='MCT 401',
                             lecturer_id=self.owner.id, department_id=dept.id)
        db.session.add(self.course)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def running(self):
        return SessionModel.query.filter_by(course_id=self.course.id, is_active=True).count()

    def leftover(self, days_ago=1):
        """A session a lecturer never ended, from `days_ago` days back."""
        s = SessionModel(course_id=self.course.id, is_active=True,
                         session_date=campus_today() - timedelta(days=days_ago))
        db.session.add(s)
        db.session.commit()
        return s

    def test_leftover_from_yesterday_does_not_block_start(self):
        old = self.leftover()
        outcome, new = start_class_session(self.owner, self.course.id)
        self.assertEqual(outcome, 'started')
        self.assertFalse(db.session.get(SessionModel, old.id).is_active)
        self.assertEqual(self.running(), 1)
        self.assertEqual(new.session_date, campus_today())

    def test_sweep_ends_earlier_days_only_and_they_count_as_held(self):
        old = self.leftover()
        start_class_session(self.owner, self.course.id)  # today's, running
        self.leftover(days_ago=3)
        self.assertEqual(close_stale_sessions(force=True), 1)
        today = SessionModel.query.filter_by(session_date=campus_today()).one()
        self.assertTrue(today.is_active)
        self.assertFalse(db.session.get(SessionModel, old.id).is_active)
        # Both earlier classes are now finished, so both count as held.
        self.assertEqual(held_sessions([self.course.id]), {self.course.id: 2})

    def test_sweep_runs_at_most_every_ten_minutes(self):
        close_stale_sessions(force=True)
        self.leftover()
        self.assertEqual(close_stale_sessions(), 0)   # inside the window
        self.assertEqual(close_stale_sessions(force=True), 1)

    def test_start_then_second_start_is_refused(self):
        outcome, first = start_class_session(self.owner, self.course.id)
        self.assertEqual(outcome, 'started')
        outcome, running = start_class_session(self.owner, self.course.id)
        self.assertEqual(outcome, 'already_active')
        self.assertEqual(running.id, first.id)
        self.assertEqual(self.running(), 1)

    def test_other_lecturer_cannot_start_or_end(self):
        self.assertEqual(start_class_session(self.other, self.course.id)[0], 'not_found')
        start_class_session(self.owner, self.course.id)
        self.assertEqual(end_class_session(self.other, self.course.id)[0], 'not_found')
        self.assertEqual(self.running(), 1)

    def test_end_closes_every_running_session(self):
        # A duplicate, as two simultaneous Starts used to create.
        db.session.add_all([SessionModel(course_id=self.course.id, is_active=True),
                            SessionModel(course_id=self.course.id, is_active=True)])
        db.session.commit()
        outcome, latest = end_class_session(self.owner, self.course.id)
        self.assertEqual(outcome, 'ended')
        self.assertEqual(self.running(), 0)
        self.assertIsNotNone(latest.stop_time)

    def test_end_with_nothing_running(self):
        self.assertEqual(end_class_session(self.owner, self.course.id)[0], 'none_active')


if __name__ == '__main__':
    unittest.main()
