"""Tests for personal admin logins and the audit trail.

The point of the feature is that several people can share admin access and
every change still has a name on it. So these pin:

  * entries name the signed-in person (not "unknown"),
  * secrets never reach the log, but ordinary fields like a course code do,
  * a temporary password can't be skipped and a disabled account is signed
    out mid-session,
  * real dashboard routes write the entries you'd expect, including how much
    a cascade delete removed,
  * a bad row in a bulk CSV upload no longer silently discards the good rows
    before it,
  * create_admin.py's create/disable rules.

Runs the real blueprints against a throwaway in-memory SQLite database.

Run with:  python tests/test_audit.py
(also collected by pytest if it is installed)
"""

import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# create_admin.py imports app.py, which refuses to start without these. The
# test never touches that app's database -- it swaps in its own below.
for _name in ('SECRET_KEY', 'JWT_SECRET_KEY', 'DB_HOST', 'DB_USER',
              'DB_PASSWORD', 'DB_NAME'):
    os.environ.setdefault(_name, 'test')

from flask import Flask  # noqa: E402
import bcrypt  # noqa: E402

import audit  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Course, Lecturer,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


def _hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(4)).decode()


class AuditTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test',
            TESTING=True,
            WTF_CSRF_ENABLED=False,
            RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(auth_bp)
        self.app.register_blueprint(admin_bp)

        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        # Push needs Firebase; nothing here is about notifications.
        self.push = mock.patch('blueprints.admin.send_push_notification').start()
        # A failed sign-in re-renders the login page. These tests check what
        # gets logged, not the page (render_check.py covers pages), so the
        # login page is stubbed rather than wiring up the template folder.
        mock.patch('blueprints.auth.render_template', return_value='').start()

        self.admin = User(username='tunde', password_hash=_hash('pw'), role='admin',
                          is_active=True, requires_password_change=False)
        db.session.add(self.admin)
        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.commit()
        self.faculty = faculty

        self.client = self.app.test_client()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def sign_in(self, user):
        with self.client.session_transaction() as s:
            s['user_id'] = user.id
            s['username'] = user.username
            s['role'] = user.role

    def entries(self, action=None):
        q = AuditLog.query
        if action:
            q = q.filter_by(action=action)
        return q.order_by(AuditLog.id).all()

    # ---- audit.py itself --------------------------------------------------

    def test_entry_names_the_signed_in_person(self):
        with self.app.test_request_context('/'):
            from flask import session
            session['user_id'] = self.admin.id
            session['username'] = 'tunde'
            session['role'] = 'admin'
            audit.log_action('thing.do', 'Did a thing')
            db.session.commit()
        entry = self.entries('thing.do')[0]
        self.assertEqual(entry.actor_label, 'tunde')
        self.assertEqual(entry.actor_id, self.admin.id)
        self.assertEqual(entry.actor_role, 'admin')

    def test_secrets_are_scrubbed_but_course_codes_are_kept(self):
        audit.log_action('x.y', 's', details={
            'password': 'hunter2', 'nested': {'refresh_token': 't'},
            'code': 'MCT 401',
        }, actor=(None, 'cli', 'system'))
        db.session.commit()
        details = self.entries('x.y')[0].details
        self.assertEqual(details['password'], '[redacted]')
        self.assertEqual(details['nested']['refresh_token'], '[redacted]')
        self.assertEqual(details['code'], 'MCT 401')

    def test_ip_is_the_entry_the_proxy_added(self):
        # The first X-Forwarded-For entry is whatever the client sent; the
        # last is what Render's proxy saw.
        with self.app.test_request_context(
                '/', headers={'X-Forwarded-For': '6.6.6.6, 41.58.1.2'}):
            self.assertEqual(audit._client_ip(), '41.58.1.2')

    # ---- account-state enforcement -----------------------------------------

    def test_temporary_password_cannot_be_skipped(self):
        self.admin.requires_password_change = True
        db.session.commit()
        self.sign_in(self.admin)
        resp = self.client.get('/admin/activity')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/change-password', resp.headers['Location'])

    def test_disabled_account_is_signed_out_mid_session(self):
        self.sign_in(self.admin)
        self.admin.is_active = False
        db.session.commit()
        resp = self.client.get('/admin/activity')
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login', resp.headers['Location'])
        with self.client.session_transaction() as s:
            self.assertNotIn('user_id', s)

    # ---- sign-in entries ----------------------------------------------------

    def test_admin_sign_in_and_failed_attempt_are_logged(self):
        self.client.post('/login', data={'username': 'tunde', 'password': 'wrong'})
        self.client.post('/login', data={'username': 'tunde', 'password': 'pw'})
        self.assertEqual(len(self.entries('auth.login_failed')), 1)
        self.assertEqual(self.entries('auth.login')[0].actor_label, 'tunde')

    def test_student_sign_ins_are_not_logged(self):
        student_user = User(username='MCT/19/0001', password_hash=_hash('pw'),
                            role='student', requires_password_change=False)
        db.session.add(student_user)
        db.session.commit()
        self.client.post('/login', data={'username': 'MCT/19/0001', 'password': 'nope'})
        self.assertEqual(self.entries(), [])

    # ---- dashboard routes -----------------------------------------------------

    def test_creating_a_student_is_logged_with_who_did_it(self):
        self.sign_in(self.admin)
        self.client.post('/admin/students', data={
            'full_name': 'Ada Obi', 'matric_number': 'MCT/19/0001',
            'level': '400', 'department_id': self.dept.id,
        })
        entry = self.entries('student.create')[0]
        self.assertEqual(entry.actor_label, 'tunde')
        self.assertIn('Ada Obi', entry.summary)

    def test_department_delete_records_what_the_cascade_removed(self):
        user = User(username='MCT/19/0002', password_hash='x', role='student')
        db.session.add(user)
        db.session.flush()
        db.session.add(Student(full_name='Bayo', matric_number='MCT/19/0002',
                               level='400', department_id=self.dept.id, user_id=user.id))
        db.session.commit()

        self.sign_in(self.admin)
        self.client.post(f'/admin/departments/{self.dept.id}/delete')
        entry = self.entries('department.delete')[0]
        self.assertEqual(entry.details['removed']['students'], 1)
        self.assertIn('1 student', entry.summary)

    def test_failed_change_leaves_no_entry(self):
        # Duplicate faculty name: the commit fails, and its log entry must
        # be rolled back with it -- a log claiming a change that didn't
        # happen is worse than no log.
        self.sign_in(self.admin)
        self.client.post('/admin/organization', data={'action': 'add_faculty', 'name': 'Engineering'})
        self.assertEqual(self.entries('faculty.create'), [])

    def test_bad_csv_row_does_not_discard_the_rows_before_it(self):
        self.sign_in(self.admin)
        csv_text = (
            'matric_number,full_name,level,department_name,rfid_uid\n'
            'MCT/19/0010,First,400,Mechatronics,AAA\n'
            'MCT/19/0011,Second,400,Mechatronics,AAA\n'   # duplicate RFID: fails
            'MCT/19/0012,Third,400,Mechatronics,\n'
        )
        self.client.post('/admin/students/bulk-enroll', data={
            'file': (io.BytesIO(csv_text.encode()), 'students.csv'),
        }, content_type='multipart/form-data')

        saved = {s.matric_number for s in Student.query.all()}
        self.assertEqual(saved, {'MCT/19/0010', 'MCT/19/0012'})
        entry = self.entries('student.bulk_import')[0]
        self.assertEqual(entry.details['created'], 2)
        self.assertEqual(entry.details['skipped'], 1)

    # ---- bulk upload speed and rules -------------------------------------------

    def upload(self, csv_text):
        self.sign_in(self.admin)
        return self.client.post('/admin/students/bulk-enroll', data={
            'file': (io.BytesIO(csv_text.encode()), 'students.csv'),
        }, content_type='multipart/form-data')

    @staticmethod
    def csv_rows(start, count):
        header = 'matric_number,full_name,level,department_name\n'
        return header + ''.join(
            f'MCT/20/{n:04d},Student {n},300,Mechatronics\n'
            for n in range(start, start + count))

    def count_statements(self, fn):
        """Database statements issued while fn runs. An executemany (one
        multi-row INSERT) counts once -- it's one round trip."""
        from sqlalchemy import event
        count = [0]

        def on_execute(*_args, **_kwargs):
            count[0] += 1
        event.listen(db.engine, 'before_cursor_execute', on_execute)
        try:
            fn()
        finally:
            event.remove(db.engine, 'before_cursor_execute', on_execute)
        return count[0]

    def test_upload_round_trips_do_not_grow_with_the_file(self):
        # The 502: ~6 round trips + a full-cost hash PER ROW made uploads
        # past ~10 students outlive Render's 30s request limit.
        small = self.count_statements(lambda: self.upload(self.csv_rows(0, 20)))
        large = self.count_statements(lambda: self.upload(self.csv_rows(100, 200)))
        self.assertEqual(Student.query.count(), 220)
        self.assertEqual(small, large)

    def test_uploaded_students_sign_in_with_their_matric_number(self):
        self.upload(self.csv_rows(0, 1))
        user = User.query.filter_by(username='MCT/20/0000').one()
        self.assertTrue(bcrypt.checkpw(b'MCT/20/0000', user.password_hash.encode()))
        self.assertTrue(user.requires_password_change)
        self.assertEqual(user.role, 'student')

    def test_existing_and_repeated_matric_numbers_are_skipped(self):
        self.upload(self.csv_rows(0, 1))                      # MCT/20/0000 now exists
        self.upload(
            'matric_number,full_name,level,department_name\n'
            'MCT/20/0000,Already Here,300,Mechatronics\n'
            'MCT/20/0001,New,300,Mechatronics\n'
            'mct/20/0001,Same Again Lowercase,300,Mechatronics\n'
            'MCT/20/0002,Bad Dept,300,Underwater Basketry\n'
        )
        self.assertEqual(
            {s.matric_number for s in Student.query.all()},
            {'MCT/20/0000', 'MCT/20/0001'},
        )
        entry = self.entries('student.bulk_import')[-1]
        self.assertEqual((entry.details['created'], entry.details['skipped']), (1, 3))

    def test_oversized_upload_is_refused_and_saves_nothing(self):
        from blueprints.admin import BULK_UPLOAD_MAX_ROWS
        self.upload(self.csv_rows(0, BULK_UPLOAD_MAX_ROWS + 1))
        self.assertEqual(Student.query.count(), 0)

    def test_enrol_by_matric_number(self):
        # Finding 11: the enrol form takes a matric number instead of a
        # dropdown of every student.
        user = User(username='MCT/19/0099', password_hash='x', role='student')
        db.session.add(user)
        db.session.flush()
        student = Student(full_name='Ola', matric_number='MCT/19/0099', level='400',
                          department_id=self.dept.id, user_id=user.id)
        lect_user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add_all([student, lect_user])
        db.session.flush()
        lecturer = Lecturer(full_name='Dr Ade', staff_id='S1', department_id=self.dept.id,
                            user_id=lect_user.id)
        db.session.add(lecturer)
        db.session.flush()
        course = Course(course_title='Control', course_code='MCT 401',
                        lecturer_id=lecturer.id, department_id=self.dept.id)
        db.session.add(course)
        db.session.commit()

        self.sign_in(self.admin)
        self.client.post('/admin/courses', data={
            'action': 'enroll_student', 'matric_number': 'mct/19/9999', 'course_id': course.id})
        self.assertEqual(self.entries('enrollment.create'), [])   # unknown matric
        self.client.post('/admin/courses', data={
            'action': 'enroll_student', 'matric_number': ' mct/19/0099 ', 'course_id': course.id})
        self.assertEqual([c.id for c in db.session.get(Student, student.id).courses], [course.id])
        self.assertIn('MCT/19/0099', self.entries('enrollment.create')[0].summary)

    def test_activity_filters_by_person(self):
        audit.log_action('a.b', 'one', actor=(1, 'tunde', 'admin'))
        audit.log_action('a.b', 'two', actor=(2, 'amaka', 'admin'))
        db.session.commit()
        self.sign_in(self.admin)
        with mock.patch('blueprints.admin.render_template') as render:
            render.return_value = ''
            self.client.get('/admin/activity?who=amaka')
            entries = render.call_args.kwargs['entries']
        self.assertEqual([e.summary for e, _tone in entries], ['two'])

    # ---- create_admin.py --------------------------------------------------------

    def test_create_admin_requires_a_password_change(self):
        import create_admin
        with mock.patch.object(create_admin, 'app', self.app), \
                mock.patch('builtins.print'):
            create_admin.create('amaka')
        user = User.query.filter_by(username='amaka').one()
        self.assertEqual(user.role, 'admin')
        self.assertTrue(user.requires_password_change)
        self.assertTrue(self.entries('admin.create')[0].actor_label.startswith('cli:'))

    def test_cannot_disable_the_last_active_admin(self):
        import create_admin
        with mock.patch.object(create_admin, 'app', self.app), \
                self.assertRaises(SystemExit):
            create_admin.disable('tunde')
        self.assertTrue(db.session.get(User, self.admin.id).is_active)

    def test_disable_keeps_the_account_and_logs_it(self):
        import create_admin
        db.session.add(User(username='amaka', password_hash='x', role='admin', is_active=True))
        db.session.commit()
        with mock.patch.object(create_admin, 'app', self.app), \
                mock.patch('builtins.print'):
            create_admin.disable('tunde')
        user = db.session.get(User, self.admin.id)
        self.assertFalse(user.is_active)
        self.assertEqual(len(self.entries('admin.disable')), 1)


if __name__ == '__main__':
    unittest.main()
