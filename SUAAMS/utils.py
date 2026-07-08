from flask import session,redirect,url_for
from functools import wraps
import mysql.connector
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'bikxczmqtdlkynudsfrp-mysql.services.clever-cloud.com'),
    'user': os.environ.get('DB_USER', 'uo5woagbfvcducyy'),
    'password': os.environ.get('DB_PASSWORD', 'edVtI3biNQmhQrfJwRe8'),
    'database': os.environ.get('DB_NAME', 'bikxczmqtdlkynudsfrp'),
    'port': int(os.environ.get('DB_PORT', 3306))
}

def connect_to_database():
    return mysql.connector.connect(**DB_CONFIG)

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
    
def get_active_session_by_course_id(cursor, course_id):
    query = "SELECT id, course_id, start_time, stop_time, session_date FROM sessions WHERE is_active = 1 AND course_id = %s ORDER BY id DESC LIMIT 1"
    cursor.execute(query, (course_id,))
    return cursor.fetchone()