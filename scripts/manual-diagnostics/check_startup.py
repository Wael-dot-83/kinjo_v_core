
import sys
import os

try:
    print("Attempting to import main...")
    import main
    print("Import successful.")
    print("Initializing DB...")
    from database import init_db
    init_db()
    print("DB Init successful.")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
