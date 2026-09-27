"""
Create the offline_checkin_logs table on an existing database.

WHY A STANDALONE SCRIPT
-----------------------
This project's Alembic chain cannot bootstrap: the base revision
(21763aa0310a) immediately does batch_op.add_column() on a `users` table
that no migration ever creates, and reset_db.py rebuilds via create_all()
without stamping a revision. So `flask db upgrade` is not a usable path for
adding a table to production.

This script does the one thing needed, with CREATE TABLE IF NOT EXISTS, so
it is safe to run against the live database: it touches nothing else, drops
nothing, and is a no-op if the table already exists.

    python add_offline_checkin_log.py

Verify first (read-only):

    python add_offline_checkin_log.py --check

Matches OfflineCheckinLog in models.py. If you change that model, change
this too -- there is no migration to catch the drift.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app  # noqa: E402
from extensions import db  # noqa: E402

DDL = """
CREATE TABLE IF NOT EXISTS offline_checkin_logs (
    id INT NOT NULL AUTO_INCREMENT,
    student_id INT NOT NULL,
    session_id INT NOT NULL,
    terminal_id VARCHAR(64) NOT NULL,
    captured_at DATETIME NOT NULL,
    synced_at DATETIME NOT NULL,
    status ENUM('pending_verification','superseded','rejected') NOT NULL DEFAULT 'pending_verification',
    reason VARCHAR(120) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_offline_checkin_student_session (student_id, session_id),
    KEY ix_offline_checkin_session_status (session_id, status),
    CONSTRAINT fk_offline_checkin_student FOREIGN KEY (student_id) REFERENCES students (id),
    CONSTRAINT fk_offline_checkin_session FOREIGN KEY (session_id) REFERENCES sessions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def main():
    check_only = "--check" in sys.argv

    with app.app_context():
        existing = db.session.execute(
            db.text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_name = 'offline_checkin_logs'"
            )
        ).scalar()

        if existing:
            print("offline_checkin_logs already exists -- nothing to do.")
            return

        if check_only:
            print("offline_checkin_logs is MISSING. Run without --check to create it.")
            return

        print("Creating offline_checkin_logs ...")
        db.session.execute(db.text(DDL))
        db.session.commit()
        print("Done. offline_checkin_logs created.")


if __name__ == "__main__":
    main()
