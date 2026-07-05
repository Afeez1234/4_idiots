import bcrypt
import mysql.connector
from config import DB_CONFIG

# this will help us to create an admin user if it doesn't exist already. we can run this script once after setting up the database to ensure we have an admin user to log in with. the password is set to "admin1234" but i might change it to something cooler

def seed_admin():
    
    password = "admin1234"
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes,salt)
    
    connection = mysql.connector.connect(**DB_CONFIG)
    cursor = connection.cursor()
    
    cursor.execute("SELECT id from users where username = 'admin'")
    existing = cursor.fetchone()
    
    if existing:
        print('Admin User already exists. skipping')
    else:
        query = "insert into users(username,password_hash,role,is_active) values (%s,%s,%s,%s)"
        cursor.execute(query, ('admin',hashed_password,'admin',1))
        connection.commit()
        print('Admin user created successfully')
        
    cursor.close()
    connection.close()
    
if __name__ == '__main__':
    seed_admin()