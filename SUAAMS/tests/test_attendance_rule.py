"""Tests for the one attendance rule (utils.held_sessions, attended_by_*,
course_attendance) and the pages that now share it.

Until 2026-10-15 eight places computed an attendance percentage with three
different rules, so a student could see one number in the app, their HOD
another and their lecturer's register a third. Pins:

  * a class counts as held only once it has finished -- a running class
    doesn't pull anyone down before they've had the chance to tap in;
  * present and late count as attended; excused and absent don't;
  * the student app, the HOD pages, a course's average and the register
    CSV agree for the same student;
  * the admin Reports table runs a fixed number of queries, however many
    courses there are (it used to run three per course).

Run with:  python tests/test_attendance_rule.py
(also collected by pytest if it is installed)
"""

import csv
import io
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

import utils  # noqa: E402
from blueprints import hod  # noqa: E402
from models import (  # noqa: E402
    db, Attendance, Course, Department, Enrollment, Faculty, Lecturer,
    Session as SessionModel, Student, User,
)


class AttendanceRuleTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI='sqlite:///:memory:', TESTING=True)
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.flush()
        u = self.user('STF/1')
        self.lect = Lecturer(full_name='Dr Lead', staff_id='STF/1', department_id=self.dept.id, user_id=u.id)
        db.session.add(self.lect)
        db.session.flush()
        self.course = self.make_course('MCT 401')
        self.ada = self.student('ADA')
        self.bayo = self.student('BAYO')

        # Four finished classes and one running now. Ada: present, late,
        # excused, absent (no row) -> 2 of 4 = 50%. Bayo: present at all four
        # finished classes, and already tapped into the running one.
        done = [self.session(i) for i in range(4)]
        self.live = self.session(4, active=True)
        self.mark(self.ada, done[0], 'present')
        self.mark(self.ada, done[1], 'late')
        self.mark(self.ada, done[2], 'excused')
        for s in done + [self.live]:
            self.mark(self.bayo, s, 'present')
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    # ---- fixtures -----------------------------------------------------------------

    def user(self, username):
        u = User(username=username, password_hash='x', role='student')
        db.session.add(u)
        db.session.flush()
        return u

    def make_course(self, code):
        c = Course(course_code=code, course_title=code, lecturer_id=self.lect.id, department_id=self.dept.id)
        db.session.add(c)
        db.session.flush()
        return c

    def student(self, matric, course=None):
        st = Student(full_name=matric, matric_number=matric, level='400', department_id=self.dept.id,
                     user_id=self.user(matric).id)
        db.session.add(st)
        db.session.flush()
        db.session.add(Enrollment(student_id=st.id, course_id=(course or self.course).id))
        db.session.flush()
        return st

    def session(self, week, active=False, course=None):
        s = SessionModel(course_id=(course or self.course).id, session_date=date(2026, 9, 7) + timedelta(weeks=week),
                         is_active=active)
        db.session.add(s)
        db.session.flush()
        return s

    def mark(self, student, session, status):
        db.session.add(Attendance(student_id=student.id, session_id=session.id, status=status))
        db.session.flush()

    def student_pct(self, student):
        [row] = utils.student_course_attendance(student)
        return row['attended'], row['total'], row['pct']

    # ---- the rule -----------------------------------------------------------------

    def test_running_class_is_not_held_and_excused_is_not_attended(self):
        self.assertEqual(self.student_pct(self.ada), (2, 4, 50.0))
        # Bayo's tap into the running class doesn't count until it ends.
        self.assertEqual(self.student_pct(self.bayo), (4, 4, 100.0))

    def test_course_average(self):
        # (2 + 4) attended of 4 classes x 2 students.
        self.assertEqual(utils.course_attendance([self.course.id])[self.course.id],
                         {'enrolled': 2, 'held': 4, 'attended': 6, 'pct': 75.0})

    def test_student_app_hod_and_register_agree(self):
        app_pct = self.student_pct(self.ada)[2]
        overall, per_course = hod._department_attendance([self.course])[self.ada.id]
        self.assertEqual((overall, per_course[0]['pct']), (round(app_pct), round(app_pct)))
        register = list(csv.reader(io.StringIO(utils.build_course_register_csv(self.course))))
        ada_row = next(r for r in register if len(r) > 2 and r[1] == 'ADA')
        self.assertEqual(float(ada_row[-2]), app_pct)          # Attendance (%)
        self.assertEqual(ada_row[-1], 'NO')                     # below 75%: not eligible

    # ---- page cost ----------------------------------------------------------------

    def test_reports_queries_do_not_grow_with_courses(self):
        from blueprints.admin import _all_course_attendance_reports

        def queries():
            seen = []
            listener = lambda *a: seen.append(1)    # noqa: E731
            event.listen(db.engine, 'before_cursor_execute', listener)
            try:
                rows = _all_course_attendance_reports()
            finally:
                event.remove(db.engine, 'before_cursor_execute', listener)
            return len(seen), rows

        few, _ = queries()
        for i in range(8):
            c = self.make_course(f'X{i}')
            st = self.student(f'S{i}', course=c)
            self.mark(st, self.session(0, course=c), 'present')
        db.session.commit()
        db.session.expire_all()
        many, rows = queries()
        self.assertEqual(few, many)
        self.assertEqual(next(r for r in rows if r['course'].course_code == 'MCT 401')['average_attendance'], 75.0)


if __name__ == '__main__':
    unittest.main()
