from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    print("Checking messages table columns...")
    result = db.execute(text("PRAGMA table_info(messages)"))
    columns = [row[1] for row in result.fetchall()]
    print(f"Existing columns: {columns}")
    
    needed = ['target_roles', 'target_governorates', 'target_kindergarten_ids', 'target_mode', 'recipient_count']
    missing = [c for c in needed if c not in columns]
    
    if missing:
        print(f"MISSING COLUMNS: {missing}")
    else:
        print("All columns present.")
        
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
