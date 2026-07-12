from flask import Blueprint, flash, render_template, redirect, request, url_for
import bcrypt
from datetime import datetime, timezone
from utils import login_required

# Notice we imported 'Attendance' to make our dashboard query cleaner
from models import db, User, Student, Lecturer, Session as SessionModel, Attendance

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/admin/dashboard')
@login_required('admin')
def dashboard():
    # Direct ORM counts
    lecturer_count = Lecturer.query.count()
    student_count = Student.query.count()
    active_sessions = SessionModel.query.filter_by(is_active=True).count()
    
    # 1. Fetch today's date using our new future-proofed timezone method
    today = datetime.now(timezone.utc).date()
    
    # 2. Replaced the bulky db.execute block with a sleek ORM query
    today_scans = Attendance.query.filter(
        db.func.date(Attendance.time_in) == today
    ).count()

    sessions = SessionModel.query.filter_by(is_active=True).all()

    return render_template(
        'admin1/dashboard.html',
        lecturer_count=lecturer_count,
        student_count=student_count,
        active_sessions=active_sessions,
        today_scans=today_scans,
        sessions=sessions,
    )


@admin_bp.route('/admin/create-lecturer', methods=['GET', 'POST'])
@login_required('admin')
def create_lecturer():
    if request.method == 'GET':
        return render_template('admin1/create-lecturer.html')

    full_name = request.form.get('full_name')
    staff_id = request.form.get('staff_id')

    if not full_name or not staff_id:
        flash('Full name and staff ID are required.', 'error')
        return render_template('admin1/create-lecturer.html')

    # Check if user already exists
    existing_user = User.query.filter_by(username=staff_id).first()
    if existing_user:
        flash('A user with this staff ID already exists.', 'error')
        return render_template('admin1/create-lecturer.html')

    hashed_password = bcrypt.hashpw(
        staff_id.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    try:
        # Create user account (Defaults to requires_password_change=True)
        new_user = User(
            username=staff_id,
            password_hash=hashed_password,
            role='lecturer',
            is_active=True,
            requires_password_change=True,
        )
        db.session.add(new_user)
        db.session.flush()  # Gets the new user ID without committing

        # Create lecturer profile
        new_lecturer = Lecturer(
            user_id=new_user.id,
            full_name=full_name,
            staff_id=staff_id,
        )
        db.session.add(new_lecturer)
        db.session.commit()

        flash('Lecturer created successfully.', 'success')
        return redirect(url_for('admin.create_lecturer'))

    except Exception as e:
        db.session.rollback()
        print(f"Error creating lecturer: {e}") # Added for console debugging
        flash('Error occurred while creating lecturer.', 'error')
        return redirect(url_for('admin.create_lecturer'))


@admin_bp.route('/admin/create-student', methods=['GET', 'POST'])
@login_required('admin')
def create_student():
    if request.method == 'GET':
        return render_template('admin1/create-student.html')

    full_name = request.form.get('full_name')
    matric_number = request.form.get('matric_number')
    department = request.form.get('department')
    level = request.form.get('level')
    rfid_uid = request.form.get('rfid_uid')

    if not full_name or not matric_number or not department or not level or not rfid_uid:
        flash('All fields are required.', 'error')
        return render_template('admin1/create-student.html')

    # Check if user already exists
    existing_user = User.query.filter_by(username=matric_number).first()
    if existing_user:
        flash('A user with this matric number already exists.', 'error')
        return render_template('admin1/create-student.html')

    hashed_password = bcrypt.hashpw(
        matric_number.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

    try:
        # Create user account (Defaults to requires_password_change=True)
        new_user = User(
            username=matric_number,
            password_hash=hashed_password,
            role='student',
            is_active=True,
            requires_password_change=True,
        )
        db.session.add(new_user)
        db.session.flush()

        # Create student profile
        new_student = Student(
            user_id=new_user.id,
            full_name=full_name,
            matric_number=matric_number,
            department=department,
            level=level,
            rfid_uid=rfid_uid,
        )
        db.session.add(new_student)
        db.session.commit()

        flash('Student created successfully.', 'success')
        return redirect(url_for('admin.create_student'))

    except Exception as e:
        db.session.rollback()
        print(f"Error creating student: {e}") # Added for console debugging
        flash('Error occurred while creating student.', 'error')
        return redirect(url_for('admin.create_student'))