from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required,connect_to_database

student_bp = Blueprint('student', __name__)


@student_bp.route('/student/dashboard')
@login_required('student')
def dashboard():
    return render_template('student/dashboard.html')