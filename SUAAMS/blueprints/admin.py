from flask import Blueprint,flash,render_template,redirect,request,session,url_for
from utils import login_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/dashboard')
@login_required('admin')
def dashboard():
    return render_template('admin/dashboard.html')