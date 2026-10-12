"""Tests for lecturer review of offline taps (utils.pending_offline_taps,
utils.review_offline_tap, utils.accept_all_offline_taps).

An offline tap is a genuine signed read of a student's phone that the
terminal couldn't deliver in time, so it never becomes attendance on its own.
These pin what happens when a lecturer decides: accepted taps count at the
time of the tap (present/late computed against it), are labelled 'offline'
and attributable, never overwrite a real check-in, and can't land on the
register of a student who has since dropped the course.

Same setup as test_manual_marking.py: in-memory SQLite with the real models.

Run with:  python tests/test_offline_tap_review.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date, datetime, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

import utils  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance, OfflineCheckinLog,
)

# Class at 09:00 campus time (Africa/Lagos, UTC+1), 10-minute grace.
# captured_at is stored as naive UTC, so 08:05 UTC = 09:05 campus = on time,
# and 08:20 UTC = 09:20 campus = late.
CLASS_DAY = date(2026, 10, 12)
ON_TIME_UTC = datetime(2026, 10, 12, 8, 5)
LATE_UTC = datetime(2026, 10, 12, 8, 20)


class OfflineTapReviewTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Push is best-effort and needs Firebase; stub it and count calls.
        self.push = mock.patch('push_notifications.send_push_notification').start()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(dept)
        db.session.flush()

        lecturer_user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(lecturer_user)
        db.session.flush()
        self.lecturer_user = lecturer_user
        lecturer = Lecturer(full_name='Dr Ade', staff_id='S1',
                            department_id=dept.id, user_id=lecturer_user.id)
        db.session.add(lecturer)
        db.session.flush()

        self.course = Course(course_title='Control Systems', course_code='MCT 401',
                             lecturer_id=lecturer.id, department_id=dept.id)
        db.session.add(self.course)
        db.session.flush()

        def student(name, matric):
            user = User(username=matric, password_hash='x', role='student')
            db.session.add(user)
            db.session.flush()
            s = Student(full_name=name, matric_number=matric, level='400',
                        department_id=dept.id, user_id=user.id)
            db.session.add(s)
            db.session.flush()
            db.session.add(Enrollment(student_id=s.id, course_id=self.course.id))
            return s

        self.zara = student('Zara Bello', 'M1')
        self.ade = student('Ade Okafor', 'M2')

        self.session = SessionModel(course_id=self.course.id, is_active=False,
                                    session_date=CLASS_DAY, planned_start=time(9, 0))
        db.session.add(self.session)
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _tap(self, student, captured_at=ON_TIME_UTC):
        log = OfflineCheckinLog(student_id=student.id, session_id=self.session.id,
                                terminal_id='T1', captured_at=captured_at)
        db.session.add(log)
        db.session.commit()
        return log

    def _record(self, student):
        return Attendance.query.filter_by(session_id=self.session.id,
                                          student_id=student.id).first()

    def test_accept_records_offline_attendance_at_tap_time(self):
        log = self._tap(self.ade)
        outcome = utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=True)
        self.assertEqual(outcome, 'accepted')

        rec = self._record(self.ade)
        self.assertEqual(rec.method, 'offline')
        self.assertEqual(rec.marked_by, self.lecturer_user.id)
        self.assertEqual(rec.time_in, ON_TIME_UTC)
        self.assertEqual(rec.status, 'present')

        log = db.session.get(OfflineCheckinLog, log.id)
        self.assertEqual(log.status, 'accepted')
        self.assertEqual(log.reviewed_by, self.lecturer_user.id)
        self.assertIsNotNone(log.reviewed_at)
        self.push.assert_called_once()

    def test_late_tap_is_late(self):
        # Unlike a hand mark, the tap time is known, so lateness applies.
        log = self._tap(self.ade, captured_at=LATE_UTC)
        utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=True)
        self.assertEqual(self._record(self.ade).status, 'late')

    def test_reject_records_nothing(self):
        log = self._tap(self.ade)
        outcome = utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=False)
        self.assertEqual(outcome, 'rejected')
        self.assertIsNone(self._record(self.ade))
        log = db.session.get(OfflineCheckinLog, log.id)
        self.assertEqual((log.status, log.reviewed_by), ('rejected', self.lecturer_user.id))
        self.push.assert_not_called()

    def test_does_not_overwrite_a_real_check_in(self):
        log = self._tap(self.ade)
        db.session.add(Attendance(student_id=self.ade.id, session_id=self.session.id,
                                  status='late', method='nfc'))
        db.session.commit()

        outcome = utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=True)
        self.assertEqual(outcome, 'already_marked')
        rec = self._record(self.ade)
        self.assertEqual((rec.method, rec.status, rec.marked_by), ('nfc', 'late', None))
        self.assertEqual(db.session.get(OfflineCheckinLog, log.id).status, 'superseded')

    def test_dropped_student_is_rejected(self):
        log = self._tap(self.ade)
        Enrollment.query.filter_by(student_id=self.ade.id).delete()
        db.session.commit()

        outcome = utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=True)
        self.assertEqual(outcome, 'not_enrolled')
        self.assertIsNone(self._record(self.ade))
        self.assertEqual(db.session.get(OfflineCheckinLog, log.id).status, 'rejected')

    def test_reviewed_once_only(self):
        log = self._tap(self.ade)
        utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=False)
        outcome = utils.review_offline_tap(self.session, log.id, self.lecturer_user, accept=True)
        self.assertEqual(outcome, 'already_reviewed')
        self.assertIsNone(self._record(self.ade))

    def test_tap_from_another_session_not_found(self):
        other = SessionModel(course_id=self.course.id, is_active=False)
        db.session.add(other)
        db.session.commit()
        log = self._tap(self.ade)
        outcome = utils.review_offline_tap(other, log.id, self.lecturer_user, accept=True)
        self.assertEqual(outcome, 'not_found')

    def test_pending_list_hides_students_with_attendance(self):
        self._tap(self.zara, captured_at=LATE_UTC)
        self._tap(self.ade)
        names = [log.student.full_name for log in utils.pending_offline_taps(self.session)]
        # Oldest tap first.
        self.assertEqual(names, ['Ade Okafor', 'Zara Bello'])

        utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        names = [log.student.full_name for log in utils.pending_offline_taps(self.session)]
        self.assertEqual(names, ['Zara Bello'])

    def test_accept_all(self):
        self._tap(self.zara)
        self._tap(self.ade, captured_at=LATE_UTC)
        counts = utils.accept_all_offline_taps(self.session, self.lecturer_user)

        self.assertEqual(counts, {'accepted': 2})
        self.assertEqual(self._record(self.zara).status, 'present')
        self.assertEqual(self._record(self.ade).status, 'late')
        self.assertEqual(utils.pending_offline_taps(self.session), [])
        # One push per accepted student, sent after the batch.
        self.assertEqual(self.push.call_count, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
