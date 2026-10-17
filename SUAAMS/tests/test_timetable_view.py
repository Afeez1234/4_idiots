"""Tests for the admin timetable page's department/level view
(_timetable_view / _timetable_coverage in blueprints/admin.py and
utils.course_level).

Pins:

  * a course's level is read from its code (first digit), "other" if none;
  * default view = coverage: one row per department+level with courses this
    semester, saying whether it has classes, drafts, or nothing yet;
  * a lone department or level filter narrows the coverage rows;
  * department AND level -> the grid, holding only that class's classes, and
    its course list holds only that class's courses;
  * drafts and Publish are never filtered away;
  * a hand edit posted from a filtered grid comes back to the same filters;
  * "happening now" is scoped to the class being viewed;
  * both views render for real (the whole template, not a mock).

Run with:  python tests/test_timetable_view.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, datetime, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Lecturer, Course, Semester, Timetable,
)
from utils import course_level  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static')


class CourseLevelTestCase(unittest.TestCase):

    def test_levels_from_codes(self):
        self.assertEqual(course_level('MCT401'), '400')
        self.assertEqual(course_level('GST 212'), '200')
        self.assertEqual(course_level('XYZ-SAM101'), '100')
        self.assertIsNone(course_level('PROJ'))
        self.assertIsNone(course_level('MCT901'))      # not a level the school runs
        self.assertIsNone(course_level(None))


class TimetableViewTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=TEMPLATES, static_folder=STATIC)
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
        self.sem = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2026, 6, 1), is_active=True)
        self.old_sem = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                                end_date=date(2025, 12, 20), is_active=False)
        db.session.add_all([self.mct, self.acc, self.sem, self.old_sem])
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

        self.mct401 = self.course('MCT401', self.mct)
        self.mct403 = self.course('MCT403', self.mct)
        self.mct301 = self.course('MCT301', self.mct)
        self.acc201 = self.course('ACC201', self.acc)
        self.gst212 = self.course('GST212', None)
        self.proj = self.course('PROJ', self.mct)
        self.slot(self.mct401, 0, 8, 10, published=True)
        self.slot(self.mct301, 1, 8, 10, published=False)
        self.slot(self.acc201, 2, 8, 10, published=True, semester=self.old_sem)   # last semester
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def course(self, code, dept):
        c = Course(course_title=f'Course {code}', course_code=code, lecturer_id=self.lect.id,
                   department_id=dept.id if dept else None, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        return c

    def slot(self, course, day, start, end, published, semester=None):
        t = Timetable(course_id=course.id, semester_id=(semester or self.sem).id, day_of_week=day,
                      start_time=time(start), end_time=time(end), room='LR 1',
                      is_published=published, created_by=self.admin.id)
        db.session.add(t)
        db.session.flush()
        return t

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def page(self, **args):
        """The template context the page renders with (rendering mocked)."""
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.get('/admin/timetable', query_string=args)
        return render.call_args.kwargs

    def rows(self, ctx):
        return {(r['dept_name'], r['level']): r for r in ctx['coverage']}

    # ---- coverage -------------------------------------------------------------

    def test_default_is_coverage_of_the_active_semester(self):
        ctx = self.page()
        self.assertFalse(ctx['view']['is_grid'])
        rows = self.rows(ctx)
        self.assertEqual(set(rows), {('Accounting', '200'), ('Mechatronics', '300'),
                                     ('Mechatronics', '400'), ('Mechatronics', 'other'),
                                     ('General (no department)', '200')})
        self.assertEqual((rows['Mechatronics', '400']['scheduled'], rows['Mechatronics', '400']['courses']), (1, 2))
        self.assertEqual(rows['Mechatronics', '400']['status'], 'published')
        self.assertEqual(rows['Mechatronics', '300']['status'], 'draft')
        # ACC201's classes are last semester's: this semester it has none.
        self.assertEqual(rows['Accounting', '200']['status'], 'none')
        # General courses come last.
        self.assertEqual(ctx['coverage'][-1]['dept'], 'general')

    def test_a_lone_filter_narrows_the_coverage(self):
        self.assertEqual({r['level'] for r in self.page(dept=self.mct.id)['coverage']}, {'300', '400', 'other'})
        self.assertEqual({r['dept_name'] for r in self.page(level='200')['coverage']},
                         {'Accounting', 'General (no department)'})

    def test_drafts_are_never_filtered_away(self):
        ctx = self.page(dept=self.acc.id, level='200')       # MCT301's draft is elsewhere
        self.assertEqual(ctx['draft_count'], 1)
        self.assertEqual(len(ctx['draft_semesters']), 1)

    # ---- grid -------------------------------------------------------------------

    def test_department_and_level_show_that_class_only(self):
        ctx = self.page(dept=self.mct.id, level='400')
        self.assertTrue(ctx['view']['is_grid'])
        self.assertEqual([e.course_id for e in ctx['timetable_entries']], [self.mct401.id])
        self.assertEqual([c.course_code for c in ctx['courses']], ['MCT401', 'MCT403'])

    def test_general_courses_have_their_own_grid(self):
        ctx = self.page(dept='general', level='200')
        self.assertEqual([c.course_code for c in ctx['courses']], ['GST212'])

    def test_hand_edit_returns_to_the_same_filters(self):
        self.sign_in()
        entry = Timetable.query.filter_by(course_id=self.mct401.id).one()
        resp = self.client.post(f'/admin/timetable?semester={self.sem.id}&dept={self.mct.id}&level=400',
                                data={'action': 'delete', 'timetable_id': entry.id})
        self.assertIn(f'dept={self.mct.id}', resp.headers['Location'])
        self.assertIn('level=400', resp.headers['Location'])

    def test_happening_now_is_scoped_to_the_class(self):
        self.sign_in()
        monday_9am = datetime(2026, 3, 2, 9, 0)              # MCT401 is Mon 08:00-10:00
        with mock.patch('utils.campus_now', return_value=monday_9am):
            mct = self.client.get('/admin/timetable/current',
                                  query_string={'dept': self.mct.id, 'level': '400'}).get_json()
            acc = self.client.get('/admin/timetable/current',
                                  query_string={'dept': self.acc.id, 'level': '200'}).get_json()
        self.assertEqual(mct['status'], 'in_session')
        self.assertEqual(acc['status'], 'no_class_now')

    # ---- the real template ----------------------------------------------------

    def test_both_views_render(self):
        self.sign_in()
        coverage = self.client.get('/admin/timetable')
        self.assertEqual(coverage.status_code, 200, coverage.data[:500])
        self.assertIn(b'Timetable coverage', coverage.data)
        self.assertIn(b'Draft waiting', coverage.data)
        self.assertNotIn(b'slot-modal', coverage.data)

        grid = self.client.get('/admin/timetable', query_string={'dept': self.mct.id, 'level': '400'})
        self.assertEqual(grid.status_code, 200, grid.data[:500])
        self.assertIn(b'Mechatronics', grid.data)
        self.assertIn(b'slot-modal', grid.data)
        self.assertNotIn(b'Timetable coverage', grid.data)

    # ---- Add Slot's semester (2026-10-17) -----------------------------------------
    # The form's semester used to be a dropdown defaulting to the ACTIVE
    # semester. Adding a class while preparing next semester's grid saved it
    # into the current one -- published and announced -- with no warning,
    # since the default never differed from the active semester.

    def test_add_slot_goes_into_the_semester_being_viewed(self):
        nxt = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                       end_date=date(2027, 1, 31), is_active=False)
        db.session.add(nxt)
        db.session.flush()
        course = Course(course_title='Robotics', course_code='MCT405', lecturer_id=self.lect.id,
                        department_id=self.mct.id, semester_id=nxt.id)
        db.session.add(course)
        db.session.commit()
        self.sign_in()

        html = self.client.get('/admin/timetable', query_string={
            'semester': nxt.id, 'dept': self.mct.id, 'level': '400'}).get_data(as_text=True)
        self.assertIn(f'name="semester_id" value="{nxt.id}"', html)
        # Not the active semester, so the confirmation is asked up front.
        self.assertIn('name="confirm_other_semester" id="create-confirm-other-semester" required', html)

        # What the browser posts from that form.
        self.client.post(f'/admin/timetable?semester={nxt.id}&dept={self.mct.id}&level=400', data={
            'action': 'create', 'course_id': course.id, 'semester_id': nxt.id,
            'confirm_other_semester': 'on', 'day_of_week': 3,
            'start_time': '10:00', 'end_time': '12:00', 'room': 'LR 9'})
        added = Timetable.query.filter_by(course_id=course.id).one()
        self.assertEqual(added.semester_id, nxt.id)

    def test_active_semester_grid_asks_no_confirmation(self):
        self.sign_in()
        html = self.client.get('/admin/timetable', query_string={
            'dept': self.mct.id, 'level': '400'}).get_data(as_text=True)
        self.assertIn(f'name="semester_id" value="{self.sem.id}"', html)
        self.assertNotIn('create-confirm-other-semester', html)

    def test_draft_chip_says_draft_before_the_code(self):
        # A truncating line: "Draft" first, or a narrow chip cuts it off.
        self.sign_in()
        html = self.client.get('/admin/timetable', query_string={
            'dept': self.mct.id, 'level': '300'}).get_data(as_text=True)
        self.assertRegex(html, r'Draft &middot;</span>\s*MCT301')
        self.assertIn('Drafts waiting', html)


if __name__ == '__main__':
    unittest.main()
