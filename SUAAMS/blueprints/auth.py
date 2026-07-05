from flask import Blueprint,flash,render_template,redirect,request,session,url_for
import bcrypt
from utils import connect_to_database

auth_bp = Blueprint('auth',__name__)


@auth_bp.route('/login', methods = ['POST','GET'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required','error')
            return render_template('auth/login.html')
        
        connection = connect_to_database()
        cursor = connection.cursor()
        try:
            cursor.execute("select id ,username, password_hash,role,is_active from users where username =%s", (username,))
            user = cursor.fetchone()
        except Exception as e:
            flash('Error occurred while fetching user data','error')
            return render_template('auth/login.html')
        finally:
            cursor.close()
            connection.close()
        
        if not user:
            flash('Invalid username or password','error')
            return render_template('auth/login.html')
        
        user_id,db_username,password_hash,role,is_active = user
        
        if not is_active:
            flash('User profile is deactivated','error')
            return render_template('auth/login.html')
        
        password_bytes = password.encode('utf-8')
        if not bcrypt.checkpw(password_bytes, password_hash.encode('utf-8')):
            flash('Invalid username or password','error')
            return render_template('auth/login.html')
        
        session['user_id'] = user_id
        session['username'] = db_username
        session['role'] = role
        
        if role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif role == 'lecturer':
            return redirect(url_for('lecturer.dashboard'))
        elif role == 'student':
            return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid user role','error')
            return render_template('auth/login.html')
                
     
    
    
@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('you have been ejected','success')
    return redirect(url_for('auth.login'))
    