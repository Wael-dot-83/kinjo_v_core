import sqlite3

conn = sqlite3.connect('kinjo_dev.db')
cursor = conn.cursor()

# Check if tasks table exists
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
result = cursor.fetchone()

if result:
    print("Tasks table exists!")

    # Get table schema
    cursor.execute("PRAGMA table_info(tasks)")
    columns = cursor.fetchall()

    print("\nTable columns:")
    for col in columns:
        print(f"  {col[1]} - {col[2]}")

    # Count tasks
    cursor.execute("SELECT COUNT(*) FROM tasks")
    count = cursor.fetchone()[0]
    print(f"\nTotal tasks: {count}")

    if count > 0:
        cursor.execute("SELECT id, title, status, priority FROM tasks LIMIT 5")
        tasks = cursor.fetchall()
        print("\nSample tasks:")
        for task in tasks:
            print(f"  [{task[0]}] {task[1]} - {task[2]} ({task[3]})")
else:
    print("Tasks table does NOT exist!")

conn.close()
