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
  * delete_blockers answers for a whole page in a fixed number of queries;
  * "Reset password" sets a random one-time password (flashed, never
    logged), forces a change, signs the app out and leaves the phone bound;
  * HODs: an edit is copied to a promoted lecturer's Lecturer row (and the
    reverse); one HOD per department; "remove as HOD" sends a promoted
    lecturer back to teaching, deletes a direct HOD with nothing on record,
    and switches off one with a record; a lecturer who is HOD can't be
    deleted from the Lecturers page.

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
    db, Announcement, Attendance, AuditLog, Course, Department, Enrollment, Faculty, HOD, Lecturer,
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

    def hod(self, name, staff_id, dept, user=None):
        h = HOD(full_name=name, staff_id=staff_id, department_id=dept.id,
                user_id=(user or self.user(staff_id, 'hod')).id)
        db.session.add(h)
        db.session.flush()
        return h

    def promote(self, lecturer, dept):
        lecturer.user.role = 'hod'
        return self.hod(lecturer.full_name, lecturer.staff_id, dept, user=lecturer.user)

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

    # ---- password reset (2026-10-23 audit, finding 5) ---------------------------

    def reset(self, kind, record):
        self.sign_in()
        self.client.post(f'/admin/{kind}/{record.id}/reset-password')
        with self.client.session_transaction() as s:
            message = s['_flashes'][-1][1]
        return message.split(': ', 1)[1].split(' ', 1)[0]     # the password in the flash

    def test_reset_gives_a_one_time_password_and_keeps_the_phone(self):
        user = self.ada.user
        user.requires_password_change = False
        user.current_refresh_jti = 'old-session'
        self.ada.device_id = 'phone-1'
        db.session.commit()
        temp = self.reset('students', self.ada)
        self.assertEqual(len(temp), 10)
        self.assertTrue(self.password_is(user, temp))
        self.assertFalse(self.password_is(user, 'MCT/20/0001'))
        self.assertTrue(user.requires_password_change)         # must choose their own
        self.assertIsNone(user.current_refresh_jti)            # app signed out
        self.assertEqual(self.ada.device_id, 'phone-1')        # unbinding is separate
        entry = AuditLog.query.filter_by(action='student.password_reset').one()
        self.assertNotIn(temp, entry.summary + str(entry.details))

    def test_lecturer_reset_and_two_resets_differ(self):
        first = self.reset('lecturers', self.helper)
        second = self.reset('lecturers', self.helper)
        self.assertNotEqual(first, second)
        self.assertTrue(self.password_is(self.helper.user, second))
        self.assertFalse(self.password_is(self.helper.user, first))

    def test_reset_is_only_for_students_and_lecturers(self):
        self.sign_in()
        before = self.mct.course_title
        resp = self.client.post(f'/admin/courses/{self.mct.id}/reset-password')
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(db.session.get(Course, self.mct.id).course_title, before)
        self.assertEqual(AuditLog.query.filter(AuditLog.action.like('%password_reset')).count(), 0)

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

    # ---- HODs -------------------------------------------------------------------

    def test_editing_a_promoted_hod_fixes_their_lecturer_record_too(self):
        h = self.promote(self.helper, self.other_dept)
        db.session.commit()
        self.sign_in()
        self.client.post(f'/admin/hods/{h.id}/edit', data={
            'full_name': 'Dr Helper', 'staff_id': 'STF/22', 'department_id': self.other_dept.id})
        lect = db.session.get(Lecturer, self.helper.id)
        self.assertEqual((lect.full_name, lect.staff_id, lect.user.username),
                         ('Dr Helper', 'STF/22', 'STF/22'))
        self.assertEqual(lect.department_id, self.dept.id)      # teaching dept untouched

    def test_editing_the_lecturer_fixes_their_hod_record_too(self):
        h = self.promote(self.helper, self.other_dept)
        db.session.commit()
        record_edits.edit_lecturer(self.helper, {'full_name': 'Dr Helper', 'staff_id': 'STF/2',
                                                 'department_id': self.dept.id})
        self.assertEqual(h.full_name, 'Dr Helper')

    def test_one_hod_per_department(self):
        first = self.hod('Prof A', 'HOD/1', self.dept)
        second = self.hod('Prof B', 'HOD/2', self.other_dept)
        db.session.commit()
        with self.assertRaises(record_edits.EditError):
            record_edits.edit_hod(second, {'full_name': 'Prof B', 'staff_id': 'HOD/2',
                                           'department_id': self.dept.id})
        self.assertEqual(first.department_id, self.dept.id)

    def test_removing_a_promoted_hod_leaves_the_lecturer(self):
        h = self.promote(self.helper, self.other_dept)
        db.session.commit()
        self.sign_in()
        self.client.post(f'/admin/hods/{h.id}/delete')
        self.assertEqual(HOD.query.count(), 0)
        lect = db.session.get(Lecturer, self.helper.id)
        self.assertEqual((lect.user.role, lect.user.is_active), ('lecturer', True))
        self.assertEqual(AuditLog.query.filter_by(action='hod.remove').one().details['outcome'], 'lecturer')

    def test_removing_a_direct_hod_deletes_the_account(self):
        h = self.hod('Prof A', 'HOD/1', self.dept)
        db.session.commit()
        user_id = h.user_id
        self.sign_in()
        self.client.post(f'/admin/hods/{h.id}/delete')
        self.assertEqual(HOD.query.count(), 0)
        self.assertIsNone(db.session.get(User, user_id))

    def test_a_direct_hod_with_a_record_is_switched_off_not_deleted(self):
        h = self.hod('Prof A', 'HOD/1', self.dept)
        db.session.add(Announcement(title='Hi', body='x', scope='university', sender_id=h.user_id))
        db.session.commit()
        user_id = h.user_id
        self.sign_in()
        self.client.post(f'/admin/hods/{h.id}/delete')
        self.assertEqual(HOD.query.count(), 0)
        user = db.session.get(User, user_id)
        self.assertFalse(user.is_active)
        self.assertEqual(Announcement.query.one().sender_id, user_id)

    def test_a_lecturer_who_is_hod_cannot_be_deleted_from_lecturers(self):
        self.promote(self.helper, self.other_dept)
        db.session.commit()
        reason = record_edits.delete_blockers('lecturers', [self.helper])[self.helper.id]
        self.assertIn('HOD of Computer', reason)


if __name__ == '__main__':
    unittest.main()
