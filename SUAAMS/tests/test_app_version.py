"""Tests for the minimum app build gate (app_version.py).

These pin:

  * with MIN_APP_BUILD unset (the default) nothing is gated, header or not,
  * once set, an app below it -- or sending no build at all -- gets 426
    "UPDATE REQUIRED", including on login, so a signed-out phone sees it too,
  * the readers' routes are never gated: they send no app build,
  * a malformed MIN_APP_BUILD turns the gate off rather than locking
    every phone out.

Run with:  python tests/test_app_version.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import app_version  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import db  # noqa: E402
from api.auth import api_auth_bp  # noqa: E402
from api.student import api_student_bp  # noqa: E402
from api.lecturer import api_lecturer_bp  # noqa: E402
from api.terminal import api_terminal_bp  # noqa: E402

LOGIN = {'username': 'nobody', 'password': 'pw', 'device_id': 'phone'}


class AppVersionTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        app_version.init_app(self.app)
        for bp in (api_auth_bp, api_student_bp, api_lecturer_bp, api_terminal_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def gate(self, value):
        return mock.patch.dict(os.environ, {'MIN_APP_BUILD': value})

    def login(self, build=None):
        headers = {} if build is None else {app_version.HEADER: str(build)}
        return self.client.post('/api/v1/auth/login', json=LOGIN, headers=headers)

    def assertUpdateRequired(self, resp, minimum):
        self.assertEqual(resp.status_code, 426)
        self.assertEqual(resp.get_json(), {'error': 'UPDATE REQUIRED', 'min_build': minimum})

    def test_gate_off_by_default(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('MIN_APP_BUILD', None)
            self.assertNotEqual(self.login().status_code, 426)
            self.assertNotEqual(self.login(build=1).status_code, 426)

    def test_zero_and_empty_mean_off(self):
        for value in ('0', '', '  '):
            with self.gate(value):
                self.assertNotEqual(self.login().status_code, 426, value)

    def test_old_build_is_told_to_update(self):
        with self.gate('5'):
            self.assertUpdateRequired(self.login(build=4), 5)

    def test_missing_or_garbled_header_is_told_to_update(self):
        # Every build from before the header existed sends none.
        with self.gate('5'):
            self.assertUpdateRequired(self.login(), 5)
            self.assertUpdateRequired(self.login(build='abc'), 5)

    def test_current_and_newer_builds_pass(self):
        with self.gate('5'):
            self.assertNotEqual(self.login(build=5).status_code, 426)
            self.assertNotEqual(self.login(build=6).status_code, 426)

    def test_student_and_lecturer_routes_are_gated(self):
        with self.gate('5'):
            self.assertUpdateRequired(self.client.get('/api/v1/student/dashboard'), 5)
            self.assertUpdateRequired(self.client.get('/api/v1/lecturer/dashboard'), 5)
            # Before the JWT check: an old app with an expired token must see
            # "update", not "session expired" and a refresh loop.
            self.assertUpdateRequired(self.client.post('/api/v1/auth/refresh'), 5)

    def test_reader_routes_are_never_gated(self):
        with self.gate('5'):
            for method, path in (
                ('post', '/api/v1/student/checkin'),
                ('post', '/api/v1/student/checkin/backlog'),
                ('get', '/api/v1/terminal/status'),
            ):
                resp = getattr(self.client, method)(path, json={})
                self.assertNotEqual(resp.status_code, 426, path)

    def test_update_message_comes_from_the_server(self):
        with self.gate('5'), mock.patch.dict(os.environ, {
            'APP_UPDATE_MESSAGE': 'Download it at suaams.com.ng/app',
        }):
            resp = self.login(build=4)
        self.assertEqual(resp.status_code, 426)
        self.assertEqual(resp.get_json()['message'], 'Download it at suaams.com.ng/app')

    def test_malformed_minimum_turns_gate_off(self):
        with self.gate('v2'), self.assertLogs('app_version', 'ERROR'):
            self.assertNotEqual(self.login().status_code, 426)


if __name__ == '__main__':
    unittest.main()
