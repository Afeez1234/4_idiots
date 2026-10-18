"""Tests for the web sign-in and first-login password pages
(blueprints/auth.py, templates/auth/), 2026-10-18:

  * a failed sign-in keeps the typed username -- and never echoes the
    password back into the page,
  * a switched-off account is told what to do,
  * the sixth attempt in a minute renders the sign-in page with a message
    (still a 429), not Flask's bare "Too Many Requests" page,
  * the same for the password-change limit,
  * the show-password buttons are reachable by keyboard.

Run with:  python tests/test_login_page.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import db, User  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRET = 'not-the-password-123'


class LoginPageTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__, template_folder=os.path.join(ROOT, 'templates'),
                         static_folder=os.path.join(ROOT, 'static'))
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False,
            # The limits are what's under test here.
            RATELIMIT_ENABLED=True, RATELIMIT_STORAGE_URI='memory://',
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        limiter.reset()
        csrf.init_app(self.app)
        for bp in (auth_bp, admin_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        limiter.reset()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def user(self, username, active=True, fresh=False):
        u = User(username=username, role='student', is_active=active, requires_password_change=fresh,
                 password_hash=bcrypt.hashpw(b'right-password', bcrypt.gensalt(4)).decode())
        db.session.add(u)
        db.session.commit()
        return u

    def sign_in(self, username, password=SECRET):
        return self.client.post('/login', data={'username': username, 'password': password})

    # ---- failed sign-in ----------------------------------------------------------

    def test_failed_sign_in_keeps_the_username_but_never_the_password(self):
        self.user('CPE/20/1123')
        for username in ('CPE/20/1123', 'NO/SUCH/USER'):        # wrong password, unknown user
            html = self.sign_in(username).get_data(as_text=True)
            self.assertIn(f'value="{username}"', html)
            self.assertIn('Invalid username or password', html)
            self.assertNotIn(SECRET, html)

    def test_typed_username_is_escaped(self):
        html = self.sign_in('"><script>x</script>').get_data(as_text=True)
        self.assertNotIn('<script>x</script>', html)

    def test_switched_off_account_is_told_what_to_do(self):
        self.user('CPE/20/2000', active=False)
        html = self.sign_in('CPE/20/2000', 'right-password').get_data(as_text=True)
        self.assertIn('Ask the admin office', html)
        self.assertIn('value="CPE/20/2000"', html)

    # ---- the rate limits, as pages --------------------------------------------------

    def test_sixth_attempt_shows_the_sign_in_page_with_a_message(self):
        for _ in range(5):
            self.assertEqual(self.sign_in('CPE/20/3000').status_code, 200)
        resp = self.sign_in('CPE/20/3000')
        html = resp.get_data(as_text=True)
        self.assertEqual(resp.status_code, 429)
        self.assertIn('Too many sign-in attempts', html)
        self.assertIn('id="username"', html)                    # the form, not a bare error page
        self.assertIn('value="CPE/20/3000"', html)
        self.assertNotIn(SECRET, html)

    def test_password_change_limit_shows_the_page_with_a_message(self):
        u = self.user('CPE/20/4000', fresh=True)
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = u.id, u.username, 'student'
        for _ in range(5):
            self.client.post('/change-password', data={'new_password': 'a', 'confirm_password': 'b'})
        resp = self.client.post('/change-password', data={'new_password': 'a', 'confirm_password': 'b'})
        self.assertEqual(resp.status_code, 429)
        html = resp.get_data(as_text=True)
        self.assertIn('Too many attempts', html)
        self.assertIn('id="new_password"', html)

    # ---- HEAD requests ------------------------------------------------------------------
    # Flask runs the GET view for HEAD with request.method == 'HEAD'. The
    # views checked `== 'GET'` then `== 'POST'`, matched neither, returned
    # None -- a 500 in Render's log for every uptime-monitor / prefetch HEAD.

    def test_head_requests_get_a_200_not_a_500(self):
        self.assertEqual(self.client.head('/login').status_code, 200)
        u = self.user('CPE/20/6000', fresh=True)
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = u.id, u.username, 'student'
        self.assertEqual(self.client.head('/change-password').status_code, 200)

    def test_head_on_terminals_isnt_treated_as_a_form_post(self):
        admin = User(username='tunde', role='admin', is_active=True, requires_password_change=False,
                     password_hash='x')
        db.session.add(admin)
        db.session.commit()
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = admin.id, 'tunde', 'admin'
        self.assertEqual(self.client.head('/admin/terminals').status_code, 200)
        # It used to fall into the POST branch and leave an error flash.
        with self.client.session_transaction() as s:
            self.assertFalse(s.get('_flashes'))

    # ---- the pages ---------------------------------------------------------------------

    def test_show_password_buttons_are_reachable_by_keyboard(self):
        html = self.client.get('/login').get_data(as_text=True)
        self.assertIn('id="toggle-password"', html)
        self.assertNotIn('tabindex="-1"', html)
        u = self.user('CPE/20/5000', fresh=True)
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = u.id, u.username, 'student'
        html = self.client.get('/change-password').get_data(as_text=True)
        self.assertIn('Set a new password', html)
        self.assertNotIn('tabindex="-1"', html)


if __name__ == '__main__':
    unittest.main()
