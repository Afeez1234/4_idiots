"""Tests for importing Student Affairs timetable PDFs (timetable_import.py
and the admin routes /admin/timetable/import[/confirm]).

Uses the look-alike sheet from tests/fixtures/timetables/make_sample.py
(invented codes and names), with matching courses created here. Pins:

  * a clean sheet plans to exactly its classes; saving makes DRAFTS;
  * an unknown course code blocks the whole import;
  * the same class on two sheets (a GST course) is saved once;
  * room and lecturer clashes with stored classes block the import --
    co-lecturers included;
  * re-importing replaces earlier drafts but never published classes;
  * drafts are invisible to students until published;
  * the routes: preview saves nothing; confirm re-checks the plan, so a
    changed preview can't sneak past the checks.

Run with:  python tests/test_timetable_import.py
(also collected by pytest if it is installed)
"""

import io
import json
import os
import sys
import unittest
from datetime import date, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures', 'timetables'))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402

import make_sample  # noqa: E402
import timetable_import as ti  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Semester, Timetable,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402
from api.student import api_student_bp  # noqa: E402

SAMPLE_CODES = ['XYZ-SAM101', 'SAM102', 'SAM103', 'GEN201', 'SAM104']


class TimetableImportTestCase(unittest.TestCase):

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
        for bp in (auth_bp, admin_bp, api_student_bp):
            self.app.register_blueprint(bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Examples')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Sample Studies', faculty_id=faculty.id)
        db.session.add(self.dept)
        self.sem = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2026, 6, 1), is_active=True)
        db.session.add(self.sem)
        db.session.flush()
        self.admin = User(username='tunde', password_hash='x', role='admin',
                          is_active=True, requires_password_change=False)
        db.session.add(self.admin)
        db.session.flush()
        self.lect = self.lecturer('Dr A. Example', 'STF/1')
        self.courses = {code: self.course(code, self.lect) for code in SAMPLE_CODES}
        db.session.commit()

    def tearDown(self):
        mock.patch.stopall()
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def lecturer(self, name, staff_id):
        u = User(username=staff_id, password_hash='x', role='lecturer')
        db.session.add(u)
        db.session.flush()
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.dept.id, user_id=u.id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def course(self, code, lecturer):
        c = Course(course_title=f'Course {code}', course_code=code, lecturer_id=lecturer.id,
                   department_id=self.dept.id, semester_id=self.sem.id)
        db.session.add(c)
        db.session.flush()
        return c

    def stored(self, course, day, start, end, room, published=True):
        db.session.add(Timetable(course_id=course.id, semester_id=self.sem.id, day_of_week=day,
                                 start_time=time(start), end_time=time(end), room=room,
                                 is_published=published, created_by=self.admin.id))
        db.session.commit()

    def plan(self, *pdfs):
        files = [(f'sheet{i}.pdf', data) for i, data in enumerate(pdfs or [make_sample.build_pdf()])]
        return ti.plan_sheets(files, self.sem)

    # ---- planning ------------------------------------------------------------

    def test_clean_sheet_plans_to_its_classes(self):
        plan = self.plan()
        self.assertTrue(plan.ok, [s.errors for sh in plan.sheets for s in sh.slots])
        self.assertEqual(len(plan.unique_slots), len(make_sample.EXPECTED))
        self.assertEqual(plan.sheets[0].title, 'Sample Studies · 300 level')

    def test_unknown_course_blocks_the_import(self):
        db.session.delete(self.courses['SAM103'])
        db.session.commit()
        plan = self.plan()
        self.assertFalse(plan.ok)
        bad = [s for s in plan.sheets[0].slots if s.errors]
        self.assertEqual({s.code for s in bad}, {'SAM103'})
        self.assertIn('Create it on the Courses page', bad[0].errors[0])

    def test_same_class_on_two_sheets_is_saved_once(self):
        plan = self.plan(make_sample.build_pdf(), make_sample.build_pdf())
        self.assertTrue(plan.ok)
        self.assertEqual(len(plan.unique_slots), len(make_sample.EXPECTED))
        self.assertTrue(all(s.shared_with for s in plan.sheets[0].slots))

    def test_room_clash_with_a_stored_class(self):
        other = self.course('OTH101', self.lecturer('Dr Other', 'STF/9'))
        self.stored(other, 3, 8, 9, 'LR 2')          # SAM104 is Thu 08:00 in LR 2
        plan = self.plan()
        self.assertFalse(plan.ok)
        [bad] = [s for s in plan.sheets[0].slots if s.errors]
        self.assertEqual(bad.code, 'SAM104')
        self.assertIn('Room LR 2 is also booked by OTH101', bad.errors[0])

    def test_co_lecturer_clash_with_a_stored_class(self):
        busy = self.lecturer('Dr Busy', 'STF/7')
        self.courses['SAM104'].co_lecturers.append(busy)
        other = self.course('OTH102', busy)
        self.stored(other, 3, 8, 9, 'ELSEWHERE')     # Dr Busy is elsewhere Thu 08:00
        plan = self.plan()
        self.assertFalse(plan.ok)
        [bad] = [s for s in plan.sheets[0].slots if s.errors]
        self.assertIn('Dr Busy also teaches OTH102', bad.errors[0])

    # ---- saving ----------------------------------------------------------------

    def test_saved_as_drafts_and_reimport_replaces_only_drafts(self):
        self.stored(self.courses['SAM104'], 4, 9, 10, 'OLD ROOM')   # published, from before
        ti.apply_plan(self.plan(), self.sem, self.admin.id)
        db.session.commit()
        drafts = Timetable.query.filter_by(is_published=False).count()
        self.assertEqual(drafts, len(make_sample.EXPECTED))

        ti.apply_plan(self.plan(), self.sem, self.admin.id)        # import again
        db.session.commit()
        self.assertEqual(Timetable.query.filter_by(is_published=False).count(), drafts)
        # The published SAM104 slot is untouched until publishing.
        self.assertEqual(Timetable.query.filter_by(is_published=True, room='OLD ROOM').count(), 1)

    def test_drafts_are_invisible_to_students(self):
        su = User(username='S/1', password_hash='x', role='student')
        db.session.add(su)
        db.session.flush()
        st = Student(full_name='Ada', matric_number='S/1', level='300',
                     department_id=self.dept.id, user_id=su.id)
        db.session.add(st)
        db.session.flush()
        db.session.add(Enrollment(student_id=st.id, course_id=self.courses['SAM102'].id))
        db.session.commit()
        ti.apply_plan(self.plan(), self.sem, self.admin.id)
        db.session.commit()

        token = create_access_token(identity=str(su.id), additional_claims={'role': 'student'})
        week = lambda: self.client.get('/api/v1/student/schedule/week',  # noqa: E731
                                       headers={'Authorization': f'Bearer {token}'}).get_json()['week']
        self.assertEqual(week(), [])
        Timetable.query.update({Timetable.is_published: True})
        db.session.commit()
        self.assertEqual({e['course_code'] for e in week()}, {'SAM102'})

    # ---- routes -------------------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def test_preview_saves_nothing_and_confirm_saves_drafts(self):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post('/admin/timetable/import', data={
                'semester_id': self.sem.id,
                'files': (io.BytesIO(make_sample.build_pdf()), 'sample.pdf'),
            }, content_type='multipart/form-data')
            kwargs = render.call_args.kwargs
        self.assertTrue(kwargs['plan'].ok)
        self.assertEqual(Timetable.query.count(), 0)            # preview saved nothing

        self.client.post('/admin/timetable/import/confirm', data={
            'semester_id': self.sem.id, 'plan': kwargs['plan_json']})
        self.assertEqual(Timetable.query.filter_by(is_published=False).count(), len(make_sample.EXPECTED))
        self.assertEqual(AuditLog.query.filter_by(action='timetable.import').count(), 1)

    def test_confirm_rechecks_a_changed_preview(self):
        self.sign_in()
        payload = self.plan().to_json()
        payload['sheets'][0]['slots'][0]['code'] = 'NOPE999'     # edited after the preview
        with mock.patch('blueprints.admin.render_template', return_value=''):
            self.client.post('/admin/timetable/import/confirm', data={
                'semester_id': self.sem.id, 'plan': json.dumps(payload)})
        self.assertEqual(Timetable.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
