from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token, decode_token,
    jwt_required, get_jwt_identity, get_jwt,
)
import bcrypt
from sqlalchemy.exc import IntegrityError

# We import db and User instead of connect_to_database
from models import db, User, Student, DeviceToken
from extensions import limiter, jwt_identity_or_ip, api_error_response, login_username_key, client_ip
from push_notifications import send_push_notification
from utils import new_password_problem

# Create the API blueprint for mobile authentication
api_auth_bp = Blueprint('api_auth', __name__, url_prefix='/api/v1/auth')


# Strings older app builds sent when the real hardware ID couldn't be read
# (see _getHardwareUUID in auth_provider.dart). They are constants, so every
# phone that hit the fallback reported the SAME "device" -- binding a student
# to one meant any other fallback phone could log into that account. Current
# builds refuse to log in instead of sending these; this set rejects them
# from builds still in the wild.
_PLACEHOLDER_DEVICE_IDS = frozenset({
    'fallback_device_id',
    'unknown_ios_device',
    'unknown_platform',
})

# Checked against when the username doesn't exist, so a wrong username
# costs the same bcrypt time as a wrong password. Without it, an unknown
# username answered in ~1 ms and a known one in ~300 ms, which told anyone
# timing the requests which matric numbers have accounts.
_DUMMY_HASH = bcrypt.hashpw(b'not-a-real-password', bcrypt.gensalt()).decode('utf-8')

# One answer for "no such user" and "wrong password" (the web login does the
# same). They used to differ -- 404 "User not found" / 401 "Invalid
# password" -- so the endpoint confirmed which usernames exist.
_BAD_LOGIN = ({"error": "Invalid username or password"}, 401)

_DEVICE_IN_USE_ERROR = (
    "DEVICE IN USE: This phone is already registered to another student "
    "account. Please visit IT Administration if this is your phone."
)


def install_account_check(jwt_manager):
    """Refuse every app request from an account that no longer exists or
    has been switched off. Registered in app.py (and by the tests that need
    it); runs before every @jwt_required route, so none of them change.

    Before this, switching an account off (people_status, create_admin.py
    --disable) revoked the refresh token, but the phone's current access
    token stayed valid for up to its full 30 minutes: an expelled student
    could still check in, a lecturer who had left could still mark
    attendance. The web dashboards already re-check on every request
    (blueprints/auth.enforce_account_state); this does the same for the app.

    Cost: one primary-key lookup per app request.
    """
    @jwt_manager.token_in_blocklist_loader
    def account_switched_off(_jwt_header, jwt_payload):
        try:
            user = db.session.get(User, int(jwt_payload.get('sub')))
        except (TypeError, ValueError):
            return True
        return user is None or not user.is_active

    # The library's default answer is {"msg": "Token has been revoked"}.
    # This says why, in the "error" key the app's services pass on as the
    # exception text. "Unauthorized" is load-bearing: the app's withAuthRetry
    # (core/network/auth_retry.dart) only refreshes on errors containing
    # "unauthorized" or "expired"; the refresh is then refused for the
    # disabled account, and the app signs out.
    @jwt_manager.revoked_token_loader
    def account_switched_off_response(_jwt_header, _jwt_payload):
        return jsonify({"error": "Unauthorized: account is disabled"}), 401


def _issue_token_pair(user):
    """
    Mints a fresh access+refresh token pair for `user` and records the new
    refresh token's JTI on User.current_refresh_jti (see models.py). This
    is what both login and /refresh call -- login to start a session,
    /refresh to rotate it. Rotating on every refresh (storing the NEW jti,
    overwriting whatever was there) means a stale/replayed refresh token
    presented later won't match and gets rejected -- see mobile_refresh
    below for where that check happens.

    decode_token() is used to read back the jti Flask-JWT-Extended
    auto-generated for the refresh token, rather than generating one
    ourselves -- avoids needing a custom JTI callback just to know what
    value was assigned.
    """
    access_token = create_access_token(
        identity=str(user.id),
        additional_claims={"role": user.role, "username": user.username},
    )
    refresh_token = create_refresh_token(identity=str(user.id))
    user.current_refresh_jti = decode_token(refresh_token)["jti"]
    return access_token, refresh_token

# Two limits. 5/minute PER USERNAME caps password guessing against any one
# account -- generous for a real user who mistypes. 200/minute per address
# caps one machine trying many accounts while still letting a full lecture
# hall on one campus Wi-Fi address sign in during the same minute. This used to be a single 5/minute
# per address, which on campus Wi-Fi (hundreds of students behind one
# public IP) let only five students in the whole hall log in each minute.
@api_auth_bp.route('/login', methods=['POST'])
@limiter.limit("5 per minute", key_func=login_username_key)
@limiter.limit("200 per minute", key_func=client_ip)
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
        bcrypt.checkpw(password.encode('utf-8'), _DUMMY_HASH.encode('utf-8'))
        return jsonify(_BAD_LOGIN[0]), _BAD_LOGIN[1]

    # 2. Verify bcrypt password
    if bcrypt.checkpw(password.encode('utf-8'), user.password_hash.encode('utf-8')):
        # 3. Disabled accounts, checked only AFTER the password: before it,
        # anyone could learn that an account exists and is switched off.
        if not user.is_active:
            return jsonify({"error": "Account is disabled"}), 403

        if user.role == 'student':
            student_profile = user.student
            if not student_profile:
                return jsonify({"error": "Student profile corrupted"}), 500
            
            # Placeholder IDs aren't per-phone, so they can't anchor a
            # binding. Checked for students only -- lecturers aren't bound.
            if device_id in _PLACEHOLDER_DEVICE_IDS:
                return jsonify({
                    "error": "DEVICE UNVERIFIED: This phone's hardware ID could not be read. Please update the app and try again."
                }), 403

            # 1. First Login (No device bound yet)
            if student_profile.device_id is None:
                # ONE ACCOUNT PER PHONE. The lock below only stops an
                # account moving to another phone; without this, one phone
                # could bind several students' accounts and its owner could
                # check them all in with their own fingerprint (buddy
                # punching). Lecturers are unaffected -- only Student rows
                # carry a device_id.
                taken = Student.query.filter(
                    Student.device_id == device_id,
                    Student.id != student_profile.id,
                ).first()
                if taken:
                    return jsonify({"error": _DEVICE_IN_USE_ERROR}), 403

                student_profile.bind_device(device_id)
                try:
                    db.session.commit()
                except IntegrityError:
                    # Two first-logins on the same phone raced past the
                    # check above; the unique constraint on
                    # students.device_id lets exactly one of them bind.
                    db.session.rollback()
                    return jsonify({"error": _DEVICE_IN_USE_ERROR}), 403
            
            # 2. Subsequent Login (Check if hardware matches)
            elif student_profile.device_id != device_id:
                # Security alert to the LEGITIMATE bound device -- the
                # device attempting this login is the one being rejected,
                # so it never gets this far (no token issued to it, ever).
                # Only the previously-bound device can hold a registered
                # DeviceToken, since token registration requires a prior
                # successful login (see /device-token in api/student.py).
                send_push_notification(
                    user,
                    'device_lockout_alert',
                    'Login Attempt Blocked',
                    'Someone tried to log into your account from a different device. If this wasn\'t you, your account remains locked to your original device.',
                )
                return jsonify({
                    "error": "SECURITY LOCK: Account is bound to another device. Please visit IT Administration to request a hardware unbind."
                }), 403
        
        # 4. Generate the access+refresh token pair (see _issue_token_pair
        # above) and persist the refresh token's jti so /refresh can later
        # verify and rotate it.
        access_token, refresh_token = _issue_token_pair(user)
        db.session.commit()

        return jsonify({
            "success": True,
            "token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "requires_password_change": user.requires_password_change, # Flutter relies on this!
                # An HOD created as a new account has no Lecturer profile,
                # so every lecturer screen would fail "Lecturer profile not
                # found"; the app sends them to its web-portal screen
                # instead. A promoted HOD (lecturer + HOD) has one and keeps
                # the lecturer app for their teaching. (2026-10-19)
                "has_lecturer_profile": user.lecturer is not None,
            }
        }), 200
        
    else:
        return jsonify(_BAD_LOGIN[0]), _BAD_LOGIN[1]


# Keyed by user id (via jwt_identity_or_ip), not IP -- this is an
# authenticated action, so the limit should track "this account" rather
# than "this network", which also avoids one shared-WiFi/NAT IP tripping
# the limit for every student behind it.
@api_auth_bp.route('/change-password', methods=['POST'])
@limiter.limit("5 per minute", key_func=jwt_identity_or_ip)
@jwt_required()
def mobile_change_password():
    data = request.get_json(silent=True) or {}
    new_password = data.get('new_password')

    if not new_password:
        return jsonify({"error": "New password is required"}), 400

    current_user_id = get_jwt_identity()

    # BUG FIX: the old code was `try: User.query.get(current_user_id) except
    # Exception: User.query.get(int(current_user_id))` -- a fallback with no
    # try/except of its own. If the FIRST query failed for a reason other
    # than the str/int type mismatch it was written to guard against (e.g.
    # the DB connection itself was down), the retry hit the exact same
    # failure, and that second exception had nothing catching it -- it
    # propagated straight out of the view function, past the
    # api_error_response handling below, and Flask's default error handler
    # returned a bare HTML 500 page instead of JSON. (Confirmed by testing
    # this route against a broken DB connection.)
    #
    # current_user_id is always a numeric string here anyway -- mobile_login
    # above always creates the token with identity=str(user.id) -- so there
    # was never a real need for a fallback query shape, just a plain int()
    # cast. Wrapping the single lookup in one try/except means ANY failure
    # here (bad DB connection, unexpected identity format, etc.) gets
    # logged in full and answered with the same generic JSON error as every
    # other failure path in this route, instead of silently falling through
    # to Flask's default HTML error page.
    try:
        user = User.query.get(int(current_user_id))
    except Exception:
        return api_error_response(
            "Change Password User Lookup Error", "Failed to update authorization code"
        )

    if not user:
        return jsonify({"error": "User not found"}), 404

    # A change the user chose to make needs the current password. Without
    # it, anyone holding an unlocked phone could set a password of their
    # own -- and a lecturer's then opens the web portal, which has no device
    # binding. The forced first change skips it: the user has just signed
    # in with that password. 403 rather than 401, so the app doesn't read
    # it as an expired session and refresh. The 5/minute limit above caps
    # guessing.
    if not user.requires_password_change:
        current = data.get('current_password')
        if not isinstance(current, str) or not bcrypt.checkpw(
                current.encode('utf-8'), user.password_hash.encode('utf-8')):
            return jsonify({"error": "Your current password is incorrect."}), 403

    # Same rules as the web form (utils.new_password_problem); the app's
    # own checks could be skipped by any other client.
    problem = new_password_problem(user, new_password)
    if problem:
        return jsonify({"error": problem}), 400

    # Hash the new password securely
    hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    try:
        # Update the password and clear the flag using ORM
        user.password_hash = hashed_password
        user.requires_password_change = False

        # SECURITY: rotate this user's session on password change -- mints
        # a fresh access+refresh pair (see _issue_token_pair above) and
        # overwrites current_refresh_jti, invalidating whatever refresh
        # token existed before this call. If the old password had been
        # compromised and someone else was holding a valid session from
        # it, changing the password alone wouldn't revoke that session --
        # an already-issued token stays valid regardless of the password
        # it was issued under -- this rotation is what actually does. The
        # device that just authenticated to make this change gets the new
        # pair back in the response, so it isn't collaterally logged out
        # by its own action.
        access_token, refresh_token = _issue_token_pair(user)

        db.session.commit() # Save changes to the database

        return jsonify({
            "success": True,
            "message": "Authorization code updated",
            "token": access_token,
            "refresh_token": refresh_token,
        }), 200

    except Exception:
        # SECURITY FIX: was `jsonify({"error": ..., "details": str(e)})`,
        # which put the raw exception message (can include DB
        # column/constraint names, e.g. from a duplicate-key error) directly
        # in the API response. api_error_response logs the full exception +
        # traceback server-side and returns only a generic message.
        db.session.rollback()
        return api_error_response(
            "Change Password Error", "Failed to update authorization code"
        )


# Keyed by user id -- same reasoning as change-password above. Slightly more
# generous than login's 5/min since a legitimate client may retry a refresh
# a few times across flaky connectivity in one minute.
@api_auth_bp.route('/refresh', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required(refresh=True)
def mobile_refresh():
    """
    Exchanges a refresh token for a new access+refresh pair. Flask-JWT-
    Extended's @jwt_required(refresh=True) already rejects anything that
    isn't a valid, unexpired refresh token before this function body runs
    -- what we check here is the rotation/revocation invariant: the
    presented token's jti must match User.current_refresh_jti exactly.

    That match fails in three legitimate cases, all of which should force
    a real re-login rather than silently succeeding:
    - The token was already rotated away by an earlier refresh call (stale
      copy, e.g. a retried request or a stolen/replayed token).
    - It was explicitly revoked by /logout.
    - It was explicitly revoked by an admin device unbind
      (reset_student_binding in blueprints/admin.py).
    """
    current_user_id = int(get_jwt_identity())
    presented_jti = get_jwt().get("jti")

    try:
        user = User.query.get(current_user_id)
    except Exception:
        return api_error_response("Refresh User Lookup Error", "Failed to refresh session")

    if not user:
        return jsonify({"error": "User not found"}), 404

    # A disabled account gets no new tokens. Without this, switching an
    # account off (is_active=False) only stopped NEW logins: a phone already
    # signed in kept refreshing every 30 minutes indefinitely -- a lecturer
    # who had left could still mark students present from the app.
    if not user.is_active:
        return jsonify({"error": "Account is disabled"}), 401

    if not user.current_refresh_jti or user.current_refresh_jti != presented_jti:
        return jsonify({"error": "Session has been revoked. Please log in again."}), 401

    try:
        access_token, refresh_token = _issue_token_pair(user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        return api_error_response("Refresh Rotation Error", "Failed to refresh session")

    return jsonify({
        "success": True,
        "token": access_token,
        "refresh_token": refresh_token,
    }), 200


# Requires the REFRESH token specifically, not the access token: logging
# out is fundamentally "invalidate my refresh token", so the client should
# present the credential actually being revoked. Unconditionally nulls
# current_refresh_jti (no jti-match check, unlike /refresh above) --
# logging out should always succeed in wiping server-side state for this
# user regardless of whether the presented token happens to still be the
# "current" one.
@api_auth_bp.route('/logout', methods=['POST'])
@limiter.limit("10 per minute", key_func=jwt_identity_or_ip)
@jwt_required(refresh=True)
def mobile_logout():
    current_user_id = int(get_jwt_identity())

    try:
        user = User.query.get(current_user_id)
        if user:
            user.current_refresh_jti = None
            # Stop pushing to this phone. Without this, the next person to
            # pick up a shared or handed-on phone kept getting this user's
            # notifications. The app registers its token again at its next
            # login (or app start with a saved session).
            DeviceToken.query.filter_by(user_id=user.id).delete()
            db.session.commit()
    except Exception:
        db.session.rollback()
        return api_error_response("Logout Error", "Failed to fully log out session")

    return jsonify({"success": True, "message": "Logged out"}), 200