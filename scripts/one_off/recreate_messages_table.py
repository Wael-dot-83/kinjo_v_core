from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    print("Recreating messages table to fix schema issues...")

    # 1. Create a backup of the existing table data
    db.execute(text("CREATE TABLE messages_backup AS SELECT * FROM messages"))
    print("Created backup table messages_backup")

    # 2. Drop the old table
    db.execute(text("DROP TABLE messages"))
    print("Dropped old messages table")

    # 3. Create the new table with the CORRECT schema
    # Based on models.py
    create_sql = """
    CREATE TABLE messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        thread_type VARCHAR(50) NOT NULL,
        sender_id INTEGER NOT NULL,
        recipient_id INTEGER,
        thread_id INTEGER,
        reply_to_id INTEGER,
        kindergarten_id INTEGER,
        subject VARCHAR(255),
        message_body TEXT NOT NULL,
        translated_text TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        allow_replies BOOLEAN NOT NULL DEFAULT 1,
        target_mode VARCHAR(50),
        target_roles TEXT,
        target_governorates TEXT,
        target_kindergarten_ids TEXT,
        target_search VARCHAR(255),
        recipient_count INTEGER,
        FOREIGN KEY(sender_id) REFERENCES users (id),
        FOREIGN KEY(recipient_id) REFERENCES users (id),
        FOREIGN KEY(thread_id) REFERENCES messages (id),
        FOREIGN KEY(reply_to_id) REFERENCES messages (id),
        FOREIGN KEY(kindergarten_id) REFERENCES kindergartens (id)
    )
    """
    db.execute(text(create_sql))
    print("Created new messages table with correct schema")

    # 4. Create Indexes (matching models.py)
    db.execute(text("CREATE INDEX ix_messages_id ON messages (id)"))
    db.execute(text("CREATE INDEX ix_messages_sender_id ON messages (sender_id)"))
    db.execute(text("CREATE INDEX ix_messages_recipient_id ON messages (recipient_id)"))
    db.execute(text("CREATE INDEX ix_messages_thread_id ON messages (thread_id)"))
    db.execute(text("CREATE INDEX ix_messages_kindergarten_created_at ON messages (kindergarten_id, created_at)"))
    print("Created indexes")

    # 5. Restore data (if columns match)
    # We only restore columns that exist in the backup and the new table
    # This ensures we don't fail if the backup has weird columns or is missing new ones
    try:
        # Get columns from backup
        res = db.execute(text("PRAGMA table_info(messages_backup)"))
        backup_cols = [r[1] for r in res.fetchall()]
        
        # New columns 
        new_cols = ['id', 'thread_type', 'sender_id', 'recipient_id', 'thread_id', 'reply_to_id', 
                    'kindergarten_id', 'subject', 'message_body', 'translated_text', 'created_at', 
                    'allow_replies', 'target_mode', 'target_roles', 'target_governorates', 
                    'target_kindergarten_ids', 'target_search', 'recipient_count']
        
        common_cols = [c for c in new_cols if c in backup_cols]
        cols_str = ", ".join(common_cols)
        
        if common_cols:
            db.execute(text(f"INSERT INTO messages ({cols_str}) SELECT {cols_str} FROM messages_backup"))
            print(f"Restored data for columns: {cols_str}")
        else:
            print("No common columns found, table left empty.")
            
    except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
        print(f"Restore failed (might be empty/incompatible): {e}")

    # 6. Cleanup backup
    db.execute(text("DROP TABLE messages_backup"))
    print("Dropped backup table")

    db.commit()
    print("Migration complete!")

except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
    print(f"Migration Failed: {e}")
    db.rollback()
finally:
    db.close()

