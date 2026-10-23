"""End-to-end tests for the check-in and login ROUTES (audit finding 6).

test_beacon.py and test_ble_beacon.py test the code formats. These test the
rules built on top of them, the ones the security model relies on, by
calling the real routes against a throwaway SQLite database:

NFC check-in
  * the code is bound to the session at mint time -- a tap counts for the
    student's own class even when another course's session started later
    (the old room-A/room-B bug),
  * a replayed code doesn't record twice,
  * forged, expired, wrong-terminal and ended-session taps are refused, and
    a session left open from an earlier day takes no check-ins at all,
  * the app's status poll sees the attendance once it lands.
Bluetooth check-in
  * a current code records attendance with method 'ble'; an old one doesn't,
  * with no BLE secret configured the route says it's off.
Offline taps
  * an expired code uploaded later is stored for review, NOT as attendance,
  * one read promptly is reviewed at the terminal's read time; one read
    long after it was made (kept and replayed) is rejected outright; an
    unusable read time falls back to review as before.
Login / device binding
  * first login binds the phone; a second phone is locked out,
  * a second account on the same phone is refused,
  * placeholder device IDs are refused,
  * login gives one answer for an unknown username and a wrong password,
    reveals a disabled account only to the right password, and the app's
    password change enforces 6 characters.
Races
  * two requests for one tap (NFC or Bluetooth) answer "already marked",
    not a 500.

Run with:  python tests/test_checkin.py
(also collected by pytest if it is installed)
"""

import calendar
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402

import ble_beacon  # noqa: E402
from beacon import mint_beacon  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, OfflineCheckinLog, DeviceToken,
)
from api.auth import api_auth_bp, install_account_check  # noqa: E402
from api.student import api_student_bp  # noqa: E402

SECRETS = {
    'BEACON_SIGNING_SECRET': 'test-beacon-secret',
    'BLE_BEACON_SECRET': 'test-ble-secret',
    'TERMINAL_ID': 'terminal-01',
    'TERMINAL_SECRET': 'terminal-secret',
}
TERMINAL = {'X-Terminal-Id': 'terminal-01', 'X-Terminal-Secret': 'terminal-secret'}


class CheckinTestCase(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, SECRETS)
        self.env.start()
        # Push needs Firebase; not what's under test.
        mock.patch('api.student.send_push_notification').start()
        mock.patch('api.auth.send_push_notification').start()

        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        # The production check that refuses tokens of switched-off accounts.
        install_account_check(JWTManager(self.app))
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(api_auth_bp)
        self.app.register_blueprint(api_student_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.flush()
        lect_user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(lect_user)
        db.session.flush()
        lecturer = Lecturer(full_name='Dr Ade', staff_id='S1', department_id=self.dept.id,
                            user_id=lect_user.id)
        db.session.add(lecturer)
        db.session.flush()
        self.course_a = Course(course_title='Room A class', course_code='MCT 401',
                               lecturer_id=lecturer.id, department_id=self.dept.id)
        self.course_b = Course(course_title='Room B class', course_code='EEE 401',
                               lecturer_id=lecturer.id, department_id=self.dept.id)
        db.session.add_all([self.course_a, self.course_b])
        db.session.flush()

        self.user, self.student = self.make_student('MCT/20/0001', 'pw')
        db.session.add(Enrollment(student_id=self.student.id, course_id=self.course_a.id))
        self.session_a = SessionModel(course_id=self.course_a.id, is_active=True)
        db.session.add(self.session_a)
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        self.env.stop()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def make_student(self, matric, password, device_id=None):
        user = User(username=matric, role='student', is_active=True, requires_password_change=False,
                    password_hash=bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode())
        db.session.add(user)
        db.session.flush()
        student = Student(full_name=matric, matric_number=matric, level='400',
                          department_id=self.dept.id, user_id=user.id, device_id=device_id)
        db.session.add(student)
        db.session.flush()
        return user, student

    def app_headers(self, user=None):
        token = create_access_token(identity=str((user or self.user).id),
                                    additional_claims={'role': 'student'})
        return {'Authorization': f'Bearer {token}'}

    def mint(self):
        resp = self.client.post('/api/v1/student/checkin/beacon', headers=self.app_headers())
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json()['beacon_token']

    def tap(self, token, headers=TERMINAL):
        return self.client.post('/api/v1/student/checkin', headers=headers,
                                json={'beacon_token': token})

    def attendance(self):
        return Attendance.query.filter_by(student_id=self.student.id).all()

    # ---- NFC ------------------------------------------------------------------

    def test_tap_counts_for_the_students_own_class_not_the_newest(self):
        token = self.mint()
        # Another course's session starts AFTER the code was minted. The old
        # lookup credited "the newest active session in any course".
        db.session.add(SessionModel(course_id=self.course_b.id, is_active=True))
        db.session.commit()
        self.assertEqual(self.tap(token).status_code, 200)
        [record] = self.attendance()
        self.assertEqual(record.session_id, self.session_a.id)
        self.assertEqual(record.method, 'nfc')

    def test_replayed_code_records_once(self):
        token = self.mint()
        self.tap(token)
        self.assertEqual(self.tap(token).status_code, 200)
        self.assertEqual(len(self.attendance()), 1)

    def test_forged_expired_and_wrong_terminal_are_refused(self):
        token = self.mint()
        forged = token[:-4] + ('AAAA' if not token.endswith('AAAA') else 'BBBB')
        expired = mint_beacon(self.student.id, self.session_a.id, ttl_seconds=-1)
        wrong_terminal = {'X-Terminal-Id': 'terminal-01', 'X-Terminal-Secret': 'guess'}
        self.assertEqual(self.tap(forged).status_code, 401)
        self.assertEqual(self.tap(expired).status_code, 401)
        self.assertEqual(self.tap(token, headers=wrong_terminal).status_code, 401)
        self.assertEqual(self.attendance(), [])

    def test_tap_after_the_session_ended_is_refused(self):
        token = self.mint()
        self.session_a.is_active = False
        db.session.commit()
        self.assertEqual(self.tap(token).status_code, 409)
        self.assertEqual(self.attendance(), [])

    def race(self):
        """Make the "already marked?" check miss an existing row, as when two
        requests for one tap run side by side; the insert then hits the
        unique constraint."""
        db.session.add(Attendance(student_id=self.student.id, session_id=self.session_a.id))
        db.session.commit()
        miss = mock.Mock(filter_by=lambda **kw: mock.Mock(first=lambda: None))
        return mock.patch.object(Attendance, 'query', miss)

    def test_simultaneous_nfc_taps_answer_already_marked_not_500(self):
        token = self.mint()
        with self.race():
            resp = self.tap(token)
        self.assertEqual((resp.status_code, resp.get_json()['message']), (200, 'Attendance already marked'))

    def test_simultaneous_ble_check_ins_answer_already_marked_not_500(self):
        with self.race():
            resp = self.ble(ble_beacon.current_slot())
        self.assertEqual((resp.status_code, resp.get_json()['message']), (200, 'Attendance already marked'))

    def test_session_left_open_from_an_earlier_day_takes_no_check_ins(self):
        # The lecturer never pressed End on Monday's class. On Wednesday no
        # code is minted for it, Bluetooth can't use it, and a token bound
        # to it (minted directly here) is refused at the terminal.
        from datetime import timedelta
        from campus_time import campus_today
        self.session_a.session_date = campus_today() - timedelta(days=2)
        db.session.commit()
        resp = self.client.post('/api/v1/student/checkin/beacon', headers=self.app_headers())
        self.assertEqual(resp.status_code, 404)
        payload = ble_beacon.build_payload(7, ble_beacon.current_slot())
        resp = self.client.post('/api/v1/student/checkin/ble', headers=self.app_headers(),
                                json={'payload': payload.hex()})
        self.assertEqual(resp.status_code, 404)
        stale = mint_beacon(self.student.id, self.session_a.id)
        self.assertEqual(self.tap(stale).status_code, 409)
        self.assertEqual(self.attendance(), [])

    def test_no_code_without_a_running_session(self):
        self.session_a.is_active = False
        db.session.commit()
        resp = self.client.post('/api/v1/student/checkin/beacon', headers=self.app_headers())
        self.assertEqual(resp.status_code, 404)

    def test_status_poll_sees_the_tap(self):
        poll = lambda: self.client.get('/api/v1/student/checkin/status',  # noqa: E731
                                       headers=self.app_headers()).get_json()
        token = self.mint()
        self.assertFalse(poll()['checked_in'])
        self.tap(token)
        self.assertTrue(poll()['checked_in'])

    # ---- Bluetooth -------------------------------------------------------------

    def ble(self, slot):
        payload = ble_beacon.build_payload(1, slot).hex()
        return self.client.post('/api/v1/student/checkin/ble', headers=self.app_headers(),
                                json={'payload': payload, 'rssi': -60})

    def test_current_ble_code_checks_in(self):
        self.assertEqual(self.ble(ble_beacon.current_slot()).status_code, 200)
        [record] = self.attendance()
        self.assertEqual(record.method, 'ble')

    def test_old_ble_code_is_refused(self):
        stale = ble_beacon.current_slot(time.time() - 60)   # a minute old
        self.assertEqual(self.ble(stale).status_code, 401)
        self.assertEqual(self.attendance(), [])

    def test_ble_off_without_its_secret(self):
        with mock.patch.dict(os.environ, {'BLE_BEACON_SECRET': ''}):
            resp = self.client.post('/api/v1/student/checkin/ble', headers=self.app_headers(),
                                    json={'payload': '00' * 14})
        self.assertEqual(resp.status_code, 503)

    # ---- Offline taps ------------------------------------------------------------

    def test_offline_tap_is_stored_for_review_not_as_attendance(self):
        expired = mint_beacon(self.student.id, self.session_a.id, ttl_seconds=-1)
        resp = self.client.post('/api/v1/student/checkin/backlog', headers=TERMINAL,
                                json={'records': [{'beacon_token': expired}]})
        self.assertEqual(resp.status_code, 200)
        [log] = OfflineCheckinLog.query.all()
        self.assertEqual(log.status, 'pending_verification')
        self.assertEqual(self.attendance(), [])

    def sync(self, read_at):
        """Upload one offline tap whose token was minted now, read at `read_at`."""
        token = mint_beacon(self.student.id, self.session_a.id)
        self.minted_at = int(time.time())
        record = {'beacon_token': token}
        if read_at is not None:
            record['read_at'] = read_at
        resp = self.client.post('/api/v1/student/checkin/backlog', headers=TERMINAL,
                                json={'records': [record]})
        self.assertEqual(resp.status_code, 200)
        return OfflineCheckinLog.query.one()

    def test_offline_tap_read_promptly_is_reviewed_at_its_read_time(self):
        read_at = int(time.time()) + 3
        log = self.sync(read_at)
        self.assertEqual(log.status, 'pending_verification')
        # Stored as naive UTC; it should be the read time, not the mint time.
        stored = calendar.timegm(log.captured_at.timetuple())
        self.assertEqual(stored, read_at)

    def test_offline_token_replayed_later_is_rejected_not_reviewed(self):
        # Minted now, read 85 minutes later: no unmodified app serves a token
        # that long, so "Accept all" must never see it.
        # +30 s of slack: the token is minted inside sync(), a moment after
        # this line, and a lag of 85 min minus a second reads "84 min".
        log = self.sync(int(time.time()) + 85 * 60 + 30)
        self.assertEqual(log.status, 'rejected')
        self.assertIn('85 min', log.reason)
        from utils import pending_offline_taps
        self.assertEqual(pending_offline_taps(self.session_a), [])

    def test_offline_read_time_unusable_falls_back_to_review(self):
        # Older firmware (no read_at), a clock that never synced (1970), a
        # clock running far behind the mint, and a non-number.
        for read_at in (None, 5, int(time.time()) - 3600, True, '1700000000'):
            OfflineCheckinLog.query.delete()
            db.session.commit()
            log = self.sync(read_at)
            self.assertEqual(log.status, 'pending_verification', read_at)

    # ---- Login and device binding --------------------------------------------------

    def login(self, username, device_id, password='pw'):
        return self.client.post('/api/v1/auth/login', json={
            'username': username, 'password': password, 'device_id': device_id})

    def test_login_says_whether_the_account_can_teach(self):
        # The app sends an HOD without a Lecturer profile to its web-portal
        # screen; every lecturer screen would fail for them. (2026-10-19)
        from models import HOD

        def account(username, role, lecturer=False, hod=False):
            user = User(username=username, role=role, is_active=True, requires_password_change=False,
                        password_hash=bcrypt.hashpw(b'pw', bcrypt.gensalt(4)).decode())
            db.session.add(user)
            db.session.flush()
            if lecturer:
                db.session.add(Lecturer(full_name=username, staff_id=username,
                                        department_id=self.dept.id, user_id=user.id))
            if hod:
                db.session.add(HOD(full_name=username, staff_id=username,
                                   department_id=self.dept.id, user_id=user.id))
            db.session.commit()

        account('HOD/NEW', 'hod', hod=True)                       # created as a new account
        account('HOD/PROMOTED', 'hod', lecturer=True, hod=True)   # a promoted lecturer
        flag = lambda name: self.login(name, 'phone-x').get_json()['user']['has_lecturer_profile']  # noqa: E731
        self.assertFalse(flag('HOD/NEW'))
        self.assertTrue(flag('HOD/PROMOTED'))
        self.assertFalse(flag('MCT/20/0001'))                     # a student

    def test_first_login_binds_and_another_phone_is_locked_out(self):
        self.assertEqual(self.login('MCT/20/0001', 'phone-1').status_code, 200)
        self.assertEqual(db.session.get(Student, self.student.id).device_id, 'phone-1')
        resp = self.login('MCT/20/0001', 'phone-2')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('SECURITY LOCK', resp.get_json()['error'])

    def test_switching_an_account_off_stops_its_token_at_once(self):
        # Not 30 minutes later when the access token would have expired.
        headers = self.app_headers()
        self.assertEqual(self.client.post('/api/v1/student/checkin/beacon', headers=headers).status_code, 200)
        self.user.is_active = False
        db.session.commit()
        resp = self.client.post('/api/v1/student/checkin/beacon', headers=headers)
        self.assertEqual(resp.status_code, 401)
        # The app signs out on errors containing "unauthorized" (auth_retry.dart).
        self.assertIn('unauthorized', resp.get_json()['error'].lower())

    def test_token_of_a_deleted_account_is_refused(self):
        headers = self.app_headers()
        db.session.delete(self.student)
        db.session.delete(self.user)
        db.session.commit()
        self.assertEqual(self.client.get('/api/v1/student/checkin/status', headers=headers).status_code, 401)

    def test_logout_stops_pushes_to_the_phone(self):
        refresh = self.login('MCT/20/0001', 'phone-1').get_json()['refresh_token']
        db.session.add(DeviceToken(user_id=self.user.id, fcm_token='fcm-1', platform='android'))
        db.session.commit()
        resp = self.client.post('/api/v1/auth/logout',
                                headers={'Authorization': f'Bearer {refresh}'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DeviceToken.query.count(), 0)

    def test_login_does_not_say_which_usernames_exist(self):
        unknown = self.login('NOBODY/1', 'phone-1')
        wrong = self.login('MCT/20/0001', 'phone-1', password='wrong')
        self.assertEqual((unknown.status_code, unknown.get_json()),
                         (wrong.status_code, wrong.get_json()))
        self.assertEqual(unknown.status_code, 401)

    def test_disabled_account_is_only_revealed_to_the_right_password(self):
        self.user.is_active = False
        db.session.commit()
        self.assertEqual(self.login('MCT/20/0001', 'phone-1', password='wrong').status_code, 401)
        resp = self.login('MCT/20/0001', 'phone-1')
        self.assertEqual((resp.status_code, resp.get_json()['error']), (403, 'Account is disabled'))

    def test_app_password_change_needs_six_characters(self):
        token = self.login('MCT/20/0001', 'phone-1').get_json()['token']
        resp = self.client.post('/api/v1/auth/change-password',
                                json={'new_password': 'abc', 'current_password': 'pw'},
                                headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(resp.status_code, 400)

    def test_one_phone_cannot_hold_two_student_accounts(self):
        self.make_student('MCT/20/0002', 'pw2')
        db.session.commit()
        self.assertEqual(self.login('MCT/20/0001', 'phone-1').status_code, 200)
        resp = self.login('MCT/20/0002', 'phone-1', password='pw2')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('DEVICE IN USE', resp.get_json()['error'])

    def test_placeholder_device_ids_are_refused(self):
        resp = self.login('MCT/20/0001', 'fallback_device_id')
        self.assertEqual(resp.status_code, 403)
        self.assertIn('DEVICE UNVERIFIED', resp.get_json()['error'])
        self.assertIsNone(db.session.get(Student, self.student.id).device_id)


if __name__ == '__main__':
    unittest.main()
