"""
One-time destructive reset: drops every table and recreates them from the
current models.py. Two uses:

  * Setting up a NEW, EMPTY database (README section 9). The migration
    chain can't do that: its first step alters tables that existed before
    migrations were used, so `flask db upgrade` on an empty database fails
    with "no such table: users".
  * Wiping an existing database back to empty. Everything is lost.

Either way, run `python create_admin.py <your-username>` afterwards to
create an admin account. seed_admin.py used to do this
with a fixed admin/admin1234 login; it was removed so every admin has a
personal login and the Activity page can say who did what.

Requires the same env vars app.py needs (DB_HOST/DB_USER/DB_PASSWORD/
DB_NAME/...) to already be set, since it imports `app` directly.
"""
import os

from flask_migrate import stamp

from app import app
from models import db

def reset_db():
    with app.app_context():
        db_name = app.config['SQLALCHEMY_DATABASE_URI'].rsplit('/', 1)[-1]
        # Confirmation gate: this is irreversible and targets whatever DB_*
        # env vars happen to be set, so print the target and require an
        # explicit typed match rather than a bare y/n -- cheap insurance
        # against running this with the wrong environment active.
        confirm = input(
            f"This will DROP ALL TABLES in database '{db_name}' and recreate them "
            f"empty. Type the database name to confirm: "
        )
        if confirm != db_name:
            print('Confirmation did not match. Aborted, nothing was changed.')
            return

        db.drop_all()
        db.create_all()
        # Tell Alembic the fresh tables are already at the latest migration.
        # Without this the next `flask db upgrade` starts again from the very
        # first migration and fails on "duplicate column", because
        # create_all() has already made every table at its final shape.
        stamp(directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'migrations'))
        print(f"All tables in '{db_name}' dropped and recreated from current models.py.")

if __name__ == '__main__':
    reset_db()
