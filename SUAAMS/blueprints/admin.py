from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required
from utils import connect_to_database
import bcrypt
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard')
@login_required('admin')
def dashboard():
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM lecturers")
    lecturer_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM students")
    student_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM sessions where is_active = 1")
    active_sessions = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM attendance WHERE time_in >= CURDATE()")
    today_scans = cursor.fetchone()[0]
    
    cursor.close()
    connection.close()

    return render_template('admin1/dashboard.html', lecturer_count=lecturer_count, student_count=student_count, active_sessions=active_sessions, today_scans=today_scans)


@admin_bp.route('/admin/create-lecturer', methods=['GET', 'POST'])
@login_required('admin')
def create_lecturer():
    if request.method == 'GET':
        return render_template('admin1/create-lecturer.html')
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        staff_id = request.form.get('staff_id')
        
        if not full_name or not staff_id:
            flash('Full name and staff ID are required.', 'error')
            return render_template('admin1/create-lecturer.html')
        
        connection = connect_to_database()
        cursor = connection.cursor()
        
        cursor.execute("SELECT username FROM users WHERE username = %s", (staff_id,))
        user_n = cursor.fetchone()
        
        if user_n:
            flash('A user with this staff ID already exists.', 'error')
            cursor.close()
            connection.close()
            return render_template('admin1/create-lecturer.html')
        
        password = staff_id
        password_bytes = password.encode('utf-8')
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        try:
            cursor.execute("INSERT INTO users (username, passwordhash, role, is_active) VALUES (%s, %s, %s, %s)", 
                        (staff_id, hashed_password, 'lecturer', 1))
            user_id = cursor.lastrowid
            cursor.execute("INSERT INTO lecturers (user_id, full_name, staff_id) VALUES (%s, %s, %s)", 
                        (user_id, full_name, staff_id))
            connection.commit()
            cursor.close()
            connection.close()
            flash('Lecturer created successfully.', 'success')
            return redirect(url_for('admin.create_lecturer'))
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            flash('Error occurred while creating lecturer.', 'error')
            return redirect(url_for('admin.create_lecturer'))
        
@admin_bp.route('/admin/create-student', methods=['GET', 'POST'])
@login_required('admin')
def create_student():
    if request.method == 'GET':
        return render_template('admin1/create-student.html')
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        matric_number = request.form.get('matric_number')
        department = request.form.get('department')
        level = request.form.get('level')
        rfid_uid = request.form.get('rfid_uid')
        
        if not full_name or not matric_number or not department or not level or not rfid_uid:
            flash('All fields are required.', 'error')
            return render_template('admin1/create-student.html')
        
        connection = connect_to_database()
        cursor = connection.cursor()
        
        cursor.execute("SELECT username FROM users WHERE username = %s", (matric_number,))
        user_n = cursor.fetchone()
        
        if user_n:
            flash('A user with this matric number already exists.', 'error')
            cursor.close()
            connection.close()
            return render_template('admin1/create-student.html')
        
        password = matric_number
        password_bytes = password.encode('utf-8')
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        try:
            cursor.execute("INSERT INTO users (username, passwordhash, role, is_active) VALUES (%s, %s, %s, %s)", 
                        (matric_number, hashed_password, 'student', 1))
            user_id = cursor.lastrowid
            cursor.execute("INSERT INTO students (user_id, FULL_NAME, MATRIC_NUMBER, DEPARTMENT, LEVEL, RFID_UID) VALUES (%s, %s, %s, %s, %s, %s)", 
                        (user_id, full_name, matric_number, department, level, rfid_uid))
            connection.commit()
            cursor.close()
            connection.close()
            flash('Student created successfully.', 'success')
            return redirect(url_for('admin.create_student'))
        except Exception as e:
            connection.rollback()
            cursor.close()
            connection.close()
            flash('Error occurred while creating student.', 'error')
            return redirect(url_for('admin.create_student'))