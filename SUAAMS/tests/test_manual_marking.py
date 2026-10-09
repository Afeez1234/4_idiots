"""Tests for lecturer manual marking (utils.mark_student_present and
utils.students_not_checked_in).

Manual marking is the fallback for a student whose phone can't check in, and
it is the one way attendance gets recorded with no device evidence at all --
only a lecturer's word. So the rules these pin are about keeping that
honest: it is attributable, it never overwrites a real check-in, it only
covers enrolled students, and it is never auto-'late'.

Runs against a throwaway in-memory SQLite database with the real models,
not mocks, because the interesting failures here are query and constraint
behaviour.

Run with:  python tests/test_manual_marking.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402

import utils  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance,
)


class ManualMarkingTestCase(unittest.TestCase):

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

        course = Course(course_title='Control Systems', course_code='MCT 401',
                        lecturer_id=lecturer.id, department_id=dept.id)
        db.session.add(course)
        db.session.flush()

        def student(name, matric, enrolled=True):
            user = User(username=matric, password_hash='x', role='student')
            db.session.add(user)
            db.session.flush()
            s = Student(full_name=name, matric_number=matric, level='400',
                        department_id=dept.id, user_id=user.id)
            db.session.add(s)
            db.session.flush()
            if enrolled:
                db.session.add(Enrollment(student_id=s.id, course_id=course.id))
            return s

        self.zara = student('Zara Bello', 'M1')
        self.ade = student('Ade Okafor', 'M2')
        self.outsider = student('Not Enrolled', 'M3', enrolled=False)

        # planned_start far in the past, so a self check-in now would be
        # computed 'late' -- manual marks must still say 'present'.
        self.session = SessionModel(course_id=course.id, is_active=True,
                                    planned_start=time(0, 0))
        db.session.add(self.session)
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def _record(self, student):
        return Attendance.query.filter_by(session_id=self.session.id,
                                          student_id=student.id).first()

    def test_marks_present_with_attribution(self):
        outcome = utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        self.assertEqual(outcome, 'marked')
        rec = self._record(self.ade)
        self.assertEqual(rec.method, 'manual')
        self.assertEqual(rec.marked_by, self.lecturer_user.id)
        self.push.assert_called_once()

    def test_never_computed_late(self):
        # The session started at 00:00, so compute_attendance_status would
        # say 'late'. Marking time says nothing about arrival time.
        self.assertEqual(utils.compute_attendance_status(self.session), 'late')
        utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        self.assertEqual(self._record(self.ade).status, 'present')

    def test_does_not_overwrite_a_real_check_in(self):
        db.session.add(Attendance(student_id=self.ade.id, session_id=self.session.id,
                                  status='late', method='nfc'))
        db.session.commit()
        outcome = utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        self.assertEqual(outcome, 'already_marked')
        rec = self._record(self.ade)
        self.assertEqual((rec.method, rec.status, rec.marked_by), ('nfc', 'late', None))
        self.push.assert_not_called()

    def test_rejects_student_not_enrolled(self):
        outcome = utils.mark_student_present(self.session, self.outsider.id, self.lecturer_user)
        self.assertEqual(outcome, 'not_enrolled')
        self.assertIsNone(self._record(self.outsider))

    def test_works_after_session_ended(self):
        self.session.is_active = False
        db.session.commit()
        outcome = utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        self.assertEqual(outcome, 'marked')

    def test_not_checked_in_list(self):
        names = [s.full_name for s in utils.students_not_checked_in(self.session)]
        # Enrolled only, sorted by name.
        self.assertEqual(names, ['Ade Okafor', 'Zara Bello'])

        utils.mark_student_present(self.session, self.ade.id, self.lecturer_user)
        names = [s.full_name for s in utils.students_not_checked_in(self.session)]
        self.assertEqual(names, ['Zara Bello'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
