#!/usr/bin/env python3
"""
diagnose_server.py — KinJo server diagnostic script.

Checks:
  1. Required Python packages from requirements.txt are installed.
  2. Database connectivity via the project's database module.
  3. Whether main.py can be imported without errors.

Exits with code 1 if any critical check fails, 0 if everything passes.
"""

import importlib
import os
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

REQUIREMENTS_FILE = PROJECT_ROOT / "requirements.txt"

REQUIREMENTS_IMPORT_MAP: Dict[str, str] = {
    "fastapi": "fastapi",
    "uvicorn[standard]": "uvicorn",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "python-jose[cryptography]": "jose",
    "passlib[bcrypt]": "passlib",
    "python-multipart": "multipart",
    "slowapi": "slowapi",
    "email-validator": "email_validator",
    "psycopg2-binary": "psycopg2",
    "redis": "redis",
    "celery": "celery",
    "python-dotenv": "dotenv",
    "httpx": "httpx",
    "bleach": "bleach",
    "jinja2": "jinja2",
    "pyotp": "pyotp",
    "qrcode[pil]": "qrcode",
    "Pillow": "PIL",
    "cryptography": "cryptography",
    "supervisor": "supervisor",
    "boto3": "boto3",
    "google-genai": "google.genai",
    "numpy": "numpy",
    "scikit-learn": "sklearn",
    "pandas": "pandas",
    "plotly": "plotly",
    "psutil": "psutil",
    "requests": "requests",
    "openpyxl": "openpyxl",
    "anyio": "anyio",
    "starlette": "starlette",
    "python-json-logger": "pythonjsonlogger",
}


def parse_requirements(path: Path) -> List[str]:
    """Return package requirement strings from a requirements.txt file."""
    if not path.exists():
        return []
    packages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline comments and version specifiers for mapping lookup
        pkg = line.split("#")[0].strip()
        if not pkg:
            continue
        # Keep the requirement string as-is (with extras) for reporting,
        # but map to the importable name for the actual check.
        packages.append(pkg)
    return packages


def check_packages() -> List[str]:
    """Check each requirement; return list of missing package import paths."""
    missing = []
    requirements = parse_requirements(REQUIREMENTS_FILE)
    if not requirements:
        print("[PACKAGES] WARNING: requirements.txt not found or empty.")
        return missing

    print(f"[PACKAGES] Checking {len(requirements)} packages from {REQUIREMENTS_FILE.name}...")
    for req in requirements:
        import_name = REQUIREMENTS_IMPORT_MAP.get(req, req.split("==")[0].split(">=")[0].split("<=")[0].strip())
        # Normalize PEP 503 name for some common cases not in map
        import_name = import_name.replace("-", "_").lower()
        if req in REQUIREMENTS_IMPORT_MAP:
            import_name = REQUIREMENTS_IMPORT_MAP[req]

        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(f"{req} (import: {import_name})")
    return missing


def check_database_connection() -> Tuple[bool, str]:
    """Attempt to import the database module and run a simple connectivity test."""
    try:
        from database import get_db  # noqa: F401
    except ImportError as exc:
        return False, f"Failed to import database module: {exc}"

    try:
        from sqlalchemy import text
        from config import settings

        db = next(get_db())
        db.execute(text("SELECT 1"))
        db.close()
        return True, f"Database connection successful ({settings.DATABASE_URL})"
    except Exception as exc:
        tb = traceback.format_exc()
        return False, f"Database connection failed:\n{exc}\n{tb}"


def check_main_import() -> Tuple[bool, str]:
    """Attempt to import main.py and capture the root cause if it fails."""
    # Clear any cached main module to get a fresh import
    if "main" in sys.modules:
        del sys.modules["main"]
    for mod in list(sys.modules):
        if mod.startswith("main."):
            del sys.modules[mod]

    try:
        import main  # noqa: F401
        return True, "main.py imported successfully"
    except Exception as exc:
        tb = traceback.format_exc()
        return False, f"main.py import failed: {exc}\n{tb}"


def main():
    print("=" * 70)
    print("KinJo Server Diagnostics")
    print("=" * 70)

    all_ok = True

    # 1. Packages
    print("\n[1] PACKAGE CHECK")
    print("-" * 70)
    missing = check_packages()
    if missing:
        all_ok = False
        print(f"[FAIL] {len(missing)} package(s) missing or cannot be imported:")
        for pkg in missing:
            print(f"  - {pkg}")
    else:
        print("[PASS] All required packages are available.")

    # 2. Database
    print("\n[2] DATABASE CONNECTION CHECK")
    print("-" * 70)
    db_ok, db_msg = check_database_connection()
    if db_ok:
        print(f"[PASS] {db_msg}")
    else:
        all_ok = False
        print("[FAIL] " + db_msg.replace("\n", "\n       "))

    # 3. main.py import
    print("\n[3] MAIN.PY IMPORT CHECK")
    print("-" * 70)
    import_ok, import_msg = check_main_import()
    if import_ok:
        print(f"[PASS] {import_msg}")
    else:
        all_ok = False
        print("[FAIL] " + import_msg.replace("\n", "\n       "))

    # Summary
    print("\n" + "=" * 70)
    if all_ok:
        print("RESULT: ALL CHECKS PASSED — server appears ready")
        sys.exit(0)
    else:
        print("RESULT: ONE OR MORE CHECKS FAILED — see details above")
        sys.exit(1)


if __name__ == "__main__":
    main()
