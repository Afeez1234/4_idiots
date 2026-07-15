from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import bcrypt

# We import db and User instead of connect_to_database
from models import db, User

# Create the API blueprint for mobile authentication
api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/v1/auth')

@api_auth_bp.route('/login', methods=['POST'])
def mobile_login():
    data = request.get_json()
    
    # The Flutter app sends "student_id" (which maps to the DB 'username') and "password"
    username = data.get('username') 
    password = data.get('password')
    device_id = data.get('device_id')

    if not username or not password or not device_id:
        return jsonify({"error": "Missing credentials or device signature"}), 400

    # 1. Fetch user gracefully via ORM
    user = User.query.filter_by(username=username).first()

    if not user:
        return jsonify({"error": "User not found"}), 404

    # 2. Check if account is active
    if not user.is_active:
        return jsonify({"error": "Account is disabled"}), 403

    # 3. Verify bcrypt password
    if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')): 
        if user.role == 'student':
            student_profile = user.student
            if not student_profile:
                return jsonify({"error": "Student profile corrupted"}), 500
            
            # 1. First Login (No device bound yet)
            if student_profile.device_id is None:
                student_profile.device_id = device_id
                db.session.commit()
            
            # 2. Subsequent Login (Check if hardware matches)
            elif student_profile.device_id != device_id:
                return jsonify({
                    "error": "SECURITY LOCK: Account is bound to another device. Please visit IT Administration to request a hardware unbind."
                }), 403
        
        # 4. Generate the Access Token using Flask-JWT-Extended
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.role, "username": user.username}
        )

        return jsonify({
            "success": True,
            "token": access_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "requires_password_change": user.requires_password_change # Flutter relies on this!
            }
        }), 200
        
    else:
        return jsonify({"error": "Invalid password"}), 401


@api_auth_bp.route('/change-password', methods=['POST'])
@jwt_required()
def mobile_change_password():
    data = request.get_json()
    new_password = data.get('new_password')
    
    if not new_password:
        return jsonify({"error": "New password is required"}), 400
        
    current_user_id = get_jwt_identity()
    
    # Fetch the user using their JWT Identity
    try:
        user = User.query.get(current_user_id)
    except Exception:
        user =  User.query.get(int(current_user_id))
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Hash the new password securely
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    try:
        # Update the password and clear the flag using ORM
        user.password_hash = hashed_password
        user.requires_password_change = False
        
        db.session.commit() # Save changes to the database
        
        return jsonify({"success": True, "message": "Authorization code updated"}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to update authorization code", "details": str(e)}), 500