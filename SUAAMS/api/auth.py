from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token,jwt_required,get_jwt_identity
import bcrypt
from utils import connect_to_database

# Create the API blueprint for mobile authentication
api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/v1/auth')

@api_auth_bp.route('/login', methods=['POST'])
def mobile_login():
    data = request.get_json()
    
    # The Flutter app sends "student_id" (which maps to the DB 'username') and "password"
    username = data.get('username') 
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "Missing credentials"}), 400

    # 1. Connect to DB and fetch user
    connection = connect_to_database()
    cursor = connection.cursor()
    try:
        query = "SELECT id, username, password_hash, role, is_active FROM users WHERE username = %s"
        cursor.execute(query, (username,))
        user = cursor.fetchone()
    finally:
        cursor.close()
        connection.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    user_id, db_username, password_hash, role, is_active = user

    # 2. Check if account is active
    if not is_active:
        return jsonify({"error": "Account is disabled"}), 403

    # 3. Verify bcrypt password
    # Note: password_hash from DB might be string, bcrypt requires bytes
    if bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8')):
        
        # 4. Generate the Access Token using Flask-JWT-Extended
        # We store the role in additional_claims so Flutter can route the user to the correct Dashboard
        access_token = create_access_token(
            identity=str(user_id),
            additional_claims={"role": role, "username": db_username}
        )

        return jsonify({
            "success": True,
            "token": access_token,
            "user": {
                "id": user_id,
                "username": db_username,
                "role": role
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
    
    # Hash the new password securely
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    connection = connect_to_database()
    cursor = connection.cursor()
    
    try:
        # Update the password and clear the flag
        cursor.execute(
            "UPDATE users SET password_hash = %s, requires_password_change = FALSE WHERE id = %s",
            (hashed_password, current_user_id)
        )
        connection.commit()
        return jsonify({"success": True, "message": "Authorization code updated"}), 200
    except Exception as e:
        connection.rollback()
        return jsonify({"error": "Failed to update authorization code", "details": str(e)}), 500
    finally:
        cursor.close()
        connection.close()