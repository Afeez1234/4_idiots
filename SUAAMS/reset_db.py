"""
One-time destructive reset: drops every table and recreates them from the
current models.py (14-table schema). Run this ONCE against the production
DB to move past the old schema without going through the migration chain,
then run seed_admin.py to recreate the admin account (wiped along with
everything else).

Requires the same env vars app.py needs (DB_HOST/DB_USER/DB_PASSWORD/
DB_NAME/...) to already be set, since it imports `app` directly.
"""
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
        print(f"All tables in '{db_name}' dropped and recreated from current models.py.")

if __name__ == '__main__':
    reset_db()
