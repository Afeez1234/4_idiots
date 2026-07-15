from app import app
from models import db
from sqlalchemy import text

with app.app_context():
    # This safely drops all tables so we can start fresh
    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
    db.session.execute(text("DROP TABLE IF EXISTS attendance, enrollments, sessions, timetable, courses, lecturers, students, departments, faculties, users, alembic_version;"))
    db.session.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
    db.session.commit()
    print("✅ Database wiped cleanly! Ready for V2.0")