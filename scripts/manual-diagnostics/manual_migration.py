import sqlite3

# Connect to database
conn = sqlite3.connect('kinjo_dev.db')
cursor = conn.cursor()

# Get table schema
cursor.execute("PRAGMA table_info(kindergartens)")
columns = cursor.fetchall()

print("Kindergartens table schema:")
for col in columns:
    cid, name, dtype, notnull, default_val, pk = col
    nullable_str = "NOT NULL" if notnull else "NULL"
    print(f"  {name}: {dtype} {nullable_str}")

print("\nExecuting direct SQLAlter...")

# Create new table with nullable email
cursor.execute("""
CREATE TABLE kindergartens_new (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    name_ar VARCHAR(255) NOT NULL,
    name_en VARCHAR(255),
    governorate VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    area VARCHAR(100) NOT NULL,
    address_line TEXT NOT NULL,
    contact_phone VARCHAR(20) NOT NULL,
    contact_email VARCHAR(255),
    status VARCHAR(10) NOT NULL DEFAULT 'DRAFT',
    working_hours_start VARCHAR(5),
    working_hours_end VARCHAR(5),
    license_number VARCHAR(100),
    license_valid_until DATE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
)
""")

# Copy data
cursor.execute("""
INSERT INTO kindergartens_new 
SELECT * FROM kindergartens
""")

# Drop old table
cursor.execute("DROP TABLE kindergartens")

# Rename new table
cursor.execute("ALTER TABLE kindergartens_new RENAME TO kindergartens")

conn.commit()
conn.close()

print("\n✅ Migration complete! contact_email is now nullable.")
