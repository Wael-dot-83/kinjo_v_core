from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    # Check enrollments for KG 5
    result = db.execute(text("SELECT ea.id, ea.child_id, ea.status, c.parent_id FROM enrollment_applications ea JOIN children c ON ea.child_id = c.id WHERE ea.kindergarten_id = 5 AND ea.status = 'ACCEPTED'"))
    enrollments = result.fetchall()
    print('Accepted enrollments in KG 5:')
    for e in enrollments:
        print(f'  Enrollment {e[0]}: Child {e[1]}, Status {e[2]}, Parent {e[3]}')

    # Check if parents exist
    if enrollments:
        parent_ids = [e[3] for e in enrollments]
        if parent_ids:
            # Simple approach for debugging
            parent_ids_str = ','.join(map(str, parent_ids))
            result = db.execute(text(f"SELECT id, username, role FROM users WHERE id IN ({parent_ids_str})"))
            parents = result.fetchall()
            print('Parent users:')
            for p in parents:
                print(f'  User {p[0]}: {p[1]} ({p[2]})')
        else:
            print('No parent IDs found')
    else:
        print('No accepted enrollments found in KG 5')

except Exception as e:
    print('Error:', e)
finally:
    db.close()