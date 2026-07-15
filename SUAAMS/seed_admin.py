from app import app
from models import db, User
import bcrypt

def seed_admin():
    with app.app_context():
        existing = User.query.filter_by(username='admin').first()
        if existing:
            print('Admin already exists. Skipping.')
            return
        hashed = bcrypt.hashpw('admin1234'.encode(), bcrypt.gensalt()).decode()
        admin = User(username='admin', password_hash=hashed, role='admin', is_active=True)
        db.session.add(admin)
        db.session.commit()
        print('Admin created successfully.')

if __name__ == '__main__':
    seed_admin()