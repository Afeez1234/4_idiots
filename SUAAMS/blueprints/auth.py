from flask import Blueprint, flash, render_template, redirect, request, session, url_for
import bcrypt
from models import db, User  # Imported 'db' to allow committing password changes

auth_bp = Blueprint('auth', __name__)


def redirect_to_dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin.dashboard'))
    if role == 'lecturer':
        return redirect(url_for('lecturer.dashboard'))
    if role == 'student':
        return redirect(url_for('student.dashboard'))
    session.clear()
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['POST', 'GET'])
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
            flash('Invalid username or password', 'error')
            return render_template('auth/login.html')

        # Set session variables
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role

        # SECURITY CHECK: Force password change on first login
        if user.requires_password_change:
            flash('Security Alert: Please update your default authorization code.', 'warning')
            return redirect(url_for('auth.web_change_password'))

        # If everything is clear, route them to their respective dashboard
        return redirect_to_dashboard()


@auth_bp.route('/change-password', methods=['GET', 'POST'])
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
        db.session.commit()

        flash('Authorization code updated successfully! Welcome to SUAAMS.', 'success')
        return redirect_to_dashboard()


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been ejected', 'success')
    return redirect(url_for('auth.login'))
