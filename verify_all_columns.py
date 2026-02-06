from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    print("--- MESSAGES COLUMNS ---")
    result = db.execute(text("PRAGMA table_info(messages)"))
    columns = [row[1] for row in result.fetchall()]
    for col in columns:
        print(f"COLUMN: {col}")
    print("------------------------")
except Exception as e:
    print(f"Error: {e}")
finally:
    db.close()
