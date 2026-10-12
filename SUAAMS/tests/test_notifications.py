"""Tests for bulk notifications (push_notifications.notify_users) and who an
announcement reaches (utils.announcement_user_ids).

Announcements used to notify students one at a time inside the request --
a commit, a token lookup and a blocking FCM call each -- so a big
announcement was killed at Render's 30s limit half-way through. These pin:

  * everyone in scope gets an in-app notification, each user once,
  * phones are pushed in batches, not one request per student,
  * tokens Firebase says are dead get removed,
  * Firebase being down never stops the in-app notifications,
  * the announcement audience matches its scope.

Firebase is faked; nothing is sent.

Run with:  python tests/test_notifications.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from firebase_admin import messaging  # noqa: E402

import push_notifications  # noqa: E402
from push_notifications import notify_users  # noqa: E402
from utils import announcement_user_ids  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Course, Enrollment, Lecturer,
    Announcement, Notification, DeviceToken,
)


class FakeResult:
    def __init__(self, exception=None):
        self.success = exception is None
        self.exception = exception


class NotificationsTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.mct = Department(name='Mechatronics', faculty_id=faculty.id)
        self.eee = Department(name='Electrical', faculty_id=faculty.id)
        db.session.add_all([self.mct, self.eee])
        db.session.flush()

        lect_user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(lect_user)
        db.session.flush()
        lecturer = Lecturer(full_name='Dr Ade', staff_id='S1',
                            department_id=self.mct.id, user_id=lect_user.id)
        db.session.add(lecturer)
        db.session.flush()
        self.course = Course(course_title='Control', course_code='MCT 401',
                             lecturer_id=lecturer.id, department_id=self.mct.id)
        db.session.add(self.course)
        db.session.flush()

        self.users = []
        for i in range(250):
            dept = self.mct if i < 150 else self.eee
            u = User(username=f'S{i:04d}', password_hash='x', role='student')
            db.session.add(u)
            db.session.flush()
            s = Student(full_name=f'S{i}', matric_number=u.username, level='400',
                        department_id=dept.id, user_id=u.id)
            db.session.add(s)
            db.session.flush()
            if i < 40:
                db.session.add(Enrollment(student_id=s.id, course_id=self.course.id))
            db.session.add(DeviceToken(user_id=u.id, fcm_token=f'tok-{i}', platform='android'))
            self.users.append(u)
        db.session.commit()

        mock.patch.object(push_notifications, '_get_firebase_app', return_value=object()).start()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def fake_send_each(self, dead_tokens=()):
        calls = []

        def send_each(messages, app=None):
            calls.append(len(messages))
            return mock.Mock(responses=[
                FakeResult(messaging.UnregisteredError('gone') if m.token in dead_tokens else None)
                for m in messages
            ])
        return calls, mock.patch.object(messaging, 'send_each', side_effect=send_each)

    def test_everyone_gets_one_notification_and_pushes_are_batched(self):
        ids = [u.id for u in self.users]
        calls, patch = self.fake_send_each()
        with patch:
            notify_users(ids + ids[:10], 'announcement', 'Title', 'Body')  # duplicates on purpose
        self.assertEqual(Notification.query.count(), 250)
        self.assertEqual(calls, [100, 100, 50])  # 3 requests, not 250

    def test_dead_tokens_are_removed(self):
        calls, patch = self.fake_send_each(dead_tokens={'tok-3', 'tok-7'})
        with patch:
            notify_users([u.id for u in self.users[:10]], 'announcement', 'T', 'B')
        remaining = {t.fcm_token for t in DeviceToken.query.all()}
        self.assertNotIn('tok-3', remaining)
        self.assertNotIn('tok-7', remaining)
        self.assertIn('tok-4', remaining)

    def test_firebase_down_still_saves_in_app_notifications(self):
        with mock.patch.object(messaging, 'send_each', side_effect=RuntimeError('FCM down')):
            notify_users([u.id for u in self.users[:5]], 'announcement', 'T', 'B')
        self.assertEqual(Notification.query.count(), 5)

    def test_announcement_audience_matches_its_scope(self):
        def audience(**kw):
            return set(announcement_user_ids(Announcement(title='t', body='b', sender_id=1, **kw)))

        everyone = {u.id for u in self.users}
        self.assertEqual(audience(scope='university'), everyone)
        self.assertEqual(audience(scope='department', department_id=self.mct.id),
                         {u.id for u in self.users[:150]})
        self.assertEqual(audience(scope='course', course_id=self.course.id),
                         {u.id for u in self.users[:40]})
        self.assertEqual(audience(scope='department', department_id=None), set())


if __name__ == '__main__':
    unittest.main()
