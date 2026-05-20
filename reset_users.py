"""
reset_users.py  --  Wipe ALL user accounts and recreate the three dev sets.

Accounts created
----------------
  WAEL       (password 0790337512)
    ADMIN       : admin-wael
    MANAGER     : manager-wael
    SUPERVISOR  : wael-supervisor
    PARENT      : wael

  SUYLEYMAN  (password 0778003268)
    ADMIN       : admin-suyleyman
    MANAGER     : manager-suyleyman
    SUPERVISOR  : suyleyman-supervisor
    PARENT      : suyleyman

  MAMOON     (password 0798282438)
    ADMIN       : admin-mamoon
    MANAGER     : manager-mamoon
    SUPERVISOR  : mamoon-supervisor
    PARENT      : mamoon

Run from the project root (venv must be active):
    python reset_users.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import bcrypt
from sqlalchemy import text
from database import SessionLocal, init_db
from models import Kindergarten, KindergartenStatus, UserRole


def _hash(password: str) -> str:
    """Hash without enforcing production complexity rules (dev seed only)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode()

# ---------------------------------------------------------------------------
# Account definitions  (username, email, plain_password, role)
# ---------------------------------------------------------------------------
ACCOUNTS = [
    # --- Wael ---
    ("admin-wael",           "admin-wael@kinjo.jo",           "0790337512", UserRole.ADMIN),
    ("manager-wael",         "manager-wael@kinjo.jo",         "0790337512", UserRole.MANAGER),
    ("wael-supervisor",      "wael-supervisor@kinjo.jo",      "0790337512", UserRole.SUPERVISOR),
    ("wael",                 "wael@kinjo.jo",                 "0790337512", UserRole.PARENT),
    # --- Suyleyman ---
    ("admin-suyleyman",      "admin-suyleyman@kinjo.jo",      "0778003268", UserRole.ADMIN),
    ("manager-suyleyman",    "manager-suyleyman@kinjo.jo",    "0778003268", UserRole.MANAGER),
    ("suyleyman-supervisor", "suyleyman-supervisor@kinjo.jo", "0778003268", UserRole.SUPERVISOR),
    ("suyleyman",            "suyleyman@kinjo.jo",            "0778003268", UserRole.PARENT),
    # --- Mamoon ---
    ("admin-mamoon",         "admin-mamoon@kinjo.jo",         "0798282438", UserRole.ADMIN),
    ("manager-mamoon",       "manager-mamoon@kinjo.jo",       "0798282438", UserRole.MANAGER),
    ("mamoon-supervisor",    "mamoon-supervisor@kinjo.jo",    "0798282438", UserRole.SUPERVISOR),
    ("mamoon",               "mamoon@kinjo.jo",               "0798282438", UserRole.PARENT),
]

# Roles that require a kindergarten_id (DB constraint enforces MANAGER)
ROLES_NEEDING_KG = {UserRole.MANAGER, UserRole.SUPERVISOR}


def run():
    init_db()
    db = SessionLocal()
    try:
        # ── 1. Wipe all users and dependent rows ─────────────────────────────
        print("=" * 60)
        print("STEP 1 : Removing all existing users ...")
        print("=" * 60)
        # Disable FK enforcement in SQLite so we can delete freely
        db.execute(text("PRAGMA foreign_keys = OFF"))
        db.execute(text("DELETE FROM users"))
        db.execute(text("PRAGMA foreign_keys = ON"))
        db.commit()
        print("  Done - users table cleared.\n")

        # ── 2. Ensure at least one active kindergarten exists ────────────────
        #       (MANAGER rows must have kindergarten_id per DB constraint)
        print("=" * 60)
        print("STEP 2 : Resolving kindergarten for manager/supervisor ...")
        print("=" * 60)
        kg = (
            db.query(Kindergarten)
            .filter(Kindergarten.status == KindergartenStatus.ACTIVE)
            .first()
        )
        if not kg:
            kg = Kindergarten(
                name_ar="روضة الأمل",
                name_en="Al Amal Kindergarten",
                governorate="عمان",
                city="عمان",
                area="الجبيهة",
                address_line="شارع الجامعة الأردنية",
                contact_phone="0791234567",
                status=KindergartenStatus.ACTIVE,
            )
            db.add(kg)
            db.commit()
            db.refresh(kg)
            print(f"  Created default kindergarten (id={kg.id})")
        else:
            print(f"  Using existing kindergarten '{kg.name_en}' (id={kg.id})")
        print()

        # ── 3. Insert new accounts ───────────────────────────────────────────
        print("=" * 60)
        print("STEP 3 : Creating accounts ...")
        print("=" * 60)

        prev_person = ""
        for username, email, password, role in ACCOUNTS:
            # Print a blank line between person groups
            person = username.split("-")[-1] if "-" in username else username
            if person not in ("wael", "suyleyman", "mamoon"):
                person = username
            if person != prev_person:
                print()
            prev_person = person

            kg_id = kg.id if role in ROLES_NEEDING_KG else None
            db.execute(
                text(
                    "INSERT INTO users "
                    "  (username, email, hashed_password, role, status, "
                    "   kindergarten_id, must_change_password, failed_login_count) "
                    "VALUES "
                    "  (:u, :e, :h, :r, 'ACTIVE', :kg, 0, 0)"
                ),
                {
                    "u":  username,
                    "e":  email,
                    "h":  _hash(password),
                    "r":  role.value,
                    "kg": kg_id,
                },
            )
            db.commit()
            print(f"  [{role.value:<12}]  {username:<28}  pw={password}")

        print()
        print("=" * 60)
        print("All accounts created successfully.")
        print("=" * 60)

    except Exception as exc:
        db.rollback()
        print(f"\nERROR: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run()
