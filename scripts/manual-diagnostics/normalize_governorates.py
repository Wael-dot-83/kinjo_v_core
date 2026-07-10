"""Data migration script to normalize governorate values in the database.

This script:
1. Scans all kindergartens for non-canonical governorate values
2. Normalizes them using services/jordan_locations.py
3. Reports what would be changed (dry-run by default)
4. With --apply flag, actually updates the database

Special handling:
- 'غير محدد' (not specified) -> left as-is (requires human review)
- City names stored as governorate (e.g. 'الرمثا') -> set to parent governorate (e.g. 'إربد')
- 'X', 'cols', etc. -> left as-is (requires human review)

Run with:
  python scripts/manual-diagnostics/normalize_governorates.py            # dry run
  python scripts/manual-diagnostics/normalize_governorates.py --apply    # apply changes
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

# Ensure project root is on sys.path so absolute imports like `from database import ...` work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from sqlalchemy.orm import Session

from database import SessionLocal
from models import Kindergarten
from services.jordan_locations import (
    normalize_governorate,
    is_valid_governorate,
    get_all_governorates,
    get_areas_for_governorate,
)


def build_area_to_governorate_map() -> dict[str, str]:
    """Build a map from area name to governorate Arabic name."""
    area_to_gov: dict[str, str] = {}
    for g in get_all_governorates():
        for area in get_areas_for_governorate(g["key"]):
            area_to_gov[area["name_ar"]] = g["name_ar"]
    return area_to_gov


def scan_governorates(db: Session) -> dict[str, list[dict]]:
    """Scan all kindergartens and group by raw governorate value."""
    rows = db.query(Kindergarten.id, Kindergarten.name_ar, Kindergarten.governorate, Kindergarten.district).all()
    by_value: dict[str, list[dict]] = defaultdict(list)
    for kg_id, name_ar, gov, district in rows:
        if gov:
            by_value[gov].append({
                "id": kg_id,
                "name_ar": name_ar,
                "governorate": gov,
                "district": district,
            })
    return dict(by_value)


def normalize_value(raw: str, area_to_gov: dict[str, str]) -> tuple[str | None, str | None]:
    """Normalize a raw governorate value.
    
    Returns (normalized_governorate, reason).
    normalized_governorate is None if the value cannot be safely normalized.
    """
    # Skip explicit "not specified" values
    if raw.strip() in ("غير محدد", "N/A", "NA", ""):
        return None, "explicitly unspecified"
    
    # Check if it's already a valid canonical governorate
    if is_valid_governorate(raw):
        return normalize_governorate(raw), "already canonical"
    
    # Check if it's a city/area name that was stored as governorate
    if raw in area_to_gov:
        return area_to_gov[raw], "city stored as governorate"
    
    # Try general normalization
    normalized = normalize_governorate(raw)
    if normalized and is_valid_governorate(normalized):
        return normalized, "alias normalized"
    
    return None, "unknown/invalid"


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize governorate values in DB")
    parser.add_argument("--apply", action="store_true", help="Actually update the database")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        by_value = scan_governorates(db)
        area_to_gov = build_area_to_governorate_map()
        canonical_set = {g["name_ar"] for g in get_all_governorates()}

        print(f"Total kindergartens scanned: {sum(len(v) for v in by_value.values())}")
        print(f"Unique raw governorate values: {len(by_value)}")
        print()

        issues = []
        for raw, kgs in sorted(by_value.items()):
            normalized, reason = normalize_value(raw, area_to_gov)
            if normalized is None:
                issues.append({
                    "raw": raw,
                    "normalized": None,
                    "count": len(kgs),
                    "kgs": kgs,
                    "reason": reason,
                })
            elif normalized != raw:
                issues.append({
                    "raw": raw,
                    "normalized": normalized,
                    "count": len(kgs),
                    "kgs": kgs,
                    "reason": reason,
                })

        if not issues:
            print("No issues found. All governorate values are canonical.")
            return 0

        print(f"Issues found: {len(issues)}")
        print("=" * 80)
        for issue in issues:
            print(f"Raw: {issue['raw']!r}")
            print(f"  Normalized: {issue['normalized']!r}")
            print(f"  Reason: {issue['reason']}")
            print(f"  Count: {issue['count']}")
            for kg in issue["kgs"][:5]:
                print(f"    - KG #{kg['id']}: {kg['name_ar']} (district: {kg['district']!r})")
            if len(issue["kgs"]) > 5:
                print(f"    ... and {len(issue['kgs']) - 5} more")
            print()

        if not args.apply:
            print("DRY RUN — no changes made. Re-run with --apply to update.")
            return 0

        print("APPLYING CHANGES...")
        updated = 0
        for issue in issues:
            if issue["normalized"] is None:
                print(f"  SKIP {issue['reason']}: {issue['raw']!r}")
                continue
            kg_ids = [kg["id"] for kg in issue["kgs"]]
            db.query(Kindergarten).filter(Kindergarten.id.in_(kg_ids)).update(
                {Kindergarten.governorate: issue["normalized"]},
                synchronize_session=False,
            )
            updated += len(kg_ids)
            print(f"  UPDATED {len(kg_ids)} records: {issue['raw']!r} -> {issue['normalized']!r}")

        db.commit()
        print(f"\nCommitted {updated} updates.")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
