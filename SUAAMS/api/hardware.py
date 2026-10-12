# What is left of the old MFRC522/RFID-card terminal's routes.
#
# They used to live here too: POST /attendance (record attendance from a
# card UID) and GET /sessions/active[/<course_id>]. They were removed on
# 2026-10-12. Nothing calls them any more -- the phone-tap terminal
# (SUAAMS_HCE.ino) uses /api/v1/student/checkin -- and /attendance kept
# alive the old "credit the newest active session in ANY course" rule that
# the signed-code design exists to prevent (a tap at a room-A door could
# count for a room-B class). The retired card sketches in
# ESP32_ARDUINO CODE/SUAAMS_ESP and SUAAMS_ still point at /attendance and
# will get a 404; they are kept for reference only.
from flask import Blueprint, redirect, url_for

api_hardware_bp = Blueprint('api_hardware', __name__)


# The site root sends visitors to the login page.
@api_hardware_bp.route('/')
def home():
    return redirect(url_for('auth.login'))
