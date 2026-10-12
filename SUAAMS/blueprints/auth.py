from flask import Blueprint, flash, render_template, redirect, request, session, url_for
import bcrypt
from models import db, User  # Imported 'db' to allow committing password changes
from extensions import limiter
from audit import log_action

auth_bp = Blueprint('auth', __name__)

# Pages a signed-in user may still reach while they owe a password change.
# Everything else redirects to the change-password page.
_PASSWORD_CHANGE_ALLOWED = {'auth.web_change_password', 'auth.logout', 'static'}


@auth_bp.before_app_request
def enforce_account_state():
    """Server-side checks on every web request from a signed-in user.

    1. A temporary password must be replaced before anything else. Login
       used to redirect to the change-password page once and then trust the
       browser to stay there -- typing /admin/dashboard skipped it, and the
       temporary password (sent over chat, printed by create_admin.py) stayed
       valid forever.
    2. A disabled account is signed out at once, not at its next login. An
       admin switched off with `create_admin.py --disable` would otherwise
       keep working until they happened to log out.

    Only web requests carry the session cookie this reads; the mobile API
    authenticates with JWTs and is unaffected. One primary-key lookup per
    page view.
    """
    user_id = session.get('user_id')
    if not user_id or request.endpoint in (None, 'static'):
        return None

    user = db.session.get(User, user_id)
    if user is None or not user.is_active:
        session.clear()
        flash('Your account is no longer active. Contact an administrator.', 'error')
        return redirect(url_for('auth.login'))

    if user.requires_password_change and request.endpoint not in _PASSWORD_CHANGE_ALLOWED:
        flash('Set a new password before continuing.', 'warning')
        return redirect(url_for('auth.web_change_password'))
    return None


def redirect_to_dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    if role == 'lecturer':
        return redirect(url_for('lecturer.dashboard'))
    if role == 'hod':
        return redirect(url_for('hod.dashboard'))
    if role == 'student':
        return redirect(url_for('student.dashboard'))
    session.clear()
    return redirect(url_for('auth.login'))


# methods=['POST'] scopes the limit to actual login submissions -- GET
# (just rendering the form) isn't rate limited, only credential attempts.
@auth_bp.route('/login', methods=['POST', 'GET'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if session.get('user_id'):
        flash('You are already logged in. Redirecting to your dashboard.', 'info')
        return redirect_to_dashboard()

    if request.method == 'GET':
        return render_template('auth/login.html')

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('auth/login.html')

        # SQLAlchemy query — no cursor, no connection management needed
        user = User.query.filter_by(username=username).first()

        if not user:
            flash('Invalid username or password', 'error')
            return render_template('auth/login.html')

        if not user.is_active:
            flash('User profile is deactivated', 'error')
            return render_template('auth/login.html')

        password_bytes = password.encode('utf-8')
        if not bcrypt.checkpw(
            password_bytes,
            user.password_hash.encode('utf-8')
        ):
            # Failed guesses at an ADMIN account are worth seeing on the
            # Activity page (someone trying a colleague's login). Students'
            # and lecturers' typos are not -- there would be thousands.
            if user.role == 'admin':
                log_action(
                    'auth.login_failed', f'Failed sign-in attempt for {user.username}',
                    'user', user.id, actor=(None, user.username, 'admin'),
                )
                db.session.commit()
            flash('Invalid username or password', 'error')
            return render_template('auth/login.html')

        # Set session variables
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role

        if user.role == 'admin':
            log_action('auth.login', f'{user.username} signed in', 'user', user.id)
            db.session.commit()

        # SECURITY CHECK: Force password change on first login
        if user.requires_password_change:
            flash('Security Alert: Please update your default authorization code.', 'warning')
            return redirect(url_for('auth.web_change_password'))

        # If everything is clear, route them to their respective dashboard
        return redirect_to_dashboard()


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def web_change_password():
    # Ensure only logged-in users can hit this page
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))

    user = db.session.get(User, session['user_id'])

    # If they somehow navigate here but don't need a change, kick them to dashboard
    if not user.requires_password_change:
        return redirect_to_dashboard()

    if request.method == 'GET':
        return render_template('auth/change_password.html')

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not new_password or not confirm_password:
            flash('Both password fields are required.', 'error')
            return render_template('auth/change_password.html')

        if new_password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/change_password.html')

        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'error')
            return render_template('auth/change_password.html')

        # Hash new password and clear the flag using ORM
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user.password_hash = hashed_password
        user.requires_password_change = False
        # Admins only, matching the sign-in entries above. The password
        # itself never reaches the log (and audit._scrub would strip it).
        if user.role == 'admin':
            log_action('auth.password_change', f'{user.username} set a new password',
                       'user', user.id)
        db.session.commit()

        flash('Authorization code updated successfully! Welcome to SUAAMS.', 'success')
        return redirect_to_dashboard()


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been ejected', 'success')
    return redirect(url_for('auth.login'))
