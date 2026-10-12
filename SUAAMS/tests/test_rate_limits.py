"""Tests for rate-limit keys: who shares a limit with whom.

Every request reaches the app through Cloudflare and Render's proxy, and on
campus hundreds of students share one public address. If limits are keyed
on the wrong thing, one busy minute locks out everyone. These pin:

  * the visitor's address is read from Cloudflare's header, not the proxy,
  * many students logging in from ONE address don't block each other,
  * one account still locks after 5 wrong guesses a minute,
  * a terminal that proved its secret gets more than 30 taps a minute.

Run with:  python tests/test_rate_limits.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

from extensions import limiter, csrf, client_ip  # noqa: E402
from models import db  # noqa: E402
from api.auth import api_auth_bp  # noqa: E402
from api.student import api_student_bp  # noqa: E402

CAMPUS = {'CF-Connecting-IP': '41.58.10.10'}


class RateLimitTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=True,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(api_auth_bp)
        self.app.register_blueprint(api_student_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        limiter.reset()
        self.client = self.app.test_client()
        self.env = mock.patch.dict(os.environ, {
            'TERMINAL_ID': 'terminal-01', 'TERMINAL_SECRET': 's3cret',
            'BEACON_SIGNING_SECRET': 'beacon-secret',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        limiter.reset()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def login(self, username):
        return self.client.post('/api/v1/auth/login', headers=CAMPUS, json={
            'username': username, 'password': 'wrong', 'device_id': 'phone',
        })

    def test_address_comes_from_cloudflare_not_the_proxy(self):
        with self.app.test_request_context('/', headers={
            'CF-Connecting-IP': '41.58.1.2',
            'X-Forwarded-For': '6.6.6.6, 172.70.1.1',
        }, environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            self.assertEqual(client_ip(), '41.58.1.2')

    def test_falls_back_to_last_forwarded_entry_then_remote_addr(self):
        with self.app.test_request_context('/', headers={'X-Forwarded-For': '6.6.6.6, 41.58.1.2'}):
            self.assertEqual(client_ip(), '41.58.1.2')
        with self.app.test_request_context('/', environ_base={'REMOTE_ADDR': '10.0.0.1'}):
            self.assertEqual(client_ip(), '10.0.0.1')

    def test_a_lecture_hall_on_one_address_can_all_log_in(self):
        # 20 different students, same campus address, same minute. Under the
        # old per-address 5/minute, students 6-20 got 429.
        statuses = [self.login(f'MCT/20/{n:04d}').status_code for n in range(20)]
        self.assertNotIn(429, statuses)

    def test_one_account_still_locks_after_five_guesses(self):
        statuses = [self.login('MCT/20/0001').status_code for _ in range(6)]
        self.assertNotIn(429, statuses[:5])
        self.assertEqual(statuses[5], 429)

    def test_a_terminal_can_take_more_than_thirty_taps_a_minute(self):
        headers = {'X-Terminal-Id': 'terminal-01', 'X-Terminal-Secret': 's3cret', **CAMPUS}
        statuses = [
            self.client.post('/api/v1/student/checkin', headers=headers,
                             json={'beacon_token': 'not-a-real-token'}).status_code
            for _ in range(60)
        ]
        # 401 (bad token) is fine -- the point is no 429 at 60 taps.
        self.assertNotIn(429, statuses)

    def test_a_made_up_terminal_id_gets_no_allowance_of_its_own(self):
        # Wrong secret: falls back to the address, so inventing a new
        # X-Terminal-Id per request doesn't reset the counter.
        statuses = [
            self.client.post('/api/v1/student/checkin', headers={
                'X-Terminal-Id': f'fake-{n}', 'X-Terminal-Secret': 'guess', **CAMPUS,
            }, json={'beacon_token': 'x'}).status_code
            for n in range(121)
        ]
        self.assertEqual(statuses[-1], 429)


if __name__ == '__main__':
    unittest.main()
