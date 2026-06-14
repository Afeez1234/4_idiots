import serial
import mysql.connector

from mysql.connector import Error
from datetime import date
from suaams_Api.config import DB_CONFIG, SERIAL_PORT, BAUD_RATE        

def connect_to_database():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            print("Connected to the database")
            return connection
    except Error as e:
        print(f"Error connecting to database: {e}")
        return None

def find_student_by_rfid(cursor, RFID_UID):
    query = "SELECT id, FULL_NAME,LEVEL,DEPARTMENT FROM students WHERE RFID_UID = %s"
    cursor.execute(query, (RFID_UID,))
    return cursor.fetchone()

def record_attendance(cursor, connection, student_id,RFID_UID):
    
    query = "INSERT INTO attendance (student_id, RFID_UID) VALUES (%s, %s)"
    cursor.execute(query, (student_id, RFID_UID))
    connection.commit()

def main():
    connection = connect_to_database()
    if not connection:
        return

    cursor = connection.cursor()

    try:
        arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"Listening for RFID scans on {SERIAL_PORT} at {BAUD_RATE} baud rate...")
        
        while True:
            if arduino.in_waiting > 0:
                RFID_UID = arduino.readline().decode('utf-8').strip()
                
                print(f"RFID UID read: {RFID_UID}")

                student = find_student_by_rfid(cursor, RFID_UID)
                if student:
                    student_id, FULL_NAME, LEVEL, DEPARTMENT = student
                    print(f"""
                        Student Found:
                        Name: {FULL_NAME}
                        Department: {DEPARTMENT}
                        Level: {LEVEL} """)

                    record_attendance(cursor, connection, student_id, RFID_UID)
                    print("Attendance recorded successfully.")
                else:
                    print("No student found with that RFID UID.")
    except serial.SerialException as e:
        print(f"Serial error: {e}")
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()
            print("Database connection closed.")

if __name__ == "__main__":
    main()