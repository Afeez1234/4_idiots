"""Tests for resetting an admin's password from the command line
(create_admin.py --reset).

Pins:

  * a reset sets a random one-time password (returned, never logged),
    forces a change at the next login and revokes the signed-in session;
  * two resets give different passwords, and only the latest works;
  * it refuses (nothing changed) an unknown name, a student or lecturer
    (reset from the dashboard instead) and a disabled admin.

Run with:  python tests/test_create_admin.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# create_admin.py imports app.py, which refuses to start without these. The
# test never touches that app's database: reset_password() runs in the
# test's own app context below. create_admin is imported in setUp, not up
# here, as in test_audit.py: importing app.py while pytest collects breaks
# test_app_version.py.
for _name in ('SECRET_KEY', 'JWT_SECRET_KEY', 'DB_HOST', 'DB_USER',
              'DB_PASSWORD', 'DB_NAME'):
    os.environ.setdefault(_name, 'test')

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402

from models import db, AuditLog, User  # noqa: E402


def _hash(password):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


class ResetAdminPasswordTest(unittest.TestCase):

    def setUp(self):
        import create_admin
        self.reset_password = create_admin.reset_password
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', TESTING=True)
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.admin = User(username='Temilade', password_hash=_hash('forgotten'), role='admin',
                          is_active=True, requires_password_change=False,
                          current_refresh_jti='old-session')
        self.lecturer = User(username='LEC/001', password_hash=_hash('kept'), role='lecturer',
                             is_active=True, requires_password_change=False)
        self.gone = User(username='old-admin', password_hash=_hash('kept'), role='admin',
                         is_active=False, requires_password_change=False)
        db.session.add_all([self.admin, self.lecturer, self.gone])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    @staticmethod
    def password_is(user, password):
        return bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8'))

    def test_reset_gives_a_one_time_password(self):
        temp = self.reset_password('Temilade')
        self.assertTrue(self.password_is(self.admin, temp))
        self.assertFalse(self.password_is(self.admin, 'forgotten'))
        self.assertTrue(self.admin.requires_password_change)   # must choose their own
        self.assertIsNone(self.admin.current_refresh_jti)      # old session revoked
        entry = AuditLog.query.filter_by(action='admin.password_reset').one()
        self.assertTrue(entry.actor_label.startswith('cli:'))
        self.assertNotIn(temp, entry.summary + str(entry.details))

    def test_two_resets_differ_and_only_the_latest_works(self):
        first = self.reset_password('Temilade')
        second = self.reset_password('Temilade')
        self.assertNotEqual(first, second)
        self.assertTrue(self.password_is(self.admin, second))
        self.assertFalse(self.password_is(self.admin, first))

    def test_refuses_what_it_should_not_reset(self):
        for name, user in (('nobody', None), ('LEC/001', self.lecturer), ('old-admin', self.gone)):
            with self.subTest(name=name):
                with self.assertRaises(SystemExit):
                    self.reset_password(name)
                if user is not None:
                    self.assertTrue(self.password_is(user, 'kept'))
                    self.assertFalse(user.requires_password_change)
        self.assertEqual(AuditLog.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
