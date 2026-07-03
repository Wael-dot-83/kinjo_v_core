import sys
sys.path.insert(0, ".")
from main import app

included = [r for r in app.routes if type(r).__name__ in ("_IncludedRouter", "Include", "Mount")]
print(f"Include/Mount objects: {len(included)}")
for r in included:
    print(f"  type={type(r).__name__} path={getattr(r, 'path', 'N/A')}")
    for attr in dir(r):
        if not attr.startswith('_'):
            try:
                val = getattr(r, attr)
                if not callable(val):
                    print(f"    {attr} = {type(val).__name__}: {repr(val)[:200]}")
            except Exception:
                pass
    print()
