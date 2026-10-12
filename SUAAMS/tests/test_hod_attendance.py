"""Tests for the HOD pages' department-wide attendance calculation.

blueprints/hod._department_attendance replaced a per-student version that
ran three queries per course for every student -- ~10,000 queries on one
HOD dashboard load for a 500-student department. These pin:

  * the numbers are identical to the old per-student calculation (kept
    below as the reference) on randomised data,
  * the number of queries does not grow with the number of students.

Run with:  python tests/test_hod_attendance.py
(also collected by pytest if it is installed)
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from sqlalchemy import event  # noqa: E402

from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance,
)
from blueprints.hod import _department_attendance  # noqa: E402


def old_student_attendance(student, course_ids):
    """The previous per-student implementation, verbatim apart from the
    name -- the reference the new one must match."""
    enrolled_ids = {c.id for c in student.courses} & set(course_ids)
    per_course = []
    total_sessions = 0
    total_attended = 0
    for course_id in enrolled_ids:
        course = Course.query.get(course_id)
        session_count = SessionModel.query.filter_by(course_id=course_id).count()
        if session_count == 0:
            continue
        attended = Attendance.query.join(SessionModel).filter(
            Attendance.student_id == student.id,
            SessionModel.course_id == course_id,
            Attendance.status.in_(['present', 'late']),
        ).count()
        pct = round(attended / session_count * 100)
        per_course.append({'code': course.course_code, 'title': course.course_title, 'pct': pct})
        total_sessions += session_count
        total_attended += attended
    overall = round(total_attended / total_sessions * 100) if total_sessions else None
    per_course.sort(key=lambda c: c['code'])
    return overall, per_course


class HodAttendanceTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(self.app)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()

        self.setUp_rows()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def build_department(self, n_students, rng):
        courses = []
        for n in range(5):
            c = Course(course_title=f'Course {n}', course_code=f'MCT 40{n}',
                       lecturer_id=self.lecturer.id, department_id=self.dept.id)
            db.session.add(c)
            courses.append(c)
        db.session.flush()
        # Course 4 never runs a session: it must be left out, not shown as 0%.
        sessions = {c.id: [] for c in courses}
        for c in courses[:4]:
            for _ in range(rng.randint(1, 6)):
                s = SessionModel(course_id=c.id, is_active=False)
                db.session.add(s)
                sessions[c.id].append(s)
        db.session.flush()

        students = []
        for i in range(n_students):
            u = User(username=f'MCT/20/{i:04d}', password_hash='x', role='student')
            db.session.add(u)
            db.session.flush()
            st = Student(full_name=f'Student {i}', matric_number=u.username, level='400',
                         department_id=self.dept.id, user_id=u.id)
            db.session.add(st)
            db.session.flush()
            students.append(st)
            for c in rng.sample(courses, rng.randint(0, 5)):
                db.session.add(Enrollment(student_id=st.id, course_id=c.id))
                for s in sessions[c.id]:
                    roll = rng.random()
                    if roll < 0.6:
                        status = 'present'
                    elif roll < 0.75:
                        status = 'late'
                    elif roll < 0.85:
                        status = 'excused'  # not attended
                    else:
                        continue
                    db.session.add(Attendance(student_id=st.id, session_id=s.id, status=status))
        db.session.commit()
        return courses, students

    def test_matches_the_old_per_student_calculation(self):
        courses, students = self.build_department(40, random.Random(7))
        course_ids = [c.id for c in courses]
        new = _department_attendance(courses)
        for st in students:
            self.assertEqual(new.get(st.id, (None, [])), old_student_attendance(st, course_ids),
                             f'student {st.id}')

    def test_query_count_does_not_grow_with_students(self):
        def queries_for(n):
            db.drop_all()
            db.create_all()
            self.setUp_rows()
            courses, _ = self.build_department(n, random.Random(n))
            count = [0]

            def on_execute(*_a, **_k):
                count[0] += 1
            event.listen(db.engine, 'before_cursor_execute', on_execute)
            try:
                _department_attendance(courses)
            finally:
                event.remove(db.engine, 'before_cursor_execute', on_execute)
            return count[0]

        self.assertEqual(queries_for(5), queries_for(80))

    def setUp_rows(self):
        """Re-create the department rows after a drop_all inside a test."""
        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.flush()
        user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(user)
        db.session.flush()
        self.lecturer = Lecturer(full_name='Dr Ade', staff_id='S1',
                                 department_id=self.dept.id, user_id=user.id)
        db.session.add(self.lecturer)
        db.session.flush()


if __name__ == '__main__':
    unittest.main()
