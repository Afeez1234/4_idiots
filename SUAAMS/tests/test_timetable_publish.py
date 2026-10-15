"""Tests for publishing the timetable and the "affects you" notifications
(timetable_publish.py and the admin route /admin/timetable/publish).

Pins:

  * publishing swaps a course's drafts in for its published classes, and
    leaves courses without drafts alone;
  * first publish -> "Timetable published"; later changes -> "Timetable
    updated", sent only to the students and lecturers (co-lecturers too)
    of courses whose classes actually changed;
  * a course re-published identically notifies nobody;
  * each person gets ONE notification, however many of their courses changed;
  * hand edits on the timetable page notify for published classes only --
    adding a draft or editing one tells nobody;
  * the route is audited and refuses a semester with no drafts;
  * a slot's start date (effective_from, for Analytics) survives a
    re-publish that keeps its course, day and times -- and so do its
    sessions -- while a new or moved slot, or a hand edit of the day or
    time, starts from today; a room change keeps the date.

FCM is never reached: tests have no Firebase app, and notify_users swallows
push failures by design. The Notification rows are what's checked.

Run with:  python tests/test_timetable_publish.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import timetable_publish as tp  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Notification, Semester, Session as SessionModel, Timetable,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class TimetablePublishTestCase(unittest.TestCase):

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

        faculty = Faculty(name='Examples')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Sample Studies', faculty_id=faculty.id)
        self.sem = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2026, 6, 1), is_active=True)
        db.session.add_all([self.dept, self.sem])
        db.session.flush()
        self.admin = self.user('tunde', 'admin')
        self.lect = self.lecturer('Dr A. Example', 'STF/1')
        self.co_lect = self.lecturer('Dr B. Helper', 'STF/2')
        self.sam101 = self.course('SAM101', self.lect)
        self.sam102 = self.course('SAM102', self.lect)
        self.sam101.co_lecturers.append(self.co_lect)
        self.ada = self.student('Ada', 'S/1', self.sam101, self.sam102)   # both courses
        self.bayo = self.student('Bayo', 'S/2', self.sam102)              # SAM102 only
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures -------------------------------------------------------------

    def user(self, username, role):
        u = User(username=username, password_hash='x', role=role,
                 is_active=True, requires_password_change=False)
        db.session.add(u)
        db.session.flush()
        return u

    def lecturer(self, name, staff_id):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, lecturer):
        c = Course(course_title=f'Course {code}', course_code=code, lecturer_id=lecturer.id,
                   department_id=self.dept.id, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        return c

    def student(self, name, matric, *courses):
        st = Student(full_name=name, matric_number=matric, level='300',
                     department_id=self.dept.id, user_id=self.user(matric, 'student').id)
        db.session.add(st)
        db.session.flush()
        for c in courses:
            db.session.add(Enrollment(student_id=st.id, course_id=c.id))
        return st

    def slot(self, course, day, start, end, room, published):
        t = Timetable(course_id=course.id, semester_id=self.sem.id, day_of_week=day,
                      start_time=time(start), end_time=time(end), room=room,
                      is_published=published, created_by=self.admin.id)
        db.session.add(t)
        db.session.commit()
        return t

    def notes(self, person):
        """Notifications for a student or lecturer, oldest first."""
        return Notification.query.filter_by(user_id=person.user_id).order_by(Notification.id).all()

    def publish(self):
        return tp.publish_drafts(self.sem, self.admin.id)

    # ---- publish_drafts --------------------------------------------------------

    def test_first_publish_notifies_everyone_once(self):
        self.slot(self.sam101, 0, 8, 10, 'LR 1', published=False)
        self.slot(self.sam102, 1, 10, 12, 'LR 2', published=False)
        result = self.publish()

        self.assertEqual(result, {'courses': 2, 'slots': 2, 'notified': 4})
        self.assertEqual(Timetable.query.filter_by(is_published=False).count(), 0)
        # Ada takes both courses: still one notification, listing both.
        [note] = self.notes(self.ada)
        self.assertEqual(note.title, 'Timetable published: 2025/2026 Second Semester')
        self.assertIn('SAM101: Mon 08:00-10:00 LR 1', note.body)
        self.assertIn('SAM102: Tue 10:00-12:00 LR 2', note.body)
        self.assertEqual(note.type, 'timetable')
        # Bayo only hears about his course; the co-lecturer only about SAM101.
        [note] = self.notes(self.bayo)
        self.assertNotIn('SAM101', note.body)
        [note] = self.notes(self.co_lect)
        self.assertNotIn('SAM102', note.body)

    def test_republish_swaps_and_notifies_only_changed_courses(self):
        self.slot(self.sam101, 0, 8, 10, 'LR 1', published=True)
        self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        # New sheet: SAM101 moves room, SAM102 is identical.
        self.slot(self.sam101, 0, 8, 10, 'LR 9', published=False)
        self.slot(self.sam102, 1, 10, 12, 'LR 2', published=False)
        self.publish()

        rooms = {t.course_id: t.room for t in Timetable.query.all()}
        self.assertEqual(Timetable.query.count(), 2)          # old ones replaced
        self.assertEqual(rooms[self.sam101.id], 'LR 9')
        [note] = self.notes(self.ada)
        self.assertEqual(note.title, 'Timetable updated')
        self.assertEqual(note.body, 'SAM101: Mon 08:00-10:00 LR 9')
        self.assertEqual(self.notes(self.bayo), [])            # SAM102 didn't change
        self.assertEqual(len(self.notes(self.co_lect)), 1)

    def test_courses_without_drafts_are_left_alone(self):
        self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        self.slot(self.sam101, 0, 8, 10, 'LR 1', published=False)
        self.publish()
        self.assertEqual(Timetable.query.filter_by(course_id=self.sam102.id).count(), 1)
        self.assertEqual(self.notes(self.bayo), [])

    def test_nothing_to_publish(self):
        self.assertEqual(self.publish(), {'courses': 0, 'slots': 0, 'notified': 0})
        self.assertEqual(Notification.query.count(), 0)

    def test_long_bodies_are_cut_with_a_pointer(self):
        items = [(f'C{i:03}', False, [(0, time(8), time(10), 'A VERY LONG ROOM NAME', '')])
                 for i in range(30)]
        body = tp._body(items)
        self.assertLessEqual(len(body), tp.BODY_LIMIT)
        self.assertTrue(body.endswith('more course(s) -- open your timetable'))

    # ---- the admin routes ------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def test_publish_route_is_audited(self):
        self.sign_in()
        self.slot(self.sam101, 0, 8, 10, 'LR 1', published=False)
        self.client.post('/admin/timetable/publish', data={'semester_id': self.sem.id})
        self.assertEqual(Timetable.query.filter_by(is_published=True).count(), 1)
        self.assertEqual(AuditLog.query.filter_by(action='timetable.publish').count(), 1)

    def test_publish_route_with_no_drafts_changes_nothing(self):
        self.sign_in()
        self.client.post('/admin/timetable/publish', data={'semester_id': self.sem.id})
        self.assertEqual(AuditLog.query.filter_by(action='timetable.publish').count(), 0)

    def edit(self, **form):
        self.sign_in()
        return self.client.post('/admin/timetable', data=form)

    def test_hand_edit_of_a_published_class_notifies(self):
        t = self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        self.edit(action='update', timetable_id=t.id, course_id=self.sam102.id,
                  semester_id=self.sem.id, day_of_week=1, start_time='14:00',
                  end_time='16:00', room='LR 2', type='scheduled')
        self.assertEqual(db.session.get(Timetable, t.id).start_time, time(14))
        [note] = self.notes(self.bayo)
        self.assertEqual(note.title, 'Timetable updated')
        self.assertIn('Tue 14:00-16:00', note.body)

    def test_hand_delete_of_a_published_class_notifies(self):
        t = self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        self.edit(action='delete', timetable_id=t.id)
        [note] = self.notes(self.bayo)
        self.assertEqual(note.body, 'SAM102: no classes')

    def test_hand_edit_of_a_draft_notifies_nobody(self):
        t = self.slot(self.sam102, 1, 10, 12, 'LR 2', published=False)
        self.edit(action='delete', timetable_id=t.id)
        self.assertEqual(Notification.query.count(), 0)

    # ---- start dates (Analytics) ----------------------------------------------

    TODAY = date(2026, 3, 2)
    EARLIER = date(2026, 1, 12)

    def test_republish_keeps_an_unchanged_slots_start_date_and_sessions(self):
        old = self.slot(self.sam101, 0, 8, 10, 'LR 1', published=True)
        old.effective_from = self.EARLIER
        moved = self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        moved.effective_from = self.EARLIER
        held = SessionModel(course_id=self.sam101.id, session_date=date(2026, 1, 19),
                            timetable_id=old.id)
        db.session.add(held)
        db.session.commit()
        # Re-issued sheet: SAM101 only changes room; SAM102 moves to Wednesday.
        same = self.slot(self.sam101, 0, 8, 10, 'LR 9', published=False)
        new = self.slot(self.sam102, 2, 10, 12, 'LR 2', published=False)
        with mock.patch('timetable_publish.campus_today', return_value=self.TODAY):
            self.publish()
        self.assertEqual(db.session.get(Timetable, same.id).effective_from, self.EARLIER)
        self.assertEqual(db.session.get(SessionModel, held.id).timetable_id, same.id)
        self.assertEqual(db.session.get(Timetable, new.id).effective_from, self.TODAY)

    def test_hand_edit_of_day_or_time_restarts_the_date_but_room_does_not(self):
        t = self.slot(self.sam102, 1, 10, 12, 'LR 2', published=True)
        t.effective_from = self.EARLIER
        db.session.commit()
        form = dict(action='update', timetable_id=t.id, course_id=self.sam102.id,
                    semester_id=self.sem.id, day_of_week=1, start_time='10:00',
                    end_time='12:00', room='LR 7', type='scheduled')
        with mock.patch('blueprints.admin.campus_today', return_value=self.TODAY):
            self.edit(**form)
            self.assertEqual(db.session.get(Timetable, t.id).effective_from, self.EARLIER)
            self.edit(**dict(form, day_of_week=3))
        self.assertEqual(db.session.get(Timetable, t.id).effective_from, self.TODAY)

    def test_a_class_added_by_hand_starts_today(self):
        with mock.patch('blueprints.admin.campus_today', return_value=self.TODAY):
            self.edit(action='create', course_id=self.sam102.id, semester_id=self.sem.id,
                      day_of_week=4, start_time='08:00', end_time='10:00', room='LR 3',
                      type='scheduled')
        self.assertEqual(Timetable.query.one().effective_from, self.TODAY)


if __name__ == '__main__':
    unittest.main()
