"""Tests for readers with their own identity and the room check
(terminal_rooms.py, models.Terminal, the admin Terminals page, and the
check-in routes that use them).

Pins:

  * a reader signs in with its own code + secret; a wrong secret, or a
    disabled reader (even with the old shared secret), is refused; the old
    shared pair still works during the changeover; last_seen_at updates;
  * the class's room is the room given at start, else its slot's room;
    rooms compare loosely ("lt-1" = "LT 1");
  * flag mode records a wrong-room check-in, marked; enforce mode refuses
    it; unknown rooms are never flagged; Bluetooth finds its reader by the
    number inside the code; offline taps carry the flag through review;
  * the admin page shows a new secret once and stores only its hash;
  * starting a class links its slot and room even when times are typed.

Run with:  python tests/test_terminal_rooms.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402

import ble_beacon  # noqa: E402
import terminal_rooms  # noqa: E402
from beacon import mint_beacon  # noqa: E402
from campus_time import campus_now, campus_today  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, Course, Department, Enrollment, Faculty, Lecturer,
    OfflineCheckinLog, Semester, Session as SessionModel, Student, Terminal,
    Timetable, User,
)
from utils import review_offline_tap, start_class_session  # noqa: E402
from api.student import api_student_bp  # noqa: E402
from api.lecturer import api_lecturer_bp  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

SECRETS = {'BEACON_SIGNING_SECRET': 'test-beacon-secret', 'BLE_BEACON_SECRET': 'test-ble-secret',
           'TERMINAL_ID': 'shared-01', 'TERMINAL_SECRET': 'shared-secret'}


class TerminalRoomsTestCase(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, SECRETS)
        self.env.start()
        os.environ.pop('ROOM_CHECK', None)
        mock.patch('api.student.send_push_notification').start()

        # The real templates: the admin test reads the rendered page.
        self.app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates'))
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', SECRET_KEY='test',
            JWT_SECRET_KEY='test-jwt-secret-key-that-is-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        for bp in (api_student_bp, api_lecturer_bp, auth_bp, admin_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.sem = Semester(name='S1', start_date=date(2026, 9, 1), end_date=date(2099, 1, 1), is_active=True)
        db.session.add_all([self.dept, self.sem])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        lu = self.user('STF/1', 'lecturer')
        self.lecturer = Lecturer(full_name='Dr Ade', staff_id='STF/1', department_id=self.dept.id, user_id=lu.id)
        db.session.add(self.lecturer)
        db.session.flush()
        self.course = Course(course_code='MCT 401', course_title='Robotics', lecturer_id=self.lecturer.id,
                             department_id=self.dept.id, semester_id=self.sem.id)
        db.session.add(self.course)
        db.session.flush()
        su = self.user('MCT/1', 'student')
        self.student = Student(full_name='Ada', matric_number='MCT/1', level='400',
                               department_id=self.dept.id, user_id=su.id)
        db.session.add(self.student)
        db.session.flush()
        db.session.add(Enrollment(student_id=self.student.id, course_id=self.course.id))
        # Today's slot is in LT 1; the class is running.
        now = campus_now()
        self.slot = Timetable(course_id=self.course.id, semester_id=self.sem.id,
                              day_of_week=now.weekday(), start_time=time(0, 0), end_time=time(23, 59),
                              room='LT 1', created_by=self.admin.id, is_published=True)
        db.session.add(self.slot)
        db.session.flush()
        self.session = SessionModel(course_id=self.course.id, session_date=campus_today(),
                                    is_active=True, timetable_id=self.slot.id)
        db.session.add(self.session)
        self.lt1 = self.reader('T-01', 'LT 1', ble=1)
        self.lt2 = self.reader('T-02', 'LT 2', ble=2)
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        self.env.stop()
        os.environ.pop('ROOM_CHECK', None)
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures -----------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, role=role, is_active=True, requires_password_change=False,
                 password_hash=bcrypt.hashpw(b'x', bcrypt.gensalt(4)).decode())
        db.session.add(u)
        db.session.flush()
        return u

    def reader(self, code, room, ble=None, secret=None):
        t = Terminal(code=code, name=code, room=room, ble_number=ble,
                     secret_hash=terminal_rooms.hash_secret(secret or f'secret-{code}'))
        db.session.add(t)
        db.session.flush()
        return t

    def tap(self, code, secret=None):
        token = mint_beacon(self.student.id, self.session.id)
        return self.client.post('/api/v1/student/checkin', json={'beacon_token': token},
                                headers={'X-Terminal-Id': code,
                                         'X-Terminal-Secret': secret or f'secret-{code}'})

    def attendance(self):
        return Attendance.query.filter_by(student_id=self.student.id).one_or_none()

    # ---- signing in ---------------------------------------------------------------

    def test_own_secret_signs_in_and_updates_last_seen(self):
        self.assertEqual(self.tap('T-01').status_code, 200)
        self.assertIsNotNone(db.session.get(Terminal, self.lt1.id).last_seen_at)
        self.assertEqual(self.attendance().terminal_id, self.lt1.id)

    def test_wrong_secret_is_refused(self):
        self.assertEqual(self.tap('T-01', secret='secret-T-02').status_code, 401)
        self.assertIsNone(self.attendance())

    def test_disabled_reader_is_refused_even_with_the_shared_secret(self):
        shared = self.reader('shared-01', 'LT 1')
        shared.is_active = False
        db.session.commit()
        self.assertEqual(self.tap('shared-01', secret='shared-secret').status_code, 401)

    def test_old_shared_pair_still_works_during_the_changeover(self):
        resp = self.tap('shared-01', secret='shared-secret')
        self.assertEqual(resp.status_code, 200)
        # An unregistered reader has no room, so it is never flagged.
        self.assertIsNone(self.attendance().wrong_room)

    # ---- the room check -----------------------------------------------------------

    def test_flag_mode_records_a_wrong_room_tap_marked(self):
        self.assertEqual(self.tap('T-02').status_code, 200)
        self.assertTrue(self.attendance().wrong_room)

    def test_same_room_is_not_flagged_and_compares_loosely(self):
        self.lt1.room = 'lt-1'
        db.session.commit()
        self.tap('T-01')
        self.assertIs(self.attendance().wrong_room, False)

    def test_enforce_mode_refuses_a_wrong_room_tap(self):
        os.environ['ROOM_CHECK'] = 'enforce'
        resp = self.tap('T-02')
        self.assertEqual((resp.status_code, resp.get_json()['reason']), (409, 'wrong_room'))
        self.assertIsNone(self.attendance())

    def test_off_mode_does_not_check(self):
        os.environ['ROOM_CHECK'] = 'off'
        self.tap('T-02')
        self.assertIsNone(self.attendance().wrong_room)

    def test_room_given_at_start_overrides_the_timetable(self):
        # The class moved to LT 2 today; the LT 2 reader is now right.
        self.session.room = 'LT 2'
        db.session.commit()
        self.tap('T-02')
        self.assertIs(self.attendance().wrong_room, False)

    def test_bluetooth_finds_its_reader_by_number(self):
        payload = ble_beacon.build_payload(2, ble_beacon.current_slot())   # LT 2's code
        token = create_access_token(identity=str(self.student.user_id), additional_claims={'role': 'student'})
        resp = self.client.post('/api/v1/student/checkin/ble', json={'payload': payload.hex()},
                                headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(resp.status_code, 200)
        record = self.attendance()
        self.assertEqual((record.terminal_id, record.wrong_room), (self.lt2.id, True))

    def test_offline_tap_carries_the_flag_through_review(self):
        expired = mint_beacon(self.student.id, self.session.id, ttl_seconds=-1)
        self.client.post('/api/v1/student/checkin/backlog', json={'records': [{'beacon_token': expired}]},
                         headers={'X-Terminal-Id': 'T-02', 'X-Terminal-Secret': 'secret-T-02'})
        log = OfflineCheckinLog.query.one()
        self.assertTrue(log.wrong_room)
        self.assertEqual(review_offline_tap(self.session, log.id, self.admin, accept=True, notify=False), 'accepted')
        record = self.attendance()
        self.assertEqual((record.terminal_id, record.wrong_room), (self.lt2.id, True))

    # ---- admin page ----------------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def test_new_reader_secret_is_shown_once_and_only_its_hash_stored(self):
        self.sign_in()
        resp = self.client.post('/admin/terminals', data={'action': 'create', 'code': 'T-03',
                                                          'name': 'Main Hall', 'room': 'Main Hall'})
        page = resp.get_data(as_text=True)
        t = Terminal.query.filter_by(code='T-03').one()
        secret = page.split('TERMINAL_SECRET "')[1].split('"')[0]
        self.assertEqual(t.secret_hash, terminal_rooms.hash_secret(secret))
        self.assertNotIn(secret, t.secret_hash)
        # The page shown later doesn't repeat it.
        self.assertNotIn(secret, self.client.get('/admin/terminals').get_data(as_text=True))

    def regenerate(self, current):
        return self.client.post('/admin/terminals', data={
            'action': 'regenerate', 'terminal_id': self.lt1.id, 'current': current})

    def test_new_secret_replaces_the_old_one(self):
        from blueprints.admin import _secret_fingerprint
        self.sign_in()
        # The form carries the current secret's fingerprint, as the page renders it.
        self.regenerate(_secret_fingerprint(self.lt1))
        self.assertEqual(self.tap('T-01').status_code, 401)            # old secret dead

    def test_a_resent_new_secret_form_issues_nothing(self):
        # Refreshing the page that showed a new secret re-sends the form. It
        # used to issue a second secret, killing the one just copied into
        # the reader. Since 2026-10-18 the stale fingerprint is refused.
        from blueprints.admin import _secret_fingerprint
        self.sign_in()
        stale = _secret_fingerprint(self.lt1)
        page = self.regenerate(stale).get_data(as_text=True)
        issued = page.split('TERMINAL_SECRET "')[1].split('"')[0]
        hash_after_first = db.session.get(Terminal, self.lt1.id).secret_hash

        resp = self.regenerate(stale)                                  # the refresh
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(db.session.get(Terminal, self.lt1.id).secret_hash, hash_after_first)
        self.assertEqual(hash_after_first, terminal_rooms.hash_secret(issued))

    def test_page_asks_before_disabling_and_labels_the_edit_fields(self):
        self.sign_in()
        page = self.client.get('/admin/terminals').get_data(as_text=True)
        self.assertIn('class="disable-form" data-code="T-01"', page)
        self.assertIn(f'<label class="form-label" for="edit-room-{self.lt1.id}">Room</label>', page)

    def test_duplicate_code_is_refused(self):
        self.sign_in()
        self.client.post('/admin/terminals', data={'action': 'create', 'code': 'T-01', 'name': 'Again'})
        self.assertEqual(Terminal.query.filter_by(code='T-01').count(), 1)

    # ---- starting a class -----------------------------------------------------------

    def test_start_links_slot_and_room_even_with_typed_times(self):
        self.session.is_active = False
        db.session.commit()
        outcome, s = start_class_session(self.lecturer, self.course.id, time(9), time(11))
        self.assertEqual(outcome, 'started')
        self.assertEqual((s.timetable_id, s.room, s.planned_start), (self.slot.id, 'LT 1', time(9)))

    def test_app_gets_todays_room_and_can_start_in_another(self):
        # The class moved: the lecturer starts it from the app in LT 2.
        self.session.is_active = False
        db.session.commit()
        token = create_access_token(identity=str(self.lecturer.user_id), additional_claims={'role': 'lecturer'})
        headers = {'Authorization': f'Bearer {token}'}
        data = self.client.get(f'/api/v1/lecturer/course/{self.course.id}', headers=headers).get_json()['data']
        self.assertEqual(data['today_room'], 'LT 1')                     # pre-fills the Room field
        resp = self.client.post(f'/api/v1/lecturer/course/{self.course.id}/start-session',
                                json={'room': 'LT 2'}, headers=headers)
        self.assertEqual(resp.status_code, 201)
        data = self.client.get(f'/api/v1/lecturer/course/{self.course.id}', headers=headers).get_json()['data']
        self.assertEqual(data['active_session']['room'], 'LT 2')


if __name__ == '__main__':
    unittest.main()
