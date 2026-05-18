from database import get_db
from sqlalchemy import text

db = next(get_db())
columns_to_add = [
    ("thread_type", "VARCHAR(50)"),
    ("thread_id", "INTEGER"),
    ("reply_to_id", "INTEGER"),
    ("recipient_id", "INTEGER"),
    ("kindergarten_id", "INTEGER"),
    ("translated_text", "TEXT"),
    ("target_mode", "VARCHAR(50)"),
    ("target_roles", "TEXT"),
    ("target_governorates", "TEXT"),
    ("target_kindergarten_ids", "TEXT"),
    ("target_search", "VARCHAR(255)"),
    ("recipient_count", "INTEGER"),
    ("allow_replies", "BOOLEAN DEFAULT 1")
]

print("Applying blind migration...")
for col_name, col_type in columns_to_add:
    try:
        db.execute(text(f"ALTER TABLE messages ADD COLUMN {col_name} {col_type}"))
        print(f"Added {col_name}")
    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        # Ignore "duplicate column name" error
        if "duplicate column" not in str(e).lower():
            print(f"Error adding {col_name}: {e}")
        else:
            print(f"Column {col_name} already exists.")

try:
    db.commit()
    print("Migration committed.")
except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    print(f"Commit failed: {e}")
    db.rollback()
finally:
    db.close()

