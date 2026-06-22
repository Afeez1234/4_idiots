from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required,connect_to_database,get_active_session_by_course_id

lecturer_bp = Blueprint('lecturer', __name__)

#reminder:: the fuction below will create a new session for the course,i'm still wondering if i shoud keep it here or put it in the endpoint
def create_session(cursor,connection,course_id,start_time,stop_time,session_date):
    query = "INSERT INTO sessions (course_id,start_time,stop_time,session_date,is_active) VALUES(%s,%s,%s,%s,1)"
    cursor.execute(query, (course_id,start_time,stop_time,session_date))
    connection.commit()

def end_session(cursor,connection,session_id):
    query = "UPDATE sessions SET is_active = 0 WHERE id = %s"
    cursor.execute(query, (session_id,))
    connection.commit()
    
def get_attendance_by_session_id(cursor, session_id):
    query = "SELECT students.FULL_NAME, students.LEVEL, students.DEPARTMENT,students.MATRIC_NUMBER,attendance.status, attendance.TIME_IN FROM attendance JOIN students ON attendance.student_id = students.id WHERE attendance.session_id = %s"
    cursor.execute(query, (session_id,))
    return cursor.fetchall()

@lecturer_bp.route('/lecturer/dashboard')
@login_required('lecturer')
def dashboard():
    user_id = session.get('user_id')
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM lecturers WHERE user_id = %s', (user_id,))
    lecturer = cursor.fetchone()
    if not lecturer:
        flash('Lecturer profile not found.', 'error')
        return redirect(url_for('auth.login'))
    lecturer_id, = lecturer
    cursor.execute('SELECT id, course_title,course_code FROM courses WHERE lecturer_id = %s', (lecturer_id,))
    courses = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template('lecturer/dashboard.html', courses=courses)
    

@lecturer_bp.route('/lecturer/course/<int:course_id>')
@login_required('lecturer')
def course_workspace(course_id):
    user_id = session.get('user_id')
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM lecturers WHERE user_id = %s', (user_id,))
    lecturer = cursor.fetchone()
    if not lecturer:
        flash('Lecturer profile not found.', 'error')
        return redirect(url_for('auth.login'))
    lecturer_id, = lecturer
    cursor.execute('SELECT id, course_title, course_code FROM courses WHERE id = %s AND lecturer_id = %s', (course_id, lecturer_id))
    course = cursor.fetchone()
    if not course:
        flash('Course not found or access denied.', 'error')
        return redirect(url_for('lecturer.dashboard'))
    attendance_records = []
    sesh = get_active_session_by_course_id(cursor, course_id)
    if sesh:
        session_id, _, start_time, stop_time, session_date = sesh
        attendance_records = get_attendance_by_session_id(cursor, session_id)
    cursor.close()
    connection.close()
    return render_template('lecturer/course_workspace.html', course=course, active_session=sesh, attendance_records=attendance_records)