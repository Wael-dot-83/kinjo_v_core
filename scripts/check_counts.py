import os
import sys

from sqlalchemy import MetaData, Table, func, inspect, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal


db = SessionLocal()
try:
    metadata = MetaData()
    inspector = inspect(db.bind)
    print("=== Tables ===")
    for name in sorted(inspector.get_table_names()):
        if name.startswith("alembic") or name.startswith("sqlite"):
            continue
        table = Table(name, metadata, autoload_with=db.bind)
        count = db.execute(select(func.count()).select_from(table)).scalar()
        if count > 0:
            print(f"  {name}: {count}")
finally:
    db.close()
