from database import get_db
from sqlalchemy import text

db = next(get_db())
try:
    result = db.execute(text('SELECT name FROM sqlite_master WHERE type="table" AND name="message_recipients"'))
    if result.fetchone():
        print('MessageRecipient table exists')
        # Check columns
        result = db.execute(text('PRAGMA table_info(message_recipients)'))
        columns = result.fetchall()
        print('Columns:', [col[1] for col in columns])
    else:
        print('MessageRecipient table does not exist')

    # Check messages table
    result = db.execute(text('SELECT name FROM sqlite_master WHERE type="table" AND name="messages"'))
    if result.fetchone():
        print('Messages table exists')
        result = db.execute(text('PRAGMA table_info(messages)'))
        columns = result.fetchall()
        print('Messages columns:', [col[1] for col in columns])
    else:
        print('Messages table does not exist')

except Exception as e:
    print('Error:', e)
finally:
    db.close()