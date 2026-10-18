"""Tests for the admin Organization page (blueprints/admin.py), 2026-10-18:

  * a faculty or department deletes only when EMPTY -- no students,
    lecturers, courses or HODs under it. The cascade used to remove all of
    them, with their attendance, behind nothing but a typed name;
  * an empty faculty still deletes, taking its empty departments;
  * the page shows "In use, can't delete" instead of a delete button for
    one that isn't empty, and programme length saves with a button, not on
    change (an arrow key on the dropdown used to save a wrong length).

Run with:  python tests/test_organization_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, Department, Faculty, HOD, Lecturer, User  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class OrganizationPageTestCase(unittest.TestCase):

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

        self.eng = Faculty(name='Engineering')
        self.arts = Faculty(name='Arts')
        db.session.add_all([self.eng, self.arts])
        db.session.flush()
        self.mct = Department(name='Mechatronics', faculty_id=self.eng.id, programme_years=5)
        self.hist = Department(name='History', faculty_id=self.arts.id)    # empty
        db.session.add_all([self.mct, self.hist])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

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

    # ---- deletes ---------------------------------------------------------------------

    def test_department_with_only_an_hod_is_not_deleted(self):
        # An HOD alone still counts: the cascade would delete their account.
        db.session.add(HOD(full_name='Prof H', staff_id='HOD/1', department_id=self.mct.id,
                           user_id=self.user('HOD/1', 'hod').id))
        db.session.commit()
        resp = self.client.post(f'/admin/departments/{self.mct.id}/delete', follow_redirects=True)
        self.assertIsNotNone(db.session.get(Department, self.mct.id))
        self.assertIn('still has 1 HOD', resp.get_data(as_text=True))

    def test_faculty_with_a_lecturer_under_it_is_not_deleted(self):
        db.session.add(Lecturer(full_name='Dr L', staff_id='STF/1', department_id=self.mct.id,
                                user_id=self.user('STF/1', 'lecturer').id))
        db.session.commit()
        self.client.post(f'/admin/faculties/{self.eng.id}/delete')
        self.assertIsNotNone(db.session.get(Faculty, self.eng.id))
        self.assertEqual(Lecturer.query.count(), 1)

    def test_empty_faculty_deletes_with_its_empty_departments(self):
        self.client.post(f'/admin/faculties/{self.arts.id}/delete')
        self.assertIsNone(db.session.get(Faculty, self.arts.id))
        self.assertIsNone(db.session.get(Department, self.hist.id))

    # ---- the page -----------------------------------------------------------------------

    def test_page_offers_delete_only_for_empty_ones(self):
        db.session.add(Lecturer(full_name='Dr L', staff_id='STF/1', department_id=self.mct.id,
                                user_id=self.user('STF/1', 'lecturer').id))
        db.session.commit()
        html = self.client.get('/admin/organization').get_data(as_text=True)
        self.assertIn('aria-label="Delete department History"', html)
        self.assertNotIn('aria-label="Delete department Mechatronics"', html)
        self.assertNotIn('aria-label="Delete faculty Engineering"', html)
        self.assertIn("In use, can't delete", html)
        self.assertIn('2 faculties', html)                      # not "2 facultys"
        # Programme length: a Save button, and no save-on-change script.
        self.assertNotIn("select.form.submit()", html)

    def test_programme_length_still_saves(self):
        self.client.post('/admin/organization', data={
            'action': 'set_programme_years', 'department_id': self.hist.id, 'programme_years': 4})
        self.assertEqual(db.session.get(Department, self.hist.id).programme_years, 4)


if __name__ == '__main__':
    unittest.main()
