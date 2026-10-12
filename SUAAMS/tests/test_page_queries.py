"""Tests for the pages rewritten to stop running queries per item (audit
findings 12 and 20):

  * utils.student_course_attendance (student dashboard, app and web) gives
    the same numbers as the old per-course version, kept below as the
    reference, and its query count doesn't grow with the number of courses,
  * the app's course analytics returns the right numbers and its query
    count doesn't grow with the number of students.

Run with:  python tests/test_page_queries.py
(also collected by pytest if it is installed)
"""

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from flask_jwt_extended import JWTManager, create_access_token  # noqa: E402
from sqlalchemy import event  # noqa: E402

from extensions import limiter, csrf  # noqa: E402
from models import (  # noqa: E402
    db, Faculty, Department, User, Student, Lecturer, Course, Enrollment,
    Session as SessionModel, Attendance,
)
from api.lecturer import api_lecturer_bp  # noqa: E402
from utils import student_course_attendance  # noqa: E402


def old_course_breakdown(student):
    """The previous per-course loop (api/student.py dashboard and
    blueprints/student.py), the reference the new helper must match."""
    out = {}
    for course in student.courses:
        total = SessionModel.query.filter_by(course_id=course.id).count()
        attended = Attendance.query.join(SessionModel).filter(
            SessionModel.course_id == course.id,
            Attendance.student_id == student.id,
        ).count()
        out[course.id] = (attended, total, round((attended / total * 100) if total else 0, 1))
    return out


class PageQueriesTestCase(unittest.TestCase):

    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
            SECRET_KEY='test', JWT_SECRET_KEY='test-jwt-secret-key-long-enough',
            TESTING=True, WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False,
        )
        db.init_app(self.app)
        JWTManager(self.app)
        limiter.init_app(self.app)
        csrf.init_app(self.app)
        self.app.register_blueprint(api_lecturer_bp)
        self.ctx = self.app.app_context()
        self.ctx.push()
        db.create_all()
        self.client = self.app.test_client()

        faculty = Faculty(name='Engineering')
        db.session.add(faculty)
        db.session.flush()
        self.dept = Department(name='Mechatronics', faculty_id=faculty.id)
        db.session.add(self.dept)
        db.session.flush()
        self.lect_user = User(username='lect', password_hash='x', role='lecturer')
        db.session.add(self.lect_user)
        db.session.flush()
        self.lecturer = Lecturer(full_name='Dr Ade', staff_id='S1',
                                 department_id=self.dept.id, user_id=self.lect_user.id)
        db.session.add(self.lecturer)
        db.session.commit()
        self.n = 0

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.ctx.pop()

    def student(self):
        self.n += 1
        u = User(username=f'S{self.n}', password_hash='x', role='student')
        db.session.add(u)
        db.session.flush()
        s = Student(full_name=f'Student {self.n}', matric_number=u.username, level='400',
                    department_id=self.dept.id, user_id=u.id)
        db.session.add(s)
        db.session.flush()
        return s

    def course(self, code):
        c = Course(course_title=code, course_code=code, lecturer_id=self.lecturer.id,
                   department_id=self.dept.id)
        db.session.add(c)
        db.session.flush()
        return c

    @staticmethod
    def count_queries(fn):
        n = [0]

        def on_execute(*_a, **_k):
            n[0] += 1
        event.listen(db.engine, 'before_cursor_execute', on_execute)
        try:
            fn()
        finally:
            event.remove(db.engine, 'before_cursor_execute', on_execute)
        return n[0]

    # ---- finding 12: student dashboard ----------------------------------------

    def test_student_stats_match_the_old_calculation(self):
        rng = random.Random(3)
        courses = [self.course(f'MCT 40{i}') for i in range(6)]
        sessions = {c.id: [SessionModel(course_id=c.id, is_active=rng.random() < 0.2)
                           for _ in range(rng.randint(0, 5))] for c in courses}
        for group in sessions.values():
            db.session.add_all(group)
        db.session.flush()
        students = [self.student() for _ in range(15)]
        for st in students:
            for c in rng.sample(courses, rng.randint(0, 6)):
                db.session.add(Enrollment(student_id=st.id, course_id=c.id))
                for sess in sessions[c.id]:
                    if rng.random() < 0.7:
                        db.session.add(Attendance(student_id=st.id, session_id=sess.id,
                                                  status=rng.choice(['present', 'late'])))
        db.session.commit()

        for st in students:
            new = {r['course'].id: (r['attended'], r['total'], r['pct'])
                   for r in student_course_attendance(st)}
            self.assertEqual(new, old_course_breakdown(st), f'student {st.id}')

    def test_student_stats_queries_do_not_grow_with_courses(self):
        def queries_with(n_courses):
            st = self.student()
            for i in range(n_courses):
                c = self.course(f'C{self.n}-{i}')
                db.session.add(Enrollment(student_id=st.id, course_id=c.id))
                db.session.add(SessionModel(course_id=c.id, is_active=False))
            db.session.commit()
            return self.count_queries(lambda: student_course_attendance(st))

        self.assertEqual(queries_with(2), queries_with(9))

    # ---- finding 20: app course analytics --------------------------------------

    def analytics(self, course_id):
        token = create_access_token(identity=str(self.lect_user.id),
                                    additional_claims={'role': 'lecturer'})
        return self.client.get(f'/api/v1/lecturer/course/{course_id}/analytics',
                               headers={'Authorization': f'Bearer {token}'})

    def build_course(self, n_students):
        c = self.course(f'AN{n_students}')
        done = [SessionModel(course_id=c.id, is_active=False) for _ in range(4)]
        live = SessionModel(course_id=c.id, is_active=True)  # must be ignored
        db.session.add_all(done + [live])
        db.session.flush()
        students = [self.student() for _ in range(n_students)]
        for i, st in enumerate(students):
            db.session.add(Enrollment(student_id=st.id, course_id=c.id))
            # Student i attends the first (i % 5) completed sessions...
            for sess in done[:i % 5]:
                db.session.add(Attendance(student_id=st.id, session_id=sess.id))
            # ...and the live one, which must not count.
            db.session.add(Attendance(student_id=st.id, session_id=live.id))
        db.session.commit()
        return c, students, done

    def test_analytics_numbers(self):
        c, students, done = self.build_course(5)   # attend 0,1,2,3,4 of 4 sessions
        data = self.analytics(c.id).get_json()['data']
        self.assertEqual(data['summary']['total_sessions'], 4)
        self.assertEqual([p['present_count'] for p in data['trend']], [4, 3, 2, 1])
        by_name = {s['full_name']: (s['attended'], s['pct']) for s in data['students']}
        self.assertEqual(by_name[students[0].full_name], (0, 0))
        self.assertEqual(by_name[students[4].full_name], (4, 100.0))
        self.assertEqual(data['students'][0]['pct'], 0)   # most at-risk first

    def test_analytics_queries_do_not_grow_with_students(self):
        # Plain ids, read before measuring: touching a model object after a
        # commit reloads it, and that query would be counted against the
        # endpoint.
        small = self.build_course(3)[0].id
        large = self.build_course(40)[0].id
        # The very first request in a test pays one-off setup queries;
        # make one before measuring so both counts are like for like.
        self.analytics(small)
        self.assertEqual(self.count_queries(lambda: self.analytics(small)),
                         self.count_queries(lambda: self.analytics(large)))


if __name__ == '__main__':
    unittest.main()
