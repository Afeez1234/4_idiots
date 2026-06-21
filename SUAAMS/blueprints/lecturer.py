from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required,connect_to_database

lecturer_bp = Blueprint('lecturer', __name__)

@lecturer_bp.route('/lecturer/dashboard')
@login_required('lecturer')
def dashboard():
    user_id = session.get('user_id')
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('SELECT id FROM lecturers WHERE user_id = %s', (user_id,))
    lecturer_id = cursor.fetchone()
    if not lecturer_id:
        flash('Lecturer profile not found.', 'error')
        return redirect(url_for('auth.login'))
    cursor.execute('SELECT id, course_title,course_code FROM courses WHERE lecturer_id = %s', (lecturer_id,))
    courses = cursor.fetchall()
    cursor.close()
    connection.close()
    return render_template('lecturer/dashboard.html', courses=courses)
    

