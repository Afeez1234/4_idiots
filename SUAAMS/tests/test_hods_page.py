"""Tests for the admin HODs page (blueprints/admin.py::hods_page):

  * one row per department, with its HOD or none -- the page used to list
    only HODs that exist, so a department without one didn't appear,
  * the assign forms offer only departments with no HOD,
  * Promote offers only active lecturers, and refuses one on leave or gone,
  * an HOD whose login is off reads "sign-in off" (with the lecturer status
    when that's why), not "Active".

Run with:  python tests/test_hods_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Department, Faculty, HOD, Lecturer, User  # noqa: E402
from people_status import set_lecturer_status  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class HodsPageTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                         static_folder=os.path.join(ROOT, 'static'))
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
        self.cpe = Department(name='Computer', faculty_id=faculty.id)
        self.aer = Department(name='Aerospace', faculty_id=faculty.id)
        db.session.add_all([self.mct, self.cpe, self.aer])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.ada = self.lecturer('Dr Ada', 'STF/1')
        self.bayo = self.lecturer('Dr Bayo', 'STF/2')
        self.chi = self.lecturer('Dr Chi', 'STF/3')
        # Dr Ada is a promoted HOD of Mechatronics.
        self.ada_hod = self.promote(self.ada, self.mct)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'], sess['username'], sess['role'] = self.admin.id, 'tunde', 'admin'

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

    def lecturer(self, name, staff_id):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.mct.id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def promote(self, lecturer, department):
        lecturer.user.role = 'hod'
        hod = HOD(full_name=lecturer.full_name, staff_id=lecturer.staff_id,
                  department_id=department.id, user_id=lecturer.user_id)
        db.session.add(hod)
        db.session.flush()
        return hod

    def context(self):
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            self.assertEqual(self.client.get('/admin/hods').status_code, 200)
        return render.call_args.kwargs

    # ---- one row per department ------------------------------------------------------

    def test_every_department_has_a_row_and_only_free_ones_are_offered(self):
        ctx = self.context()
        rows = {r['department'].name: r['hod'] for r in ctx['rows']}
        self.assertEqual(set(rows), {'Mechatronics', 'Computer', 'Aerospace'})
        self.assertEqual(rows['Mechatronics'].id, self.ada_hod.id)
        self.assertIsNone(rows['Computer'])
        self.assertEqual({d.name for d in ctx['free_departments']}, {'Computer', 'Aerospace'})
        self.assertEqual(ctx['hod_count'], 1)

    # ---- promote: active lecturers only -------------------------------------------------

    def test_promote_offers_only_active_lecturers_not_yet_hod(self):
        set_lecturer_status(self.chi, 'on_leave', 'Sabbatical')
        db.session.commit()
        offered = {l.staff_id for l in self.context()['promotable_lecturers']}
        self.assertEqual(offered, {'STF/2'})        # not Ada (HOD) or Chi (on leave)

    def test_promoting_an_inactive_lecturer_is_refused(self):
        set_lecturer_status(self.chi, 'left', 'Resigned')
        db.session.commit()
        self.client.post('/admin/hods', data={
            'action': 'promote_lecturer', 'lecturer_id': self.chi.id, 'department_id': self.cpe.id})
        self.assertIsNone(HOD.query.filter_by(department_id=self.cpe.id).first())

    # ---- the real page ------------------------------------------------------------------

    def test_page_shows_gaps_and_an_hod_whose_sign_in_is_off(self):
        # Ada goes on leave on the Lecturers page: the shared login goes off.
        set_lecturer_status(self.ada, 'on_leave', 'Sabbatical')
        db.session.commit()
        html = self.client.get('/admin/hods').get_data(as_text=True)
        self.assertIn('On leave · sign-in off', html)
        self.assertNotIn('>Active<', html)
        self.assertEqual(html.count('No HOD yet'), 2)               # Computer, Aerospace
        self.assertIn('1 of 3 departments have an HOD', html)
        # Mechatronics has an HOD, so neither assign form offers it.
        self.assertNotIn(f'<option value="{self.mct.id}">Mechatronics</option>', html.split('edit-modal')[0])
        self.assertIn(f'<option value="{self.cpe.id}">Computer</option>', html)


if __name__ == '__main__':
    unittest.main()
