from flask import session,redirect,url_for,flash
from functools import wraps

#it finally worked !!!!!!!!!
def login_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please log in to access that page.', 'error')
                return redirect(url_for('auth.login'))
            if session.get('role') != role:
                flash('You do not have permission to access that page.', 'error')
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)
        return wrapper
    return decorator
    
