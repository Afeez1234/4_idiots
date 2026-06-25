from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required,connect_to_database,get_active_session_by_course_id
from datetime import date, datetime
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

def get_attendance_history(cursor, course_id):

    query = """
    SELECT
        sessions.id,
        sessions.session_date,
        sessions.start_time,
        COUNT(attendance.id) as present_count
    FROM sessions
    LEFT JOIN attendance ON attendance.session_id = sessions.id
    WHERE sessions.course_id = %s AND sessions.is_active = 0
    GROUP BY sessions.id, sessions.session_date
    ORDER BY sessions.session_date DESC
    """
    cursor.execute(query, (course_id,))
    return cursor.fetchall()

def get_enrolled_students_count(cursor, course_id):
    query = "SELECT COUNT(*) FROM enrollments WHERE course_id = %s"
    cursor.execute(query, (course_id,))
    return cursor.fetchone()[0]

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
    
    #For active_session_count — count sessions WHERE is_active = 1 AND course_id belongs to this lecturer.
    cursor.execute('SELECT COUNT(*) FROM sessions WHERE is_active = 1 AND course_id IN (SELECT id FROM courses WHERE lecturer_id = %s)', (lecturer_id,))
    active_session_count, = cursor.fetchone()
    
    #for today-checkins -  you need to count attendance records from today across all the lecturer's courses. This requires a JOIN across attendance → sessions → courses WHERE lecturer_id matches and TIME_IN >= CURDATE()
    cursor.execute('SELECT COUNT(*) FROM attendance a JOIN sessions s ON a.session_id = s.id JOIN courses c ON s.course_id = c.id WHERE c.lecturer_id = %s AND a.TIME_IN >= CURDATE()', (lecturer_id,))
    today_checkins, = cursor.fetchone()

    cursor.close()
    connection.close()
    return render_template('lecturer/1.html', courses=courses, active_session_count=active_session_count, today_checkins=today_checkins)


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
        
    history = get_attendance_history(cursor, course_id)
    enrolled_count = get_enrolled_students_count(cursor, course_id)

    history_sessions = []
    for row in history:
        session_id, session_date,start_time, present_count = row
        absent_count = enrolled_count - present_count
        history_sessions.append({
            'label': f'{session_date.strftime('%d %b %Y')} {start_time}',
            'date': session_date,
            'present_count': present_count,
            'absent_count': absent_count,
            'session_id': session_id,
        })
    cursor.close()
    connection.close()
    return render_template('lecturer/2.html', course=course, active_session=sesh, attendance_records=attendance_records, history_sessions=history_sessions,)

@lecturer_bp.route('/lecturer/course/<int:course_id>/start-session', methods=['POST'])
@login_required('lecturer')
def start_session(course_id):
    
    connection = connect_to_database()
    cursor = connection.cursor()
    sesh = get_active_session_by_course_id(cursor, course_id)
    if sesh:
        flash('A session is already active for this course.', 'error')
        cursor.close()
        connection.close()
        return redirect(url_for('lecturer.course_workspace', course_id=course_id))
    create_session(cursor, connection, course_id,datetime.now(), datetime.now(), date.today())
    flash('Session started successfully.', 'success')
    cursor.close()
    connection.close()
    return redirect(url_for('lecturer.course_workspace', course_id=course_id))
    
@lecturer_bp.route('/lecturer/course/<int:course_id>/end-session', methods=['POST'])
@login_required('lecturer')
def end_session_r(course_id):
    connection = connect_to_database()
    cursor = connection.cursor()
    sesh = get_active_session_by_course_id(cursor, course_id)
    if not sesh:
        flash('No active session found for this course.', 'error')
        cursor.close()
        connection.close()
        return redirect(url_for('lecturer.course_workspace', course_id=course_id))
    session_id, _, start_time, stop_time, session_date = sesh
    end_session(cursor, connection, session_id)
    flash('Session ended successfully.', 'success')
    cursor.close()
    connection.close()
    return redirect(url_for('lecturer.course_workspace', course_id=course_id))


@lecturer_bp.route('/lecturer/course/<int:course_id>/session/<int:session_id>')
@login_required('lecturer')
def session_detail(course_id,session_id):
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
    cursor.execute('SELECT id, start_time, stop_time, session_date FROM sessions WHERE id = %s AND course_id = %s', (session_id, course_id))
    sessi0n = cursor.fetchone()
    if not sessi0n:
        flash('Session not found')
        return redirect(url_for('lecturer.course_workspace',course_id=course_id))   
    get_attendance_by_session_id()
    return render_template('lecturer/session_detail.html',course=course)