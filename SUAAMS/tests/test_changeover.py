"""Tests for the semester changeover checklist (changeover.py and the admin
routes /admin/semesters/<id>/changeover[/tick]).

Pins:

  * each step's state is read from the data: courses in, every coordinator
    active, timetable published with no drafts, the semester active;
  * a new academic year adds graduate, promote and intake; a second
    semester doesn't;
  * promotion waits on activation, and the next step skips it;
  * graduate and intake are ticked by hand, logged, and can be unticked;
  * the door board's banner shows a semester starting soon that isn't
    ready, and goes once every step is done;
  * making the semester active from the checklist comes back to it.

Run with:  python tests/test_changeover.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import changeover  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, ChangeoverTick, Faculty, Department, User, Lecturer, Course, Semester,
    Student, Timetable, PromotionRun,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class ChangeoverTestCase(unittest.TestCase):

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
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id, programme_years=5)
        self.last = Semester(name='2025/2026 Second Semester', start_date=date(2026, 2, 1),
                             end_date=date(2026, 7, 1), is_active=True)
        self.first = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 14),
                              end_date=date(2027, 1, 29))
        self.second = Semester(name='2026/2027 Second Semester', start_date=date(2027, 2, 8),
                               end_date=date(2027, 7, 1))
        db.session.add_all([self.dept, self.last, self.first, self.second])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lect = self.lecturer('Dr Lead', 'STF/1')
        db.session.commit()

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

    def lecturer(self, name, staff_id, status='active'):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id,
                        user_id=self.user(staff_id, 'lecturer').id, status=status)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, semester, coordinator=None):
        c = Course(course_code=code, course_title=code, lecturer_id=(coordinator or self.lect).id,
                   department_id=self.dept.id, semester_id=semester.id)
        db.session.add(c)
        db.session.flush()
        return c

    def slot(self, course, published=True):
        db.session.add(Timetable(course_id=course.id, semester_id=course.semester_id, day_of_week=0,
                                 start_time=time(8), end_time=time(10), created_by=self.admin.id,
                                 is_published=published))
        db.session.flush()

    def steps(self, semester):
        return {s.key: s for s in changeover.checklist(semester)['steps']}

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    # ---- reading the data ----------------------------------------------------------

    def test_steps_follow_the_data(self):
        st = self.steps(self.first)
        self.assertFalse(st['courses'].done)
        self.assertEqual(st['coordinators'].fact, 'Once its courses are in')
        self.assertEqual(st['timetable'].fact, 'Not imported yet')

        gone = self.lecturer('Dr Gone', 'STF/9', status='left')
        ok = self.course('MCT401', self.first)
        self.course('MCT405', self.first, coordinator=gone)
        self.slot(ok)
        self.slot(ok, published=False)
        db.session.commit()
        st = self.steps(self.first)
        self.assertTrue(st['courses'].done)
        self.assertFalse(st['coordinators'].done)
        self.assertIn('MCT405', st['coordinators'].fact)
        self.assertFalse(st['timetable'].done)                     # a draft still waiting
        self.assertIn('1 draft waiting', st['timetable'].fact)
        self.assertFalse(st['active'].done)

    def test_a_new_year_adds_graduation_promotion_and_intake(self):
        self.assertIn('promote', self.steps(self.first))
        self.assertNotIn('promote', self.steps(self.second))          # same academic year
        self.assertTrue(changeover.is_new_year(self.first))
        self.assertFalse(changeover.is_new_year(self.last))            # first on record

    def test_promotion_waits_on_activation(self):
        state = changeover.checklist(self.first)
        promote = next(s for s in state['steps'] if s.key == 'promote')
        self.assertTrue(promote.blocked)
        self.assertEqual(state['next'], 'courses')
        self.first.is_active = True
        db.session.add(PromotionRun(academic_year='2026/2027', promoted=40, moves='{}'))
        db.session.commit()
        promote = self.steps(self.first)['promote']
        self.assertTrue(promote.done)
        self.assertEqual(promote.fact, '40 students promoted')

    def test_graduate_counts_final_years(self):
        for i, level in enumerate(('500', '400', '500')):
            db.session.add(Student(full_name=f'S{i}', matric_number=f'M{i}', level=level,
                                   department_id=self.dept.id, user_id=self.user(f'M{i}', 'student').id))
        db.session.commit()
        self.assertTrue(self.steps(self.first)['graduate'].fact.startswith('2 active students'))

    # ---- ticks ------------------------------------------------------------------------

    def test_manual_steps_are_ticked_logged_and_unticked(self):
        self.sign_in()
        url = f'/admin/semesters/{self.first.id}/changeover/tick'
        self.client.post(url, data={'step': 'graduate'})
        self.client.post(url, data={'step': 'graduate'})                       # twice: one tick
        self.assertEqual(ChangeoverTick.query.count(), 1)
        self.assertTrue(self.steps(self.first)['graduate'].done)
        self.assertEqual(AuditLog.query.filter_by(action='semester.changeover').count(), 1)
        self.client.post(url, data={'step': 'graduate', 'undo': '1'})
        self.assertFalse(self.steps(self.first)['graduate'].done)
        self.assertEqual(AuditLog.query.filter_by(action='semester.changeover').count(), 2)
        # Only the manual steps can be ticked.
        self.client.post(url, data={'step': 'active'})
        self.assertEqual(ChangeoverTick.query.count(), 0)

    def test_deleting_a_semester_takes_its_ticks(self):
        changeover.tick(self.second, 'intake', self.admin.id)
        db.session.commit()
        db.session.delete(self.second)
        db.session.commit()
        self.assertEqual(ChangeoverTick.query.count(), 0)

    # ---- banner and routes ---------------------------------------------------------------

    def test_banner_shows_a_semester_starting_soon_until_it_is_ready(self):
        self.assertIsNone(changeover.banner(today=date(2026, 8, 1)))          # 44 days out
        b = changeover.banner(today=date(2026, 9, 5))
        self.assertEqual((b['semester'].id, b['starts_in']), (self.first.id, 9))
        # Everything done: no banner.
        c = self.course('MCT401', self.first)
        self.slot(c)
        self.first.is_active = True
        self.last.is_active = False
        db.session.add(PromotionRun(academic_year='2026/2027', promoted=1, moves='{}'))
        for step in changeover.MANUAL:
            changeover.tick(self.first, step, self.admin.id)
        db.session.commit()
        self.assertIsNone(changeover.banner(today=date(2026, 9, 15)))

    def test_page_renders_and_activate_comes_back(self):
        self.app.template_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
        self.sign_in()
        page = self.client.get(f'/admin/semesters/{self.first.id}/changeover')
        self.assertEqual(page.status_code, 200)
        html = page.get_data(as_text=True)
        self.assertIn('Graduate the final years', html)
        self.assertIn('name="back" value="changeover"', html)
        resp = self.client.post('/admin/semesters', data={
            'action': 'activate', 'semester_id': self.first.id, 'back': 'changeover'})
        self.assertTrue(resp.headers['Location'].endswith(f'/admin/semesters/{self.first.id}/changeover'))
        self.assertTrue(db.session.get(Semester, self.first.id).is_active)


if __name__ == '__main__':
    unittest.main()
