from flask import session,redirect,url_for
from functools import wraps
import mysql.connector
from config import DB_CONFIG


#it finally worked !!!!!!!!!
def login_required(role):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('auth.login'))
            if session.get('role') != role:
                return redirect(url_for('auth.login'))
            return func(*args, **kwargs)
        return wrapper
    return decorator
    
def connect_to_database():
    return mysql.connector.connect(**DB_CONFIG)