from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required
from app import connect_to_database
admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard')
@login_required('admin')
def dashboard():
    return render_template('admin/dashboard.html')


@admin_bp.route('/admin/create-lecturer', methods=['GET', 'POST'])
@login_required('admin')
def create_lecturer():
    if request.method == 'GET':
        return render_template('admin/create-lecturer.html')
    
    if request.method == 'POST':
        full_name = request.form.get('full_name')
        staff_id = request.form.get('staff_id')
        
        if not full_name or not staff_id:
            flash('Full name and staff ID are required.', 'error')
            return render_template('admin/create-lecturer.html')
        
        connection = connect_to_database()
        cursor = connection.cursor()
        
        cursor.execute("SELECT username FROM users WHERE username = %s", (staff_id,))
        user_n = cursor.fetchone()
        
        if user_n:
            flash('A user with this staff ID already exists.', 'error')
            cursor.close()
            connection.close()
            return render_template('admin/create-lecturer.html')
        