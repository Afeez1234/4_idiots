"""Tests for the yearly promotion (promotion.py and /admin/students/promotion*).

Pins:

  * active students move up one level; final-year and spill-over students
    don't, and are listed as due to graduate; non-active students don't move;
  * repeaters from the CSV stay; an unknown matric number blocks the run;
  * a department with students but no programme length blocks the run;
  * the academic year comes from the active semester, and the same year
    can't be promoted twice;
  * undo moves back only students still at the level the run gave them;
  * the confirm re-plans from the database (a student suspended after the
    preview isn't promoted), and is audited;
  * the due-to-graduate CSV feeds straight into Change Status (CSV).

Run with:  python tests/test_promotion.py
(also collected by pytest if it is installed)
"""

import io
import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import promotion  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Semester, PromotionRun,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class PromotionTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates'))
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
        self.mct = Department(name='Mechatronics', faculty_id=faculty.id, programme_years=5)
        self.acc = Department(name='Accounting', faculty_id=faculty.id, programme_years=4)
        self.sem = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 30), is_active=True)
        db.session.add_all([self.mct, self.acc, self.sem])
        db.session.flush()
        self.admin = User(username='tunde', password_hash='x', role='admin',
                          is_active=True, requires_password_change=False)
        db.session.add(self.admin)
        db.session.flush()
        self.s = {
            'mct300': self.student('MCT/24/0001', '300', self.mct),
            'mct500': self.student('MCT/22/0001', '500', self.mct),     # final year (5-year)
            'acc400': self.student('ACC/23/0001', '400', self.acc),     # final year (4-year)
            'acc500': self.student('ACC/22/0001', '500', self.acc),     # spill-over
            'acc100': self.student('ACC/26/0001', '100', self.acc),
            'repeat': self.student('MCT/24/0002', '300', self.mct),
            'gone': self.student('MCT/24/0003', '300', self.mct, status='graduated'),
        }
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def student(self, matric, level, dept, status='active'):
        u = User(username=matric, password_hash='x', role='student')
        db.session.add(u)
        db.session.flush()
        st = Student(full_name=matric, matric_number=matric, level=level, department_id=dept.id,
                     user_id=u.id, status=status)
        db.session.add(st)
        db.session.flush()
        return st

    def level(self, key):
        return db.session.get(Student, self.s[key].id).level

    # ---- planning ----------------------------------------------------------------

    def test_plan(self):
        plan = promotion.plan_promotion(self.sem, ['mct/24/0002'])
        self.assertTrue(plan.ok)
        self.assertEqual(plan.year, '2026/2027')
        self.assertEqual(plan.moving, 2)                                 # mct300, acc100
        self.assertEqual({m for m, *_ in plan.due}, {'MCT/22/0001', 'ACC/23/0001', 'ACC/22/0001'})
        self.assertEqual([m for m, *_ in plan.excluded], ['MCT/24/0002'])

    def test_unknown_repeater_blocks(self):
        plan = promotion.plan_promotion(self.sem, ['MCT/99/9999'])
        self.assertFalse(plan.ok)
        self.assertEqual(plan.unknown_exclusions, ['mct/99/9999'])

    def test_missing_programme_length_blocks(self):
        self.acc.programme_years = None
        db.session.commit()
        plan = promotion.plan_promotion(self.sem)
        self.assertEqual(plan.missing_years, ['Accounting'])
        with self.assertRaises(promotion.PromotionError):
            promotion.apply_promotion(plan, self.admin.id)

    def test_semester_without_a_year_is_refused(self):
        self.sem.name = 'First Semester'
        with self.assertRaises(promotion.PromotionError):
            promotion.plan_promotion(self.sem)

    # ---- applying and undoing -----------------------------------------------------

    def test_apply_once_per_year_then_undo(self):
        plan = promotion.plan_promotion(self.sem, ['MCT/24/0002'])
        self.assertEqual(promotion.apply_promotion(plan, self.admin.id), 2)
        db.session.commit()
        self.assertEqual((self.level('mct300'), self.level('acc100')), ('400', '200'))
        self.assertEqual((self.level('mct500'), self.level('repeat'), self.level('gone')), ('500', '300', '300'))

        with self.assertRaises(promotion.PromotionError):               # same year again
            promotion.apply_promotion(promotion.plan_promotion(self.sem), self.admin.id)

        # A level fixed by hand since the run is left alone by undo.
        db.session.get(Student, self.s['acc100'].id).level = '300'
        db.session.commit()
        self.assertEqual(promotion.undo_promotion(promotion.current_run('2026/2027')), 1)
        db.session.commit()
        self.assertEqual((self.level('mct300'), self.level('acc100')), ('300', '300'))
        self.assertEqual(PromotionRun.query.count(), 0)                 # can run again

    def test_due_to_graduate_list(self):
        self.assertEqual({m for m, *_ in promotion.due_to_graduate()},
                         {'MCT/22/0001', 'ACC/23/0001', 'ACC/22/0001'})

    # ---- routes -------------------------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def test_preview_then_confirm_replans(self):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post('/admin/students/promotion/preview', content_type='multipart/form-data',
                             data={'file': (io.BytesIO(b'MCT/24/0002\n'), 'repeaters.csv')})
            kwargs = render.call_args.kwargs
        self.assertEqual(kwargs['plan'].moving, 2)
        self.assertEqual(self.level('mct300'), '300')                     # preview only

        # Suspended between the preview and the confirm: must not move.
        db.session.get(Student, self.s['acc100'].id).status = 'suspended'
        db.session.commit()
        self.client.post('/admin/students/promotion/confirm',
                         data={'year': '2026/2027', 'excluded': kwargs['excluded_json']})
        self.assertEqual((self.level('mct300'), self.level('acc100'), self.level('repeat')), ('400', '100', '300'))
        [entry] = AuditLog.query.filter_by(action='student.promote').all()
        self.assertIn('Promoted 1 students', entry.summary)

    def test_due_csv_has_the_status_upload_column(self):
        self.sign_in()
        body = self.client.get('/admin/students/promotion/due-to-graduate.csv').get_data(as_text=True)
        self.assertTrue(body.startswith('matric_number,'))
        self.assertIn('ACC/22/0001', body)

    def test_page_renders_for_real(self):
        self.sign_in()
        self.assertEqual(self.client.get('/admin/students/promotion').status_code, 200)


    def test_organization_counts(self):
        # Lives here because this fixture already has two departments with
        # students. The Organization page counts with GROUP BY queries
        # (_organization_counts) rather than loading every student.
        from blueprints.admin import _organization_counts
        dept_counts, faculty_counts = _organization_counts(Department.query.all())
        self.assertEqual(dept_counts[self.mct.id]['students'], 4)
        self.assertEqual(dept_counts[self.acc.id]['students'], 3)
        self.assertEqual(faculty_counts[self.mct.faculty_id], {'departments': 2, 'students': 7,
                                                               'lecturers': 0, 'courses': 0})
        self.sign_in()
        page = self.client.get('/admin/organization').get_data(as_text=True)
        self.assertIn('7 students', page)


if __name__ == '__main__':
    unittest.main()
