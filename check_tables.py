import sqlite3
import os

db_path = os.path.join(os.getcwd(), 'data', 'kinjo.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print('All Tables:', sorted(tables))

# Check analytics tables specifically
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name LIKE '%analytics%' OR name LIKE '%export%' OR name LIKE '%kpi%' OR name LIKE '%cache%');")
analytics_tables = [row[0] for row in cursor.fetchall()]
print('Analytics/Cache/Export/KPI Tables:', analytics_tables)

conn.close()