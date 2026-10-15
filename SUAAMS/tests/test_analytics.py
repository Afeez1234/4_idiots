"""Tests for admin Analytics (analytics.py, /admin/analytics and
/admin/analytics/eligibility.csv).

Pins:

  * eligibility uses the course register's rule: finished sessions only,
    present or late counts, below means < 75%; a course is only checked
    once it has held MIN_SESSIONS; students who aren't active are left out;
    department and level filters; the roll-ups count everyone in scope;
  * the CSV matches the page and is audited;
  * delivery counts each slot once a week from teaching start to today
    (today's only once it has ended), matches sessions by timetable_id or
    course + weekday + planned_start, counts two sessions on one class once,
    and shows unmatched sessions as extra; a slot added or moved later
    counts from its own start date, and classes held before it are extra;
  * neither runs more queries as courses and students are added.

Run with:  python tests/test_analytics.py
(also collected by pytest if it is installed)
"""

import csv
import io
import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402
from sqlalchemy import event  # noqa: E402

import analytics  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, AuditLog, Course, Department, Enrollment, Faculty, Lecturer,
    Semester, Session as SessionModel, Student, Timetable, User,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

MONDAY = 0
# Teaching starts Monday 7 Sep; "now" is Monday 5 Oct, 12:00 -- five Mondays.
FIRST_CLASS = date(2026, 9, 7)
NOW = datetime(2026, 10, 5, 12, 0)


class AnalyticsTestCase(unittest.TestCase):

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
        self.mct = Department(name='Mechatronics', faculty_id=faculty.id)
        self.csc = Department(name='Computer', faculty_id=faculty.id)
        self.sem = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        db.session.add_all([self.mct, self.csc, self.sem])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        u = self.user('STF/1', 'lecturer')
        self.lect = Lecturer(full_name='Dr Lead', staff_id='STF/1', department_id=self.mct.id, user_id=u.id)
        db.session.add(self.lect)
        db.session.flush()
        self.c401 = self.course('MCT 401', self.mct)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures ---------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role, is_active=True,
                 requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        return u

    def course(self, code, dept):
        c = Course(course_code=code, course_title=code, lecturer_id=self.lect.id,
                   department_id=dept.id, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        return c

    def student(self, matric, dept=None, level='400', courses=(), status='active'):
        st = Student(full_name=matric, matric_number=matric, level=level, status=status,
                     department_id=(dept or self.mct).id, user_id=self.user(matric, 'student').id)
        db.session.add(st)
        db.session.flush()
        for c in courses:
            db.session.add(Enrollment(student_id=st.id, course_id=c.id))
        db.session.flush()
        return st

    def sessions(self, course, n, active=False):
        out = []
        for i in range(n):
            s = SessionModel(course_id=course.id, session_date=FIRST_CLASS + timedelta(days=7 * i),
                             is_active=active)
            db.session.add(s)
            out.append(s)
        db.session.flush()
        return out

    def attend(self, student, sessions, status='present'):
        for s in sessions:
            db.session.add(Attendance(student_id=student.id, session_id=s.id, status=status))
        db.session.flush()

    def slot(self, course, weekday=MONDAY, start=(9, 0), end=(11, 0), published=True):
        s = Timetable(course_id=course.id, semester_id=self.sem.id, day_of_week=weekday,
                      start_time=time(*start), end_time=time(*end), created_by=self.admin.id,
                      is_published=published)
        db.session.add(s)
        db.session.flush()
        return s

    def held(self, course, on, slot=None, planned=None):
        s = SessionModel(course_id=course.id, session_date=on, is_active=False,
                         timetable_id=slot.id if slot else None,
                         planned_start=time(*planned) if planned else None)
        db.session.add(s)
        db.session.flush()
        return s

    def below(self, **filters):
        got = analytics.eligibility(self.sem, **filters)
        return {r['student'].matric_number: [(c['course'].course_code, c['pct']) for c in r['courses']]
                for r in got['students']}

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    # ---- eligibility ------------------------------------------------------------

    def test_register_rule_finished_classes_present_or_late(self):
        done = self.sessions(self.c401, 4)
        self.sessions(self.c401, 1, active=True)                   # running: not counted
        ada = self.student('ADA', courses=[self.c401])
        bayo = self.student('BAYO', courses=[self.c401])
        self.attend(ada, done[:2])                                 # 50%
        self.attend(bayo, done[:2])
        self.attend(bayo, done[2:3], status='late')                # 75%: not below
        db.session.commit()
        self.assertEqual(self.below(), {'ADA': [('MCT 401', 50.0)]})

    def test_excused_does_not_count_as_attended(self):
        done = self.sessions(self.c401, 4)
        ada = self.student('ADA', courses=[self.c401])
        self.attend(ada, done[:3], status='excused')
        db.session.commit()
        self.assertEqual(self.below(), {'ADA': [('MCT 401', 0.0)]})

    def test_course_needs_min_sessions_before_flagging(self):
        self.sessions(self.c401, analytics.MIN_SESSIONS - 1)
        self.student('ADA', courses=[self.c401])
        db.session.commit()
        self.assertEqual(self.below(), {})

    def test_students_who_left_are_not_listed(self):
        self.sessions(self.c401, 3)
        self.student('GONE', courses=[self.c401], status='graduated')
        db.session.commit()
        self.assertEqual(self.below(), {})

    def test_filters_and_rollups(self):
        c301 = self.course('CSC 301', self.csc)
        self.sessions(self.c401, 3)
        done = self.sessions(c301, 3)
        self.student('MCT-A', courses=[self.c401])                       # below
        ok = self.student('CSC-B', dept=self.csc, level='300', courses=[c301])
        self.attend(ok, done)
        self.student('CSC-C', dept=self.csc, level='300', courses=[c301])  # below
        db.session.commit()
        self.assertEqual(set(self.below(department_id=self.csc.id)), {'CSC-C'})
        self.assertEqual(set(self.below(level='400')), {'MCT-A'})
        got = analytics.eligibility(self.sem)
        self.assertEqual({r['name']: (r['below'], r['total']) for r in got['by_department']},
                         {'Mechatronics': (1, 1), 'Computer': (1, 2)})
        self.assertEqual({r['level']: (r['below'], r['total']) for r in got['by_level']},
                         {'300': (1, 2), '400': (1, 1)})

    def test_csv_lists_each_course_below_and_is_audited(self):
        c405 = self.course('MCT 405', self.mct)
        self.sessions(self.c401, 3)
        self.sessions(c405, 3)
        self.student('ADA', courses=[self.c401, c405])
        db.session.commit()
        self.sign_in()
        response = self.client.get('/admin/analytics/eligibility.csv')
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(sorted(r[4] for r in rows[2:]), ['MCT 401', 'MCT 405'])
        self.assertEqual(AuditLog.query.filter_by(action='analytics.export').count(), 1)

    # ---- delivery ---------------------------------------------------------------

    def test_occurrences(self):
        self.assertEqual(analytics._occurrences(MONDAY, date(2026, 9, 7), date(2026, 10, 5)), 5)
        self.assertEqual(analytics._occurrences(MONDAY, date(2026, 9, 8), date(2026, 9, 13)), 0)

    def delivery(self, now=NOW, **kw):
        got = analytics.delivery(self.sem, now=now, **kw)
        return {r['course'].course_code: (r['timetabled'], r['held'], r['missed'], r['extra'])
                for r in got['courses']}

    def test_held_vs_timetabled(self):
        s = self.slot(self.c401)
        self.held(self.c401, FIRST_CLASS, slot=s)                         # by timetable_id
        self.held(self.c401, date(2026, 9, 14), planned=(9, 0))           # older: by planned_start
        self.held(self.c401, date(2026, 9, 21), slot=s)
        self.held(self.c401, date(2026, 9, 21), slot=s)                   # opened twice: one class
        self.held(self.c401, date(2026, 9, 23))                           # no slot: extra
        self.slot(self.c401, weekday=2, published=False)                  # draft: ignored
        db.session.commit()
        # 5 Mondays from 7 Sep to 5 Oct (today's 9-11 class has ended).
        self.assertEqual(self.delivery(), {'MCT 401': (5, 3, 2, 1)})

    def test_todays_class_is_due_only_once_it_ends(self):
        self.slot(self.c401)
        self.held(self.c401, FIRST_CLASS, planned=(9, 0))
        db.session.commit()
        self.assertEqual(self.delivery(now=datetime(2026, 10, 5, 10, 0))['MCT 401'][0], 4)

    def test_nothing_due_before_teaching_starts(self):
        self.slot(self.c401)
        db.session.commit()
        got = analytics.delivery(self.sem, now=NOW)
        self.assertIsNone(got['teaching_start'])
        self.assertEqual(got['courses'], [])

    def test_department_filter(self):
        c301 = self.course('CSC 301', self.csc)
        self.slot(self.c401)
        self.slot(c301)
        self.held(c301, FIRST_CLASS, planned=(9, 0))
        db.session.commit()
        self.assertEqual(set(self.delivery(department_id=self.mct.id)), {'MCT 401'})
        # Teaching start is the school's, so MCT's 5 Mondays still count.
        self.assertEqual(self.delivery(department_id=self.mct.id)['MCT 401'], (5, 0, 5, 0))

    def test_a_class_added_mid_semester_counts_from_its_start(self):
        s = self.slot(self.c401)
        s.effective_from = date(2026, 9, 28)              # added in week 4
        self.held(self.c401, FIRST_CLASS)                 # sets teaching start
        self.held(self.c401, date(2026, 9, 28), slot=s)
        db.session.commit()
        # Mondays 28 Sep and 5 Oct only; the 7 Sep class was before the slot.
        self.assertEqual(self.delivery()['MCT 401'], (2, 1, 1, 1))

    def test_a_moved_class_does_not_count_back_to_week_one(self):
        # Moved from Monday to Wednesday on 23 Sep: the old Monday sessions
        # are history (extra), not held Wednesdays, and Wednesdays before
        # the move aren't missed.
        wed = self.slot(self.c401, weekday=2)
        wed.effective_from = date(2026, 9, 23)
        for day in (7, 14, 21):
            self.held(self.c401, date(2026, 9, day), planned=(9, 0))
        self.held(self.c401, date(2026, 9, 23), slot=wed)
        self.held(self.c401, date(2026, 9, 30), slot=wed)
        db.session.commit()
        self.assertEqual(self.delivery()['MCT 401'], (2, 2, 0, 3))

    def test_a_department_with_nothing_due_yet_has_no_rate(self):
        # Every slot in it was added today (or starts later this week): the
        # page must show "nothing due yet", not divide by zero or crash.
        s = self.slot(self.c401)
        s.effective_from = NOW.date()
        self.held(self.c401, FIRST_CLASS)                 # teaching has started
        db.session.commit()
        got = analytics.delivery(self.sem, now=datetime(2026, 10, 5, 8, 0))   # before 09:00
        self.assertEqual([(r['timetabled'], r['rate']) for r in got['by_department']], [(0, None)])

    def past_semester(self):
        old = Semester(name='2025/2026 Second Semester', start_date=date(2026, 2, 1),
                       end_date=date(2026, 7, 1))
        db.session.add(old)
        db.session.flush()
        course = Course(course_code='MCT 302', course_title='Old', lecturer_id=self.lect.id,
                        department_id=self.mct.id, semester_id=old.id)
        db.session.add(course)
        db.session.flush()
        for i in range(3):
            db.session.add(SessionModel(course_id=course.id, session_date=date(2026, 3, 2 + 7 * i),
                                        is_active=False))
        # Below the threshold then, graduated since.
        self.student('GRAD', courses=[course], status='graduated')
        db.session.commit()
        return old

    def test_a_past_semester_is_picked_without_changing_the_active_one(self):
        old = self.past_semester()
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            self.client.get('/admin/analytics', query_string={'semester': old.id})
        kwargs = render.call_args.kwargs
        self.assertEqual(kwargs['semester'].id, old.id)
        self.assertTrue(db.session.get(Semester, self.sem.id).is_active)    # untouched
        # A past semester keeps students who have since left.
        self.assertEqual([r['student'].matric_number for r in kwargs['eligibility']['students']],
                         ['GRAD'])
        # The same student isn't listed under the active semester.
        self.assertEqual(analytics.eligibility(self.sem)['students'], [])

    def test_csv_follows_the_picked_semester(self):
        old = self.past_semester()
        self.sign_in()
        response = self.client.get('/admin/analytics/eligibility.csv', query_string={'semester': old.id})
        rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
        self.assertIn('2025/2026 Second Semester', rows[0][0])
        self.assertEqual([r[0] for r in rows[2:]], ['GRAD'])

    def test_page_renders(self):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            response = self.client.get('/admin/analytics', query_string={'dept': self.mct.id, 'level': '400'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(render.call_args.kwargs['filters'], {'dept': self.mct.id, 'level': '400'})

    # ---- page cost --------------------------------------------------------------

    def test_queries_do_not_grow(self):
        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                analytics.eligibility(self.sem)
                analytics.delivery(self.sem, now=NOW)
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen)

        def add(n, start):
            for i in range(n):
                c = self.course(f'X{start + i}', self.csc)
                self.slot(c)
                done = self.sessions(c, 3)
                for j in range(3):
                    st = self.student(f'S{start + i}-{j}', dept=self.csc, courses=[c])
                    self.attend(st, done[:j])
            db.session.commit()
            db.session.expire_all()

        add(1, 0)
        few = queries()
        add(6, 100)
        self.assertEqual(few, queries())


if __name__ == '__main__':
    unittest.main()
