"""Tests for editing and deleting courses, lecturers and students
(record_edits.py and the admin routes /admin/<kind>/<id>/edit and
/admin/<kind>/<id>/delete).

Pins:

  * an edit changes the record and leaves an audit entry with old -> new;
  * a course code stays unique within its semester;
  * a corrected staff ID / matric number moves the login username with it,
    and resets the password to the new ID only while it is still the
    default (requires_password_change);
  * an ID already used as someone's login is refused;
  * delete works for a record with no history and takes its login,
    enrollments and co-lecturer links with it;
  * delete is refused (nothing removed) for a course with sessions, a
    coordinator, a lecturer who ran a class, a student with attendance;
  * delete_blockers answers for a whole page in a fixed number of queries.

Run with:  python tests/test_record_edits.py
(also collected by pytest if it is installed)
"""

import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402
from sqlalchemy import event  # noqa: E402

import record_edits  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, AuditLog, Course, Department, Enrollment, Faculty, Lecturer,
    Semester, Session as SessionModel, Student, User,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


class RecordEditsTestCase(unittest.TestCase):

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
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        self.other_dept = Department(name='Computer', faculty_id=faculty.id)
        self.sem = Semester(name='2025/2026 First Semester', start_date=date(2025, 9, 1),
                            end_date=date(2099, 1, 1), is_active=True)
        db.session.add_all([self.dept, self.other_dept, self.sem])
        db.session.flush()
        self.admin = self.user('tunde', 'admin', fresh=False)
        self.lead = self.lecturer('Dr Lead', 'STF/1')
        self.helper = self.lecturer('Dr Helpr', 'STF/2')        # typo on purpose
        self.ada = self.student('Ada', 'MCT/20/0001')
        self.mct = self.course('MCT 401', self.lead, co=[self.helper])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures ---------------------------------------------------------------

    def user(self, username, role, fresh=True):
        # fresh = still on the default password (their ID), like a new account.
        u = User(username=username, role=role, is_active=True, requires_password_change=fresh,
                 password_hash=bcrypt.hashpw(username.encode(), bcrypt.gensalt(4)).decode())
        db.session.add(u)
        db.session.flush()
        return u

    def lecturer(self, name, staff_id):
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id,
                        user_id=self.user(staff_id, 'lecturer').id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def student(self, name, matric):
        st = Student(full_name=name, matric_number=matric, level='400', department_id=self.dept.id,
                     user_id=self.user(matric, 'student').id)
        db.session.add(st)
        db.session.flush()
        return st

    def course(self, code, coordinator, co=()):
        c = Course(course_code=code, course_title=code, lecturer_id=coordinator.id,
                   department_id=self.dept.id, semester_id=self.sem.id)
        c.co_lecturers = list(co)
        db.session.add(c)
        db.session.flush()
        return c

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def password_is(self, user, password):
        return bcrypt.checkpw(password.encode(), user.password_hash.encode())

    # ---- edit -------------------------------------------------------------------

    def test_course_edit_is_saved_and_audited(self):
        self.sign_in()
        self.client.post(f'/admin/courses/{self.mct.id}/edit', data={
            'code': 'mct 402', 'title': 'Robotics', 'department_id': self.other_dept.id,
            'semester_id': self.sem.id, 'credit_units': '3'})
        c = db.session.get(Course, self.mct.id)
        self.assertEqual((c.course_code, c.course_title, c.department_id, c.credit_units),
                         ('MCT 402', 'Robotics', self.other_dept.id, 3))
        entry = AuditLog.query.filter_by(action='course.edit').one()
        self.assertEqual(entry.details['changes']['course_code'], {'from': 'MCT 401', 'to': 'MCT 402'})

    def test_course_code_must_stay_unique_in_its_semester(self):
        other = self.course('MCT 403', self.lead)
        db.session.commit()
        with self.assertRaises(record_edits.EditError):
            record_edits.edit_course(other, {'code': 'MCT 401', 'title': 'x', 'semester_id': self.sem.id})

    def test_new_staff_id_moves_the_login_and_default_password(self):
        self.sign_in()
        self.client.post(f'/admin/lecturers/{self.helper.id}/edit', data={
            'full_name': 'Dr Helper', 'staff_id': 'STF/20', 'department_id': self.dept.id})
        lect = db.session.get(Lecturer, self.helper.id)
        self.assertEqual((lect.full_name, lect.staff_id, lect.user.username),
                         ('Dr Helper', 'STF/20', 'STF/20'))
        self.assertTrue(self.password_is(lect.user, 'STF/20'))

    def test_a_password_they_chose_is_kept(self):
        self.ada.user.requires_password_change = False
        db.session.commit()
        record_edits.edit_student(self.ada, {'full_name': 'Ada', 'matric_number': 'MCT/20/0009',
                                             'level': '400L', 'department_id': self.dept.id})
        self.assertEqual(self.ada.user.username, 'MCT/20/0009')
        self.assertTrue(self.password_is(self.ada.user, 'MCT/20/0001'))    # unchanged
        self.assertEqual(self.ada.level, '400')                             # normalised

    def test_an_id_already_used_as_a_login_is_refused(self):
        self.sign_in()
        self.client.post(f'/admin/lecturers/{self.helper.id}/edit', data={
            'full_name': 'Dr Helper', 'staff_id': 'stf/1', 'department_id': self.dept.id})
        self.assertEqual(db.session.get(Lecturer, self.helper.id).staff_id, 'STF/2')
        self.assertEqual(AuditLog.query.filter_by(action='lecturer.edit').count(), 0)

    # ---- delete -----------------------------------------------------------------

    def test_course_without_sessions_is_deleted_with_its_enrollments(self):
        db.session.add(Enrollment(student_id=self.ada.id, course_id=self.mct.id))
        db.session.commit()
        self.sign_in()
        self.client.post(f'/admin/courses/{self.mct.id}/delete')
        self.assertIsNone(db.session.get(Course, self.mct.id))
        self.assertEqual(Enrollment.query.count(), 0)
        entry = AuditLog.query.filter_by(action='course.delete').one()
        self.assertEqual(entry.details['removed']['enrollments'], 1)

    def test_course_with_a_session_is_kept(self):
        db.session.add(SessionModel(course_id=self.mct.id))
        db.session.commit()
        self.sign_in()
        self.client.post(f'/admin/courses/{self.mct.id}/delete')
        self.assertIsNotNone(db.session.get(Course, self.mct.id))

    def test_coordinator_cannot_be_deleted(self):
        reason = record_edits.delete_blockers('lecturers', [self.lead])[self.lead.id]
        self.assertIn('MCT 401', reason)
        self.sign_in()
        self.client.post(f'/admin/lecturers/{self.lead.id}/delete')
        self.assertIsNotNone(db.session.get(Lecturer, self.lead.id))

    def test_lecturer_who_ran_a_class_cannot_be_deleted(self):
        db.session.add(SessionModel(course_id=self.mct.id, started_by=self.helper.user_id))
        db.session.commit()
        self.assertIn(self.helper.id, record_edits.delete_blockers('lecturers', [self.helper]))

    def test_unused_lecturer_is_deleted_with_login_and_course_links(self):
        user_id = self.helper.user_id
        self.sign_in()
        self.client.post(f'/admin/lecturers/{self.helper.id}/delete')
        self.assertIsNone(db.session.get(Lecturer, self.helper.id))
        self.assertIsNone(db.session.get(User, user_id))
        db.session.expire_all()
        self.assertEqual(db.session.get(Course, self.mct.id).co_lecturers, [])

    def test_student_with_attendance_is_kept(self):
        s = SessionModel(course_id=self.mct.id)
        db.session.add(s)
        db.session.flush()
        db.session.add(Attendance(student_id=self.ada.id, session_id=s.id))
        db.session.commit()
        self.sign_in()
        self.client.post(f'/admin/students/{self.ada.id}/delete')
        self.assertIsNotNone(db.session.get(Student, self.ada.id))

    def test_new_student_is_deleted_with_login(self):
        db.session.add(Enrollment(student_id=self.ada.id, course_id=self.mct.id))
        db.session.commit()
        user_id = self.ada.user_id
        self.sign_in()
        self.client.post(f'/admin/students/{self.ada.id}/delete')
        self.assertIsNone(db.session.get(Student, self.ada.id))
        self.assertIsNone(db.session.get(User, user_id))
        self.assertEqual(Enrollment.query.count(), 0)

    # ---- page cost --------------------------------------------------------------

    def test_blockers_do_not_query_per_row(self):
        def queries_for(records):
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                record_edits.delete_blockers('lecturers', records)
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen)
        for i in range(8):
            self.lecturer(f'L{i}', f'STF/9{i}')
        db.session.commit()
        # Loaded first, as the page does: counting attribute reloads of
        # just-committed rows would measure the test, not the function.
        everyone = Lecturer.query.all()
        self.assertEqual(queries_for(everyone[:1]), queries_for(everyone))


if __name__ == '__main__':
    unittest.main()
