"""Tests for the admin dashboard's "today" view (dashboard_today.py, the
/admin/dashboard route and /admin/timetable/<id>/remind).

Pins:

  * a slot's status from the clock: upcoming, due, late (30 min after the
    start with no session), missed (ended with no session), live, ended;
  * a course meeting twice a day: each session lands on its own slot, by
    timetable_id or, for older sessions, by planned_start;
  * starting a class picks the slot running now, not the day's first, and
    records timetable_id;
  * check-ins today: count, expected (enrolled in the classes held), split
    by method with NULL shown as "unknown";
  * department rates use sessions x enrolled PER COURSE, active semester only;
  * the reminder notifies every lecturer on the course, is audited, and
    shows on the next load;
  * the dashboard's queries don't grow with the number of classes;
  * the door board (2026-10-25): which group each class lands in, what its
    room's reader shows (the firmware's own wording), a live class started
    outside the timetable, and its 15-second refresh endpoint.

Run with:  python tests/test_dashboard_today.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, datetime, time, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402
from sqlalchemy import event  # noqa: E402

import dashboard_today as dt  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, AuditLog, Course, Department, Enrollment, Faculty, Lecturer,
    Notification, Semester, Session as SessionModel, Student, Terminal, Timetable, User,
)
from utils import resolve_timetable_slot_for_course  # noqa: E402
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402

# A Thursday. weekday() == 3.
DAY = date(2026, 10, 8)


def at(hh, mm=0):
    return datetime.combine(DAY, time(hh, mm))


class DashboardTodayTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
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
        self.sem = Semester(name='2026/2027 First Semester', start_date=date(2026, 9, 1),
                            end_date=date(2027, 1, 31), is_active=True)
        self.old = Semester(name='2025/2026 Second Semester', start_date=date(2026, 2, 1),
                            end_date=date(2026, 7, 1))
        db.session.add_all([self.mct, self.cpe, self.sem, self.old])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lead = self.lecturer('Dr Lead', 'STF/1')
        self.helper = self.lecturer('Dr Help', 'STF/2')
        self.course401 = self.course('MCT 401', self.mct, co=[self.helper])
        db.session.commit()

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

    def course(self, code, dept, semester=None, co=()):
        c = Course(course_code=code, course_title=code, lecturer_id=self.lead.id,
                   department_id=dept.id, semester_id=(semester or self.sem).id)
        c.co_lecturers = list(co)
        db.session.add(c)
        db.session.flush()
        return c

    def slot(self, course, start, end, room='LT 1'):
        s = Timetable(course_id=course.id, semester_id=self.sem.id, day_of_week=DAY.weekday(),
                      start_time=time(*start), end_time=time(*end), room=room,
                      created_by=self.admin.id, is_published=True)
        db.session.add(s)
        db.session.flush()
        return s

    def session(self, course, active=False, slot=None, planned=None, on=DAY):
        s = SessionModel(course_id=course.id, session_date=on, is_active=active,
                         timetable_id=slot.id if slot else None,
                         planned_start=time(*planned) if planned else None)
        db.session.add(s)
        db.session.flush()
        return s

    def students(self, course, n):
        out = []
        for i in range(n):
            u = self.user(f'{course.course_code}/{i}', 'student')
            st = Student(full_name=f'S{i}', matric_number=f'{course.course_code}/{i}', level='400',
                         department_id=self.mct.id, user_id=u.id)
            db.session.add(st)
            db.session.flush()
            db.session.add(Enrollment(student_id=st.id, course_id=course.id))
            out.append(st)
        db.session.flush()
        return out

    def checkin(self, student, session, method='nfc'):
        db.session.add(Attendance(student_id=student.id, session_id=session.id, method=method))
        db.session.flush()

    def statuses(self, now):
        return [r['status'] for r in dt.today(self.sem, now=now)['slots']]

    # ---- status -----------------------------------------------------------------

    def test_status_follows_the_clock(self):
        self.slot(self.course401, (10, 0), (12, 0))
        db.session.commit()
        self.assertEqual(self.statuses(at(9, 50)), ['upcoming'])
        self.assertEqual(self.statuses(at(10, 29)), ['due'])
        self.assertEqual(self.statuses(at(10, 30)), ['late'])        # LATE_AFTER = 30 min
        self.assertEqual(self.statuses(at(12, 0)), ['missed'])

    def test_late_slots_become_alerts(self):
        self.slot(self.course401, (10, 0), (12, 0))
        db.session.commit()
        self.assertEqual(len(dt.today(self.sem, now=at(10, 45))['alerts']), 1)
        self.assertEqual(dt.today(self.sem, now=at(10, 5))['alerts'], [])

    def test_a_started_class_is_live_then_ended(self):
        s = self.slot(self.course401, (10, 0), (12, 0))
        sess = self.session(self.course401, active=True, slot=s)
        db.session.commit()
        self.assertEqual(self.statuses(at(10, 45)), ['live'])
        sess.is_active = False
        db.session.commit()
        self.assertEqual(self.statuses(at(13, 0)), ['ended'])

    def test_lecture_and_tutorial_on_the_same_day_are_told_apart(self):
        lecture = self.slot(self.course401, (9, 0), (11, 0))
        tutorial = self.slot(self.course401, (14, 0), (16, 0))
        self.session(self.course401, active=True, slot=tutorial)
        db.session.commit()
        rows = {r['slot'].id: r['status'] for r in dt.today(self.sem, now=at(14, 10))['slots']}
        self.assertEqual(rows, {lecture.id: 'missed', tutorial.id: 'live'})

    def test_older_sessions_match_by_planned_start(self):
        self.slot(self.course401, (9, 0), (11, 0))
        self.slot(self.course401, (14, 0), (16, 0))
        self.session(self.course401, planned=(9, 0))      # no timetable_id
        db.session.commit()
        self.assertEqual(self.statuses(at(15, 0)), ['ended', 'late'])

    def test_drafts_and_other_days_are_left_out(self):
        self.slot(self.course401, (10, 0), (12, 0)).is_published = False
        other = self.slot(self.course401, (10, 0), (12, 0))
        other.day_of_week = (DAY.weekday() + 1) % 7
        db.session.commit()
        self.assertEqual(self.statuses(at(11, 0)), [])

    # ---- starting a class -------------------------------------------------------

    def test_starting_a_class_picks_the_slot_running_now(self):
        self.slot(self.course401, (9, 0), (11, 0))
        tutorial = self.slot(self.course401, (14, 0), (16, 0))
        db.session.commit()
        self.assertEqual(resolve_timetable_slot_for_course(self.course401.id, on_date=at(13, 55)).id,
                         tutorial.id)
        self.assertEqual(resolve_timetable_slot_for_course(self.course401.id, on_date=at(18, 0)).id,
                         tutorial.id)                       # after the last slot: the last one

    def test_a_started_session_records_its_slot(self):
        from utils import start_class_session
        tutorial = self.slot(self.course401, (14, 0), (16, 0))
        db.session.commit()
        with mock.patch('utils.campus_now', return_value=at(14, 2)), \
                mock.patch('campus_time.campus_now', return_value=at(14, 2)):
            outcome, sess = start_class_session(self.lead, self.course401.id)
        self.assertEqual(outcome, 'started')
        self.assertEqual((sess.timetable_id, sess.planned_start), (tutorial.id, time(14, 0)))

    # ---- check-ins --------------------------------------------------------------

    def test_checkins_today_count_expected_and_method(self):
        s = self.slot(self.course401, (9, 0), (11, 0))
        sess = self.session(self.course401, active=True, slot=s)
        people = self.students(self.course401, 4)
        self.checkin(people[0], sess, 'nfc')
        self.checkin(people[1], sess, 'nfc')
        self.checkin(people[2], sess, None)
        # Yesterday's check-in doesn't count today.
        old = self.session(self.course401, on=date(2026, 10, 7))
        self.checkin(people[3], old, 'ble')
        db.session.commit()
        got = dt.today(self.sem, now=at(10, 0))
        self.assertEqual((got['checkins']['count'], got['checkins']['expected'], got['checkins']['pct']),
                         (3, 4, 75))
        self.assertEqual(got['checkins']['by_method'], [('nfc', 2), ('unknown', 1)])
        self.assertEqual(got['slots'][0]['present'], 3)
        self.assertEqual(got['live'][0]['room'], 'LT 1')

    # ---- departments ------------------------------------------------------------

    def test_department_rate_is_summed_per_course(self):
        # The example in department_rates' docstring: 10 sessions x 5 students
        # plus 1 session x 100 students = 150 expected check-ins.
        small = self.course('MCT 501', self.mct)
        big = self.course('MCT 502', self.mct)
        small_people, big_people = self.students(small, 5), self.students(big, 100)
        for i in range(10):
            sess = self.session(small, on=date(2026, 9, 10 + i))
            if i < 6:
                for st in small_people:
                    self.checkin(st, sess)              # 30 check-ins
        sess = self.session(big, on=date(2026, 9, 25))
        for st in big_people[:45]:
            self.checkin(st, sess)                      # 45 check-ins
        # Last semester's course doesn't count.
        past = self.course('MCT 499', self.mct, semester=self.old)
        self.checkin(self.students(past, 1)[0], self.session(past, on=date(2026, 3, 3)))
        db.session.commit()
        self.assertEqual(dt.department_rates(self.sem), [{'name': 'Mechatronics', 'percentage': 50.0}])

    # ---- reminder ---------------------------------------------------------------

    def test_reminder_notifies_every_lecturer_and_shows_next_load(self):
        from campus_time import campus_today
        s = self.slot(self.course401, (10, 0), (12, 0))
        # The reminder's audit entry is stamped with the real clock, so the
        # slot is put on the real today for the read-back below.
        s.day_of_week = campus_today().weekday()
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'], sess['username'], sess['role'] = self.admin.id, 'tunde', 'admin'
        self.client.post(f'/admin/timetable/{s.id}/remind')
        self.assertEqual({n.user_id for n in Notification.query.all()},
                         {self.lead.user_id, self.helper.user_id})
        self.assertEqual(Notification.query.first().data, {'course_id': self.course401.id})
        self.assertEqual(AuditLog.query.filter_by(action=dt.REMIND_ACTION).count(), 1)
        row = dt.today(self.sem)['slots'][0]
        self.assertIsNotNone(row['reminded_at'])

    def test_dashboard_page_renders(self):
        self.slot(self.course401, (10, 0), (12, 0))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess['user_id'], sess['username'], sess['role'] = self.admin.id, 'tunde', 'admin'
        with mock.patch('blueprints.admin.render_template', return_value='ok') as render:
            response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn('today', render.call_args.kwargs)

    def test_dashboard_error_renders_instead_of_redirecting(self):
        # It used to redirect to the login page, which bounces a signed-in
        # admin straight back: an endless redirect loop.
        with self.client.session_transaction() as sess:
            sess['user_id'], sess['username'], sess['role'] = self.admin.id, 'tunde', 'admin'
        with mock.patch('blueprints.admin.dashboard_today.today', side_effect=RuntimeError('db down')), \
             mock.patch('blueprints.admin.render_template', return_value='error page') as render:
            response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 500)
        self.assertTrue(render.call_args.kwargs.get('load_error'))

    # ---- page cost --------------------------------------------------------------

    def test_queries_do_not_grow_with_classes(self):
        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                # The classes table names each row's lecturer, so read it
                # here too: a lazy coordinator load would add a query per
                # lecturer.
                for row in dt.today(self.sem, now=at(11, 0))['slots']:
                    row['course'].lecturer_summary
                dt.department_rates(self.sem)
                dt.recent_checkins()
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen)

        def add_classes(n, start):
            for i in range(n):
                c = self.course(f'X{start + i}', self.cpe)
                # A lecturer of its own: with them all sharing Dr Lead the
                # identity map would hide a per-lecturer query.
                c.lecturer_id = self.lecturer(f'Dr X{start + i}', f'STF/X{start + i}').id
                s = self.slot(c, (9, 0), (10, 0))
                sess = self.session(c, slot=s)
                self.checkin(self.students(c, 1)[0], sess)
            db.session.commit()
            db.session.expire_all()

        add_classes(1, 0)
        few = queries()
        add_classes(8, 100)
        self.assertEqual(few, queries())


    # ---- door board ---------------------------------------------------------------

    def reader(self, room, seen_min_ago=1, active=True):
        last = None if seen_min_ago is None else datetime(2026, 10, 8, 10, 0) - timedelta(minutes=seen_min_ago)
        t = Terminal(code=f"R-{room}", name=room, room=room, secret_hash="x" * 64,
                     is_active=active, last_seen_at=last)
        db.session.add(t)
        db.session.flush()
        return t

    def board(self, now):
        # A fixed UTC clock for "last seen", 10:00 UTC.
        return dt.door_board(dt.today(self.sem, now=now), Terminal.query.all(),
                             timedelta(minutes=15), now_utc=datetime(2026, 10, 8, 10, 0))

    def by_course(self, board):
        return {r["course"].course_code: r for r in board["rows"]}

    def test_board_groups_each_class_by_what_it_needs(self):
        late = self.course("MCT 405", self.mct)
        offline = self.course("CPE 401", self.cpe)
        due = self.course("PHY 101", self.mct)
        later = self.course("MCT 403", self.mct)
        self.slot(late, (10, 0), (12, 0), room="LT 2")
        self.session(offline, active=True, slot=self.slot(offline, (10, 0), (12, 0), room="B14"))
        self.session(self.course401, active=True, slot=self.slot(self.course401, (9, 0), (12, 0)))
        self.slot(due, (10, 45), (12, 0), room="LT 3")
        self.slot(later, (14, 0), (16, 0), room="LT 1")
        self.reader("LT 1")                       # online
        self.reader("B14", seen_min_ago=27)       # offline: over 15 minutes
        db.session.commit()
        board = self.board(at(11, 0))
        rows = self.by_course(board)
        self.assertEqual((rows["MCT 405"]["group"], rows["MCT 405"]["reason"]), ("needs", "late"))
        self.assertEqual(rows["MCT 405"]["late_by"], 60)
        self.assertEqual((rows["CPE 401"]["group"], rows["CPE 401"]["reason"]), ("needs", "reader"))
        self.assertEqual(rows["CPE 401"]["seen_min"], 27)
        self.assertEqual(rows["MCT 401"]["group"], "live")
        self.assertEqual(rows["PHY 101"]["group"], "due")
        self.assertEqual((rows["MCT 403"]["group"], rows["MCT 403"]["starts_in"]), ("later", 180))
        self.assertEqual(board["facts"], {"needs": 2, "live": 2, "readers_online": 1, "readers": 2})

    def test_reader_screen_says_what_the_door_says(self):
        """The lines oled_display.ino draws, by the same rule as
        terminal_status.status_for: the live class, else "Not started
        yet", else NO CLASS with the next one."""
        live_slot = self.slot(self.course401, (10, 0), (12, 0), room="LT 1")
        sess = self.session(self.course401, active=True, slot=live_slot)
        for st in self.students(self.course401, 3)[:2]:
            self.checkin(st, sess)
        waiting = self.course("MCT 405", self.mct)
        self.slot(waiting, (10, 30), (12, 30), room="LT 2")
        idle = self.course("MCT 403", self.mct)
        self.slot(idle, (14, 0), (16, 0), room="LT 3")
        for room in ("LT 1", "LT 2", "LT 3"):
            self.reader(room)
        db.session.commit()
        rows = self.by_course(self.board(at(10, 40)))
        self.assertEqual(rows["MCT 401"]["screen"],
                         {"state": "lit", "lines": ["MCT 401", "2 / 3 checked in", "ends 12:00"]})
        self.assertEqual(rows["MCT 405"]["screen"]["lines"], ["MCT 405", "Not started yet", "10:30 - 12:30"])
        self.assertEqual(rows["MCT 403"]["screen"]["lines"], ["NO CLASS", "Next: MCT 403 at 14:00"])

    def test_readers_page_screens_match_the_board(self):
        """The Readers page (2026-10-26) shows each reader's screen by the
        board's rule, plus the states only a reader has: switched off,
        offline, no room set, and a room with nothing on today."""
        sess = self.session(self.course401, active=True,
                            slot=self.slot(self.course401, (10, 0), (12, 0), room="LT 1"))
        self.checkin(self.students(self.course401, 2)[0], sess)
        lit = self.reader("LT 1")
        quiet = self.reader("LT 7")
        off = self.reader("LT 2", active=False)
        gone = self.reader("LT 3", seen_min_ago=40)
        never = self.reader("LT 4", seen_min_ago=None)
        roomless = self.reader("LT 5")
        roomless.room = None
        db.session.commit()
        screens = dt.reader_screens(dt.today(self.sem, now=at(10, 40)), Terminal.query.all(),
                                    timedelta(minutes=15), now_utc=datetime(2026, 10, 8, 10, 0))
        self.assertEqual(screens[lit.id], self.by_course(self.board(at(10, 40)))["MCT 401"]["screen"])
        self.assertEqual(screens[quiet.id], {"state": "dim", "lines": ["NO CLASS", "Nothing else today"]})
        self.assertEqual(screens[off.id], {"state": "off", "lines": ["Reader switched off"]})
        self.assertEqual(screens[gone.id]["lines"], ["Reader offline", "taps held on reader"])
        self.assertEqual(screens[never.id]["lines"], ["Reader offline", "never seen"])
        self.assertEqual(screens[roomless.id]["state"], "none")

    def test_open_reader_lands_on_that_reader(self):
        # The board's Open reader carries the reader's id; the Readers page
        # marks that row and shows its screen.
        self.app.template_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
        self.session(self.course401, active=True,
                     slot=self.slot(self.course401, (10, 0), (12, 0), room="LT 1"))
        t = self.reader("LT 1", seen_min_ago=None)
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess["user_id"], sess["username"], sess["role"] = self.admin.id, "tunde", "admin"
        with mock.patch("dashboard_today.campus_now", return_value=at(10, 45)):
            board = self.client.get("/admin/dashboard/board").get_data(as_text=True)
            self.assertIn(f"/admin/terminals?reader={t.id}#reader-{t.id}", board)
            page = self.client.get(f"/admin/terminals?reader={t.id}").get_data(as_text=True)
        self.assertIn(f'id="reader-{t.id}" class="reader-row is-open"', page)
        self.assertIn("never seen", page)

    def test_a_room_without_a_reader_has_no_screen(self):
        self.session(self.course401, active=True,
                     slot=self.slot(self.course401, (10, 0), (12, 0), room="LT 9"))
        self.reader("LT 1", active=False)
        db.session.commit()
        row = self.board(at(10, 40))["rows"][0]
        self.assertEqual((row["reader"]["state"], row["screen"], row["group"]), ("none", None, "live"))

    def test_a_class_started_off_the_timetable_is_on_the_board(self):
        extra = self.course("CSC 499", self.cpe)
        s = self.session(extra, active=True)
        s.room = "B02"
        db.session.commit()
        rows = self.by_course(self.board(at(10, 40)))
        self.assertEqual(rows["CSC 499"]["group"], "live")
        self.assertIsNone(rows["CSC 499"]["slot"])

    def test_board_queries_do_not_grow_with_live_classes(self):
        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, "before_cursor_execute", listener)
            try:
                for row in self.board(at(11, 0))["rows"]:
                    row["course"].lecturer_summary
            finally:
                event.remove(db.engine, "before_cursor_execute", listener)
            return len(seen)

        def add_live(n, start):
            for i in range(n):
                c = self.course(f"Y{start + i}", self.cpe)
                c.lecturer_id = self.lecturer(f"Dr Y{start + i}", f"STF/Y{start + i}").id
                sess = self.session(c, active=True,
                                    slot=self.slot(c, (10, 0), (12, 0), room=f"R{start + i}"))
                self.checkin(self.students(c, 1)[0], sess)
                self.reader(f"R{start + i}")
            db.session.commit()
            db.session.expire_all()

        add_live(1, 0)
        few = queries()
        add_live(6, 100)
        self.assertEqual(few, queries())

    def test_board_refresh_endpoint_returns_the_board(self):
        # The real templates, not a mocked render: this checks the fragment
        # the dashboard swaps in.
        self.app.template_folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
        self.slot(self.course401, (10, 0), (12, 0))
        db.session.commit()
        with self.client.session_transaction() as sess:
            sess["user_id"], sess["username"], sess["role"] = self.admin.id, "tunde", "admin"
        with mock.patch("dashboard_today.campus_now", return_value=at(10, 45)):
            response = self.client.get("/admin/dashboard/board")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('id="door-board"', html)
        self.assertIn('id="door-facts"', html)
        self.assertIn("Notify lecturer", html)
        # Admins only.
        with self.client.session_transaction() as sess:
            sess["role"] = "student"
        self.assertNotEqual(self.client.get("/admin/dashboard/board").status_code, 200)


if __name__ == '__main__':
    unittest.main()
