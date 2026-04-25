import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from sqlalchemy import text
from auth import verify_password

db = SessionLocal()
row = db.execute(text("SELECT hashed_password FROM users WHERE username='admin'")).fetchone()
if row:
    print("Admin hash found:", row[0][:30], "...")
    print("Verify 'Admin@1234':", verify_password("Admin@1234", row[0]))
    print("Verify 'Test@1234':", verify_password("Test@1234", row[0]))
else:
    print("No admin user found!")
db.close()
