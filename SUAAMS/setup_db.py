import mysql.connector
from config import DB_CONFIG

#judst testing thid festure


def create_tables():
    # Connect without specifying a database first so we can create it if it doesn't exist.
    connection = mysql.connector.connect(
        host=DB_CONFIG['host'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password'],
    )
    cursor = connection.cursor()

    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
    cursor.execute(f"USE {DB_CONFIG['database']}")

    # 1. users — no dependencies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role ENUM('admin', 'lecturer', 'student') NOT NULL,
            is_active TINYINT(1) DEFAULT 1
        )
    ''')

    # 2. students — depends on users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INT AUTO_INCREMENT PRIMARY KEY,
            FULL_NAME VARCHAR(150) NOT NULL,
            MATRIC_NUMBER VARCHAR(50) NOT NULL UNIQUE,
            DEPARTMENT VARCHAR(100),
            LEVEL VARCHAR(20),
            RFID_UID VARCHAR(50) UNIQUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 3. lecturers — depends on users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lecturers (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(150) NOT NULL,
            staff_id VARCHAR(50) NOT NULL UNIQUE,
            department VARCHAR(100),
            user_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')

    # 4. courses — depends on lecturers
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_title VARCHAR(150) NOT NULL,
            course_code VARCHAR(20) NOT NULL UNIQUE,
            lecturer_id INT,
            FOREIGN KEY (lecturer_id) REFERENCES lecturers(id)
        )
    ''')

    # 5. sessions — depends on courses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            course_id INT,
            start_time TIME,
            stop_time TIME,
            session_date DATE,
            is_active TINYINT(1) DEFAULT 0,
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    ''')

    # 6. enrollments — depends on students and courses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS enrollments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            course_id INT,
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (course_id) REFERENCES courses(id)
        )
    ''')

    # 7. attendance — depends on students and sessions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            session_id INT,
            TIME_IN TIME DEFAULT (CURRENT_TIME),
            status VARCHAR(20) DEFAULT 'present',
            FOREIGN KEY (student_id) REFERENCES students(id),
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    ''')

    connection.commit()
    cursor.close()
    connection.close()
    print("Database and tables created successfully.")

if __name__ == '__main__':
    create_tables()