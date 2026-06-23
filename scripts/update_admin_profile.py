import sqlite3, sys

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect("data/kinjo.db")
cur = con.cursor()
cur.execute(
    "UPDATE users SET full_name=? WHERE role=?",
    ("وزارة التنمية الاجتماعية الاردن", "ADMIN"),
)
con.commit()
rows = cur.execute(
    "SELECT id, username, role, full_name FROM users WHERE role='ADMIN'"
).fetchall()
for r in rows:
    print(r)
con.close()
print("Done.")
