from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    # Check users
    result = db.execute(text('SELECT id, username, role, kindergarten_id FROM users'))
    users = result.fetchall()
    print('Users:')
    for user in users:
        print(f'  {user[0]}: {user[1]} ({user[2]}) - KG: {user[3]}')

    # Check enrollments for KG 3
    result = db.execute(text('SELECT parent_id FROM enrollment_applications WHERE kindergarten_id = 3 AND status = "ACCEPTED"'))
    enrollments = result.fetchall()
    print('Enrolled parents in KG 3:', [e[0] for e in enrollments])

except Exception as e:
    print('Error:', e)
finally:
    db.close()