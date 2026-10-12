"""Create a personal admin login, or switch an admin login off.

Each person who manages the admin dashboard should have their own account,
so the Activity page (/admin/activity) can show who changed what. A shared
login makes every change anonymous.

Run from SUAAMS/, with the same .env the server uses (it connects to that
database -- on your machine that is usually the production database):

    python create_admin.py tunde               create an admin called "tunde"
    python create_admin.py --disable admin     switch off the shared "admin"

Creating prints a temporary password ONCE. Send it to the person privately.
They must replace it at first login; the dashboard refuses every other page
until they do.
"""
import argparse
import getpass
import secrets
import sys

import bcrypt

from app import app
from audit import log_action
from models import User, db


def _cli_actor():
    # Recorded as the person at the keyboard, e.g. "cli:N9ne". There is no
    # logged-in dashboard user when this runs.
    return None, f'cli:{getpass.getuser()}', 'system'


def create(username):
    username = username.strip()
    if not username:
        sys.exit('Username cannot be empty.')

    # Random and shown once. Only the bcrypt hash is stored, so if it's
    # lost, run this again with a different username or reset it by hand.
    temp_password = secrets.token_urlsafe(12)
    password_hash = bcrypt.hashpw(temp_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    with app.app_context():
        if User.query.filter_by(username=username).first():
            sys.exit(f"An account called '{username}' already exists.")

        user = User(
            username=username,
            password_hash=password_hash,
            role='admin',
            is_active=True,
            requires_password_change=True,
        )
        db.session.add(user)
        db.session.flush()  # gives user.id for the log entry

        log_action(
            'admin.create', f'Created admin account {username}',
            'user', user.id, actor=_cli_actor(),
        )
        db.session.commit()

    print(f"Created admin '{username}'.")
    print(f'Temporary password (shown once): {temp_password}')
    print('They must change it at first login.')


def disable(username):
    with app.app_context():
        user = User.query.filter_by(username=username.strip()).first()
        if not user:
            sys.exit(f"No account called '{username}'.")
        if user.role != 'admin':
            sys.exit(f"'{username}' is a {user.role}, not an admin. Nothing changed.")
        if not user.is_active:
            sys.exit(f"'{username}' is already disabled.")

        # Refuse to switch off the last working admin -- that would lock
        # everyone out of the dashboard with no way back in except the
        # database itself.
        others = User.query.filter(
            User.role == 'admin', User.is_active.is_(True), User.id != user.id,
        ).count()
        if others == 0:
            sys.exit(f"'{username}' is the only active admin. Create another first.")

        # Disabled, not deleted: the account's past changes stay attributed
        # to it, and the web login already refuses inactive accounts.
        user.is_active = False
        log_action(
            'admin.disable', f'Disabled admin account {user.username}',
            'user', user.id, actor=_cli_actor(),
        )
        db.session.commit()

    print(f"Disabled '{username}'. It can no longer log in.")


def main():
    parser = argparse.ArgumentParser(description='Create or disable a SUAAMS admin login.')
    parser.add_argument('username', help='the login name, e.g. tunde')
    parser.add_argument('--disable', action='store_true',
                        help='switch this admin account off instead of creating it')
    args = parser.parse_args()

    if args.disable:
        disable(args.username)
    else:
        create(args.username)


if __name__ == '__main__':
    main()
