"""Tests for copying a previous semester's timetable (timetable_import.plan_copy,
default_copy_source and the admin route /admin/timetable/copy).

Pins:

  * the default source is the same semester a year earlier, never the
    other semester of the same year;
  * only PUBLISHED classes are copied, matched to this semester's courses
    by code, grouped one "sheet" per department and level;
  * a course that no longer exists is left out with a note -- it does NOT
    block the rest; a clash still does;
  * a hand-added class (no kind) copies as is;
  * the page's department/level filter narrows what's copied;
  * confirming saves drafts through the import's confirm route, audited as
    timetable.copy.

Run with:  python tests/test_timetable_copy.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import timetable_import as ti  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Lecturer, Course, Semester, Timetable,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class TimetableCopyTestCase(unittest.TestCase):

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
        self.acc = Department(name='Accounting', faculty_id=faculty.id)
        self.last_year = Semester(name='2024/2025 Second Semester', start_date=date(2025, 1, 1),
                                  end_date=date(2025, 6, 1))
        self.first = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                              end_date=date(2025, 12, 20))
        self.now = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2026, 6, 1), is_active=True)
        db.session.add_all([self.mct, self.acc, self.last_year, self.first, self.now])
        db.session.flush()
        self.admin = User(username='tunde', password_hash='x', role='admin',
                          is_active=True, requires_password_change=False)
        lect_user = User(username='STF/1', password_hash='x', role='lecturer')
        db.session.add_all([self.admin, lect_user])
        db.session.flush()
        self.lect = Lecturer(full_name='Dr A. Example', staff_id='STF/1',
                             department_id=self.mct.id, user_id=lect_user.id)
        db.session.add(self.lect)
        db.session.flush()

        # Last year's courses and classes...
        old401 = self.course('MCT401', self.mct, self.last_year)
        old201 = self.course('ACC201', self.acc, self.last_year)
        old405 = self.course('MCT405', self.mct, self.last_year)      # dropped this year
        self.slot(old401, self.last_year, 0, 8, 10, 'LR 1', kind='L')
        self.slot(old401, self.last_year, 2, 14, 15, 'LR 1', kind=None)   # added by hand
        self.slot(old201, self.last_year, 1, 10, 12, 'LR 2', kind='L')
        self.slot(old405, self.last_year, 3, 8, 10, 'LR 3', kind='L')
        self.slot(old401, self.last_year, 4, 8, 10, 'DRAFT ROOM', kind='L', published=False)
        # ...and this year's (no MCT405).
        self.mct401 = self.course('MCT401', self.mct, self.now)
        self.acc201 = self.course('ACC201', self.acc, self.now)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def course(self, code, dept, semester):
        c = Course(course_title=f'Course {code}', course_code=code, lecturer_id=self.lect.id,
                   department_id=dept.id, semester_id=semester.id)
        db.session.add(c)
        db.session.flush()
        return c

    def slot(self, course, semester, day, start, end, room, kind, published=True):
        db.session.add(Timetable(course_id=course.id, semester_id=semester.id, day_of_week=day,
                                 start_time=time(start), end_time=time(end), room=room, kind=kind,
                                 is_published=published, created_by=self.admin.id))
        db.session.flush()

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    # ---- planning ---------------------------------------------------------------

    def test_default_source_is_same_semester_last_year(self):
        semesters = Semester.query.all()
        self.assertEqual(ti.default_copy_source(self.now, semesters), self.last_year)
        self.assertIsNone(ti.default_copy_source(self.first, semesters))   # no 2024/2025 First

    def test_copies_published_classes_and_skips_dropped_courses(self):
        plan = ti.plan_copy(self.last_year, self.now)
        self.assertTrue(plan.ok, [s.errors for sh in plan.sheets for s in sh.slots])
        self.assertEqual(plan.copied_from, '2024/2025 Second Semester')
        self.assertEqual([sh.title for sh in plan.sheets],
                         ['Accounting · 200 level', 'Mechatronics · 400 level'])
        rooms = sorted(s.room for s in plan.unique_slots)
        self.assertEqual(rooms, ['LR 1', 'LR 1', 'LR 2'])               # no draft, no MCT405
        self.assertTrue(all(s.course.semester_id == self.now.id for s in plan.unique_slots))
        self.assertIn('MCT405', plan.sheets[1].notes[0])
        self.assertIn(None, {s.kind for s in plan.unique_slots})       # hand-added copied as is

    def test_a_clash_still_blocks(self):
        other = self.course('MCT403', self.mct, self.now)
        self.slot(other, self.now, 0, 9, 10, 'LR 1', kind='L')          # LR 1 on Monday 09:00
        db.session.commit()
        plan = ti.plan_copy(self.last_year, self.now)
        self.assertFalse(plan.ok)

    def test_filter_narrows_the_copy(self):
        plan = ti.plan_copy(self.last_year, self.now, keep=lambda c: c.department_id == self.acc.id)
        self.assertEqual([s.code for s in plan.unique_slots], ['ACC201'])

    def test_nothing_to_copy(self):
        self.assertIsNone(ti.plan_copy(self.first, self.now))

    # ---- routes -------------------------------------------------------------------

    def test_preview_then_confirm_saves_drafts(self):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post('/admin/timetable/copy', data={
                'source_id': self.last_year.id, 'semester_id': self.now.id})
            kwargs = render.call_args.kwargs
        self.assertTrue(kwargs['plan'].ok)
        self.assertEqual(Timetable.query.filter_by(semester_id=self.now.id).count(), 0)   # preview only

        self.client.post('/admin/timetable/import/confirm', data={
            'semester_id': self.now.id, 'plan': kwargs['plan_json']})
        saved = Timetable.query.filter_by(semester_id=self.now.id).all()
        self.assertEqual(len(saved), 3)
        self.assertTrue(all(not t.is_published for t in saved))
        self.assertEqual(AuditLog.query.filter_by(action='timetable.copy').count(), 1)

    def test_route_applies_the_page_filter(self):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post('/admin/timetable/copy', data={
                'source_id': self.last_year.id, 'semester_id': self.now.id,
                'dept': str(self.mct.id), 'level': '400'})
        self.assertEqual({s.code for s in render.call_args.kwargs['plan'].unique_slots}, {'MCT401'})

    def test_copying_a_semester_into_itself_is_refused(self):
        self.sign_in()
        resp = self.client.post('/admin/timetable/copy', data={
            'source_id': self.now.id, 'semester_id': self.now.id})
        self.assertEqual(resp.status_code, 302)


if __name__ == '__main__':
    unittest.main()
