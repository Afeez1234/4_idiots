from flask import Flask, request, jsonify
from datetime import date
import mysql.connector
from config import DB_CONFIG

app = Flask(__name__)

def connect_to_database():
    return mysql.connector.connect(**DB_CONFIG)

#reminder:: the fuction below will help find student  :)
def find_student_by_rfid(cursor, RFID_UID):
    query = "SELECT id, FULL_NAME,LEVEL,DEPARTMENT FROM students WHERE RFID_UID = %s"
    cursor.execute(query, (RFID_UID,))
    return cursor.fetchone()

#reminder:: the function below will help record attendance in the database 
def record_attendance(cursor, connection, student_id,RFID_UID,session_id):
    query = "INSERT INTO attendance (student_id, RFID_UID,session_id) VALUES (%s, %s, %s)"
    cursor.execute(query, (student_id, RFID_UID,session_id))
    connection.commit()

#reminder:: the fuction below will create a new session for the course,i'm still wondering if i shoud keep it here or put it in the endpoint
def create_session(cursor,connection,course_id,start_time,stop_time,session_date):
    query = "INSERT INTO sessions (course_id,start_time,stop_time,session_date,is_active) VALUES(%s,%s,%s,%s,1)"
    cursor.execute(query, (course_id,start_time,stop_time,session_date))
    connection.commit()

#reminder:: i'm starting to get tired of commenting but anyways just in case ,i think i'll link this to dashboard
def get_all_active_sessions(cursor):
    query = "SELECT id, course_id, start_time, stop_time, session_date FROM sessions WHERE is_active = 1"
    cursor.execute(query)
    return cursor.fetchall()

#reminder:: might use it for esp32
def get_active_session_by_course_id(cursor, course_id):
    query = "SELECT id, course_id, start_time, stop_time, session_date FROM sessions WHERE is_active = 1 AND course_id = %s ORDER BY id DESC LIMIT 1"
    cursor.execute(query, (course_id,))
    return cursor.fetchone()

def get_active_sesh(cursor):
    query = "SELECT id,course_id FROM sessions WHERE is_active = 1 ORDER BY id desc LIMIT 1"
    cursor.execute(query)
    return cursor.fetchone()

#reminder:: i think the function names says a lot
def did_student_register_course(cursor,student_id,course_id):
    query = "SELECT id FROM enrollments WHERE student_id = %s AND course_id = %s"
    cursor.execute(query, (student_id,course_id))
    return cursor.fetchone() is not None

def attendance_already_recorded(cursor,session_id,student_id):
    query = "SELECT id FROM attendance WHERE session_id =%s AND student_id = %s"
    cursor.execute(query, (session_id,student_id))
    return cursor.fetchone() is not None

@app.route('/')
def home():
    return "Welcome to the SUAAMS API"

# reminder:: the sessionstart endpoint gets the info from the dashboard that i'll create later

@app.route('/sessions/start',methods=['POST'])
def start_session():
    data = request.get_json()

    course_id = data.get('course_id')
    if not course_id:
        return jsonify({
            "error": "course_id is required"
        }), 400

    start_time = data.get('start_time')
    stop_time = data.get('stop_time')
    session_date = date.today()

    connection = connect_to_database()
    cursor = connection.cursor()
    create_session(cursor,connection,course_id,start_time,stop_time,session_date)
    return jsonify({
        "success": True,
        "message": "Session started successfully."
    }), 201

#reminder:: the sessionstop endpoint gets the info from the dashboard that i'll create later
@app.route('/sessions/active', methods=['GET'])
def get_active_sessions():
    connection = connect_to_database()
    cursor = connection.cursor()
    sessions = get_all_active_sessions(cursor)

    active_sessions = []
    for session in sessions:
        session_id, course_id, start_time, stop_time, session_date = session
        active_sessions.append({
            "id": session_id,
            "course_id": course_id,
            "start_time": start_time,
            "stop_time": stop_time,
            "session_date": session_date
        })

    return jsonify({
        "success": True,
        "active_sessions": active_sessions
    }), 200

#reminder:: aafeez,don't forget that you'll need to use this for the esp,still thinking about it
@app.route('/sessions/active/<int:course_id>', methods=['GET'])
def get_active_sessions_by_course_id(course_id):
    connection = connect_to_database()
    cursor = connection.cursor()
    session = get_active_session_by_course_id(cursor, course_id)
    if not session:
        return jsonify({
            "error": "No active session found for the given course_id."
        }), 404

    session_id, course_id, start_time, stop_time, session_date = session
    return jsonify({
        "success": True,
        "session": {
            "id": session_id,
            "course_id": course_id,
            "start_time": start_time,
            "stop_time": stop_time,
            "session_date": session_date
        }
    }), 200


#reminder:: the attendance endpoint gets the info from the esp32 (i.e the rfid uid)
@app.route('/attendance', methods=['POST'])
def attendance():
    data = request.get_json()
    RFID_UID = data.get('RFID_UID')
    if not RFID_UID:
        return jsonify({
            "error": "RFID_UID is required"
        }), 400
    connection = connect_to_database()
    cursor = connection.cursor()

    student = find_student_by_rfid(cursor, RFID_UID)
    if not student:
        return jsonify({
            "error": "No student found with that RFID UID."
        }), 404
    student_id, FULL_NAME, LEVEL, DEPARTMENT = student

    active_session = get_active_sesh(cursor)

    if not active_session:
        return jsonify({
            "error":"NO active session"
        }),404

    session_id,course_id = active_session

    if not did_student_register_course(cursor,student_id,course_id):
        return jsonify({
            "error":"Student did no register this course"
        })

    if attendance_already_recorded(cursor,session_id,student_id):
        return jsonify({
            "message":"Attendance already marked"
        })
        
    
    
    record_attendance(cursor, connection, student_id,RFID_UID ,session_id)

    return jsonify({
        "success": True,
        "message": "Attendance recorded successfully.",
        "student": {
            "id": student_id,
            "full_name": FULL_NAME,
            "level": LEVEL,
            "department": DEPARTMENT
        }
    }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)