"""Import the 635-kindergarten dataset from a historical database snapshot.

Why a script and not a raw INSERT..SELECT
-----------------------------------------
The snapshot cannot be copied in verbatim:

* **Primary keys collide.** The snapshot holds ids 1-635; the live database already
  uses ids 1-5 for different kindergartens that own classes, children, incidents,
  attendance logs, daily reports and enrolment applications. Copying ids across
  would silently re-point every one of those foreign keys at the wrong site.
  Rows are therefore inserted with fresh ids and the snapshot ids are discarded.

* **Governorates predate `canon_gov_cap_01`.** The snapshot stores the capital as
  the city name "عمان" and, in 17 rows, stores "السلط" — a city — in the
  governorate column. Every value is normalised through
  ``services.jordan_locations`` so the imported rows match the canonical form the
  live database was migrated to.

* **Actor columns may reference users that do not exist here.** ``frozen_by`` and
  ``deleted_by`` are cleared rather than carried over.

The script is idempotent on re-run: a kindergarten is skipped when an existing row
already matches on name, district and contact phone.

Usage
-----
    python scripts/import_kindergartens_from_backup.py --source <snapshot.db> [--apply]

Without ``--apply`` it reports what it would do and changes nothing.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.jordan_locations import is_valid_governorate, normalize_governorate  # noqa: E402

LIVE_DB = os.path.join("data", "kinjo.db")

# Copied verbatim except for the transformations documented above. `id` is omitted so
# SQLite assigns a fresh one; the actor columns are omitted so they default to NULL.
_SKIPPED_COLUMNS = {"id", "frozen_by", "deleted_by"}


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute("PRAGMA table_info(kindergartens)")]


def _existing_keys(conn: sqlite3.Connection) -> set[tuple[str, str, str]]:
    """Identity used for idempotency: name + district + phone."""
    return {
        (str(n or "").strip(), str(d or "").strip(), str(p or "").strip())
        for n, d, p in conn.execute(
            "SELECT name_ar, district, contact_phone FROM kindergartens"
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="Path to the snapshot database")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry run)")
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f"source not found: {args.source}")
        return 1
    if not os.path.exists(LIVE_DB):
        print(f"live database not found: {LIVE_DB}")
        return 1

    src = sqlite3.connect(f"file:{args.source}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    live = sqlite3.connect(LIVE_DB)
    live.row_factory = sqlite3.Row

    live_cols = _columns(live)
    src_cols = _columns(src)
    shared = [c for c in live_cols if c in src_cols and c not in _SKIPPED_COLUMNS]

    dropped = sorted(set(src_cols) - set(live_cols))
    if dropped:
        print(f"columns present in the snapshot but not in the live schema (ignored): {dropped}")

    existing = _existing_keys(live)
    before = live.execute("SELECT COUNT(*) FROM kindergartens").fetchone()[0]

    rows = src.execute("SELECT * FROM kindergartens ORDER BY id").fetchall()
    to_insert: list[list] = []
    skipped_duplicate = 0
    governorate_changes: dict[tuple[str, str], int] = {}
    rejected: list[str] = []

    for row in rows:
        raw_gov = str(row["governorate"] or "").strip()
        if not is_valid_governorate(raw_gov):
            rejected.append(f"id={row['id']} governorate={raw_gov!r}")
            continue
        canonical = normalize_governorate(raw_gov)
        if canonical != raw_gov:
            governorate_changes[(raw_gov, canonical)] = (
                governorate_changes.get((raw_gov, canonical), 0) + 1
            )

        key = (
            str(row["name_ar"] or "").strip(),
            str(row["district"] or "").strip(),
            str(row["contact_phone"] or "").strip(),
        )
        if key in existing:
            skipped_duplicate += 1
            continue
        existing.add(key)

        values = []
        for col in shared:
            values.append(canonical if col == "governorate" else row[col])
        to_insert.append(values)

    print()
    print(f"snapshot rows          : {len(rows)}")
    print(f"already present (skip) : {skipped_duplicate}")
    print(f"invalid governorate    : {len(rejected)}")
    for r in rejected[:5]:
        print(f"    {r}")
    print(f"to insert              : {len(to_insert)}")
    print()
    print("governorate normalisation:")
    for (was, now), n in sorted(governorate_changes.items(), key=lambda kv: -kv[1]):
        print(f"    {was!r} -> {now!r}  x{n}")
    if not governorate_changes:
        print("    (none required)")

    if not args.apply:
        print()
        print(f"DRY RUN — live database unchanged ({before} kindergartens). Re-run with --apply.")
        return 0

    backup = f"{LIVE_DB}.backup-before-kg-import-{datetime.now():%Y%m%d-%H%M%S}"
    shutil.copy2(LIVE_DB, backup)
    print()
    print(f"backup written: {backup}")

    placeholders = ", ".join("?" for _ in shared)
    columns = ", ".join(f'"{c}"' for c in shared)
    try:
        live.execute("BEGIN")
        live.executemany(
            f"INSERT INTO kindergartens ({columns}) VALUES ({placeholders})", to_insert
        )
        live.commit()
    except Exception:
        live.rollback()
        print("insert failed — live database rolled back, backup retained")
        raise

    after = live.execute("SELECT COUNT(*) FROM kindergartens").fetchone()[0]
    print(f"kindergartens: {before} -> {after}  (+{after - before})")

    src.close()
    live.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
