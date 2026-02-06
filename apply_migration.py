from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    print("Applying migration to add missing columns to messages table...")
    
    # Add target_mode
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN target_mode VARCHAR(50)"))
        print("Added target_mode")
    except Exception as e:
        print(f"target_mode error (might exist): {e}")

    # Add target_roles (JSON)
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN target_roles TEXT")) # SQLite JSON is TEXT
        print("Added target_roles")
    except Exception as e:
        print(f"target_roles error: {e}")

    # Add target_governorates (JSON)
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN target_governorates TEXT"))
        print("Added target_governorates")
    except Exception as e:
        print(f"target_governorates error: {e}")

    # Add target_kindergarten_ids (JSON)
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN target_kindergarten_ids TEXT"))
        print("Added target_kindergarten_ids")
    except Exception as e:
        print(f"target_kindergarten_ids error: {e}")

    # Add target_search
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN target_search VARCHAR(255)"))
        print("Added target_search")
    except Exception as e:
        print(f"target_search error: {e}")

    # Add recipient_count
    try:
        db.execute(text("ALTER TABLE messages ADD COLUMN recipient_count INTEGER"))
        print("Added recipient_count")
    except Exception as e:
        print(f"recipient_count error: {e}")

    db.commit()
    print("Migration complete!")

except Exception as e:
    print(f"Migration Failed: {e}")
    db.rollback()
finally:
    db.close()
