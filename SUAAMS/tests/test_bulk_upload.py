"""Tests for the lecturer and course CSV uploads (bulk_upload.py and the
admin routes /admin/bulk/<kind>, /admin/bulk/confirm).

Pins:

  * Excel's UTF-8 byte-order mark and header spellings (department_name)
    are accepted; a missing column or an oversized file is refused whole;
  * a row that already exists is skipped, never an error and never changed,
    so re-uploading a file is harmless;
  * any row error blocks the whole file;
  * a staff ID that is another account's login, an unknown department or
    an unknown lecturer are errors; a duplicate inside the file too;
  * courses: first staff ID is the coordinator, the rest co-lecturers; a
    blank department makes a general course;
  * the routes: the upload saves nothing; confirm re-checks and saves, with
    one audit entry; lecturers can sign in with their staff ID.

Run with:  python tests/test_bulk_upload.py
(also collected by pytest if it is installed)
"""

import json
import os
import sys
import unittest
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt  # noqa: E402
from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager  # noqa: E402

import bulk_upload as bu  # noqa: E402
from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, AuditLog, Faculty, Department, User, Lecturer, Course, Semester,
)
from blueprints.auth import auth_bp  # noqa: E402
from blueprints.admin import admin_bp  # noqa: E402


def csv_bytes(*lines, bom=False):
    return (('﻿' if bom else '') + '\n'.join(lines) + '\n').encode('utf-8')


class BulkUploadTestCase(unittest.TestCase):

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
        self.mct = Department(name='Mechatronics Engineering', faculty_id=faculty.id)
        self.sem = Semester(name='2025/2026 Second Semester', start_date=date(2026, 1, 1),
                            end_date=date(2026, 6, 1), is_active=True)
        db.session.add_all([self.mct, self.sem])
        db.session.flush()
        self.admin = User(username='tunde', password_hash='x', role='admin',
                          is_active=True, requires_password_change=False)
        student_user = User(username='MCT/20/0001', password_hash='x', role='student')
        db.session.add_all([self.admin, student_user])
        db.session.flush()
        self.old = self.lecturer('STF/0001', 'Dr Existing')
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def lecturer(self, staff_id, name):
        u = User(username=staff_id, password_hash='x', role='lecturer')
        db.session.add(u)
        db.session.flush()
        lect = Lecturer(full_name=name, staff_id=staff_id, department_id=self.mct.id, user_id=u.id)
        db.session.add(lect)
        db.session.flush()
        return lect

    def lecturer_plan(self, *lines, **kw):
        return bu.plan_lecturers(bu.read_csv(csv_bytes(*lines, **kw), 'lecturers'), 'l.csv')

    def course_plan(self, *lines):
        return bu.plan_courses(bu.read_csv(csv_bytes(*lines), 'courses'), 'c.csv', self.sem)

    # ---- reading ---------------------------------------------------------------

    def test_excel_bom_and_header_aliases(self):
        plan = self.lecturer_plan('Staff_ID,Full Name,department_name',
                                  'STF/0002,Dr New,Mechatronics Engineering', bom=True)
        self.assertTrue(plan.ok)
        self.assertEqual(plan.rows[0].values['staff_id'], 'STF/0002')

    def test_missing_column_is_refused(self):
        with self.assertRaises(bu.BulkCsvError):
            bu.read_csv(csv_bytes('staff_id,full_name', 'STF/2,Dr X'), 'lecturers')

    def test_too_many_rows_is_refused(self):
        lines = ['staff_id,full_name,department'] + [f'S{i},N,Mechatronics Engineering'
                                                    for i in range(bu.MAX_ROWS + 1)]
        with self.assertRaises(bu.BulkCsvError):
            bu.read_csv(csv_bytes(*lines), 'lecturers')

    # ---- lecturers ---------------------------------------------------------------

    def test_lecturer_rows(self):
        plan = self.lecturer_plan(
            'staff_id,full_name,department',
            'STF/0002,Dr New,mechatronics engineering',     # department name, any case
            'stf/0001,Dr Existing,Mechatronics Engineering',  # exists (any case): skipped
            'MCT/20/0001,Dr Clash,Mechatronics Engineering',  # a student's login
            'STF/0003,Dr Nowhere,Basket Weaving',
            'STF/0002,Dr Twice,Mechatronics Engineering',
        )
        self.assertEqual([r.status for r in plan.rows], ['new', 'exists', 'error', 'error', 'error'])
        self.assertIn("another account's login", plan.rows[2].errors[0])
        self.assertIn('No department', plan.rows[3].errors[0])
        self.assertIn('also on line 2', plan.rows[4].errors[0])
        self.assertFalse(plan.ok)
        with self.assertRaises(ValueError):
            bu.apply_lecturers(plan)

    def test_lecturers_saved_and_can_sign_in(self):
        plan = self.lecturer_plan('staff_id,full_name,department',
                                  'STF/0002,Dr New,Mechatronics Engineering',
                                  'STF/0001,Dr Existing Renamed,Mechatronics Engineering')
        self.assertEqual(bu.apply_lecturers(plan), 1)
        db.session.commit()
        new = Lecturer.query.filter_by(staff_id='STF/0002').one()
        self.assertTrue(new.user.requires_password_change)
        self.assertTrue(bcrypt.checkpw(b'STF/0002', new.user.password_hash.encode()))
        self.assertEqual(db.session.get(Lecturer, self.old.id).full_name, 'Dr Existing')   # unchanged

    # ---- courses -------------------------------------------------------------------

    def test_course_rows_and_saving(self):
        co = self.lecturer('STF/0007', 'Dr Co')
        db.session.add(Course(course_code='MCT403', course_title='Old', lecturer_id=self.old.id,
                              department_id=self.mct.id, semester_id=self.sem.id))
        db.session.commit()
        plan = self.course_plan(
            'course_code,course_title,department,credit_units,lecturers',
            'mct401,Control Systems,Mechatronics Engineering,3,STF/0001; stf/0007',
            'GST 212,Philosophy and Logic,,2,STF/0007',
            'MCT 403,Renamed,Mechatronics Engineering,3,STF/0001',     # exists: skipped
        )
        self.assertTrue(plan.ok, [r.errors for r in plan.rows])
        self.assertEqual([r.status for r in plan.rows], ['new', 'new', 'exists'])
        self.assertEqual(bu.apply_courses(plan, self.sem), 2)
        db.session.commit()

        mct401 = Course.query.filter_by(course_code='MCT401').one()
        self.assertEqual(mct401.lecturer_id, self.old.id)                # coordinator first
        self.assertEqual([l.id for l in mct401.co_lecturers], [co.id])
        self.assertEqual(mct401.credit_units, 3)
        gst = Course.query.filter_by(course_code='GST 212').one()
        self.assertIsNone(gst.department_id)                             # general course
        self.assertEqual(Course.query.filter_by(course_code='MCT403').one().course_title, 'Old')

    def test_course_errors(self):
        plan = self.course_plan(
            'course_code,course_title,department,credit_units,lecturers',
            'MCT401,A,Mechatronics Engineering,3,STF/9999',
            'MCT402,B,Mechatronics Engineering,eleven,STF/0001',
            'MCT404,C,Nowhere,3,STF/0001',
            'MCT405,D,Mechatronics Engineering,3,',
        )
        self.assertEqual([r.status for r in plan.rows], ['error'] * 4)
        self.assertIn('No lecturer with staff ID STF/9999', plan.rows[0].errors[0])
        self.assertIn('credit_units', plan.rows[1].errors[0])
        self.assertIn('lecturers is empty', plan.rows[3].errors[0])

    # ---- routes ----------------------------------------------------------------------

    def sign_in(self):
        with self.client.session_transaction() as s:
            s['user_id'], s['username'], s['role'] = self.admin.id, 'tunde', 'admin'

    def upload(self, kind, data, **form):
        self.sign_in()
        with mock.patch('blueprints.admin.render_template', return_value='') as render:
            self.client.post(f'/admin/bulk/{kind}', data={'file': (__import__('io').BytesIO(data), 'x.csv'), **form},
                             content_type='multipart/form-data')
        return render.call_args.kwargs if render.called else None

    def test_upload_previews_then_confirm_saves(self):
        kwargs = self.upload('lecturers', csv_bytes('staff_id,full_name,department',
                                                   'STF/0002,Dr New,Mechatronics Engineering'))
        self.assertTrue(kwargs['plan'].ok)
        self.assertEqual(Lecturer.query.count(), 1)                     # preview saved nothing

        self.client.post('/admin/bulk/confirm', data={'plan': kwargs['plan_json']})
        self.assertEqual(Lecturer.query.count(), 2)
        self.assertEqual(AuditLog.query.filter_by(action='lecturer.bulk_import').count(), 1)

        # Confirming the same preview again creates nothing new.
        self.client.post('/admin/bulk/confirm', data={'plan': kwargs['plan_json']})
        self.assertEqual(Lecturer.query.count(), 2)

    def test_confirm_rechecks_an_edited_preview(self):
        kwargs = self.upload('courses', csv_bytes('course_code,course_title,lecturers', 'MCT401,A,STF/0001'),
                             semester_id=self.sem.id)
        payload = json.loads(kwargs['plan_json'])
        payload['rows'][0]['lecturers'] = 'STF/NOPE'                    # edited after the preview
        with mock.patch('blueprints.admin.render_template', return_value=''):
            self.client.post('/admin/bulk/confirm', data={'plan': json.dumps(payload)})
        self.assertEqual(Course.query.count(), 0)

    def test_courses_need_a_semester(self):
        self.assertIsNone(self.upload('courses', csv_bytes('course_code,course_title,lecturers',
                                                           'MCT401,A,STF/0001')))
        self.assertEqual(Course.query.count(), 0)

    # ---- Excel workbooks (2026-10-19) -----------------------------------------------------
    # read_upload takes an .xlsx as it is, so nobody has to "Save As CSV
    # UTF-8" -- which older Excel doesn't even offer.

    def test_xlsx_is_read_like_a_csv_and_keeps_every_letter(self):
        data = xlsx_bytes(['staff_id', 'full_name', 'Department Name'],      # header spelling varies
                          [1001, 'Dr Adéwálé Ògúnlẹ́yẹ̀', 'Mechatronics Engineering'],
                          [None, None, None],                                 # a blank row is skipped
                          ['STF/0002', '  Dr   Spaced  ', 'Mechatronics Engineering'])
        rows = bu.read_upload(data, 'Lecturers.XLSX', 'lecturers')
        self.assertEqual([(r.line, r.values['staff_id'], r.values['full_name']) for r in rows],
                         [(2, '1001', 'Dr Adéwálé Ògúnlẹ́yẹ̀'),          # a whole number loses ".0"
                          (4, 'STF/0002', 'Dr Spaced')])                  # line = the spreadsheet row
        self.assertTrue(bu.plan_lecturers(rows, 'Lecturers.xlsx').ok)

    def test_an_xlsx_is_recognised_by_its_content_too(self):
        data = xlsx_bytes(['staff_id', 'full_name', 'department'], ['STF/0009', 'Dr X', 'Mechatronics Engineering'])
        self.assertEqual(bu.read_upload(data, 'renamed.csv', 'lecturers')[0].values['staff_id'], 'STF/0009')

    def test_old_xls_and_broken_workbooks_are_refused_with_a_reason(self):
        with self.assertRaisesRegex(bu.BulkCsvError, r'\.xls'):
            bu.read_upload(b'\xd0\xcf\x11\xe0 old binary', 'old.xls', 'lecturers')
        with self.assertRaisesRegex(bu.BulkCsvError, 'readable Excel workbook'):
            bu.read_upload(b'PK\x03\x04 not really a workbook', 'broken.xlsx', 'lecturers')

    def test_a_huge_sheet_is_refused_without_reading_it_all(self):
        rows = [['STF/%05d' % i, 'Dr %d' % i, 'Mechatronics Engineering'] for i in range(bu.MAX_ROWS + 1)]
        with self.assertRaisesRegex(bu.BulkCsvError, 'more than'):
            bu.read_upload(xlsx_bytes(['staff_id', 'full_name', 'department'], *rows), 'big.xlsx', 'lecturers')

    def test_xlsx_upload_previews_then_saves(self):
        data = xlsx_bytes(['staff_id', 'full_name', 'department'],
                          ['STF/0003', 'Dr Ọlá Ẹ̀mí', 'Mechatronics Engineering'])
        kwargs = self.upload('lecturers', data)
        self.assertTrue(kwargs['plan'].ok)
        self.client.post('/admin/bulk/confirm', data={'plan': kwargs['plan_json']})
        self.assertEqual(Lecturer.query.filter_by(staff_id='STF/0003').one().full_name, 'Dr Ọlá Ẹ̀mí')


def xlsx_bytes(header, *rows):
    """An in-memory Excel workbook: one sheet, a header row, then rows."""
    from openpyxl import Workbook
    book = Workbook()
    sheet = book.active
    sheet.append(header)
    for row in rows:
        sheet.append(row)
    buffer = __import__('io').BytesIO()
    book.save(buffer)
    return buffer.getvalue()


if __name__ == '__main__':
    unittest.main()
