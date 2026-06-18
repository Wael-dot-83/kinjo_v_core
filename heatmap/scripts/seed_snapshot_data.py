"""
Database seeder for the Jordan Heat Map.

Inserts the 12 Jordan governorates into the `governorate` table and runs the
daily ETL pipeline for the last `days` days so that the correlation and
regression engines have real historical data to work with.

Designed to be run against any SQLAlchemy-compatible database:
    python -m heatmap.scripts.seed_snapshot_data --days 90

For tests, use `seed_in_memory_session` to get a populated in-memory session.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Allow running this script directly from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from heatmap.backend import pipeline  # noqa: E402
from heatmap.backend.constants import GOVERNORATES  # noqa: E402
from database import Base  # noqa: E402
import models  # noqa: E402

logger = logging.getLogger(__name__)


def seed_governorates(db) -> int:
    """Insert the 12 Jordan governorates into the `governorate` table."""
    count = 0
    for gov in GOVERNORATES:
        existing = (
            db.query(models.Governorate)
            .filter(models.Governorate.code == gov["code"])
            .one_or_none()
        )
        if existing is None:
            db.add(models.Governorate(
                code=gov["code"],
                slug=gov["slug"],
                name_en=gov["name_en"],
                name_ar=gov["name_ar"],
                center_lon=float(gov["center"][0]),
                center_lat=float(gov["center"][1]),
                display_order=gov["display_order"],
                active=True,
            ))
            count += 1
    db.commit()
    return count


def seed_snapshot_data(days: int = 90, end_date: Optional[date] = None) -> dict:
    """
    Seed `days` days of snapshots for all 12 governorates.

    Returns a summary dict {governorates_added, days_processed, ...}.
    """
    from database import SessionLocal
    db = SessionLocal()
    try:
        gov_added = seed_governorates(db)
        logger.info("Seeded %d governorates", gov_added)
        result = pipeline.backfill(db, days=days, end_date=end_date)
        result["governorates_added"] = gov_added
        return result
    finally:
        db.close()


def seed_in_memory_session(days: int = 90, end_date: Optional[date] = None):
    """
    Create an in-memory SQLite database with the schema applied, the 12
    governorates seeded, and the last `days` days of pipeline snapshots.
    Returns a SQLAlchemy session ready for use in tests.
    """
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Create the schema (only the snapshot tables + users for FK)
    # In a real DB these would already exist; for the test fixture we
    # create them so the pipeline can run.
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = Session_()
    try:
        # Apply any schema-constraint migrations that Base.create_all can't
        # infer (CHECK constraints on PostgreSQL types, for example).  For
        # the in-memory test fixture, the constraint definitions in the
        # SQLAlchemy model are sufficient.
        seed_governorates(db)
        pipeline.backfill(db, days=days, end_date=end_date)
        db.commit()
        return db, engine
    finally:
        # Caller is responsible for closing the session
        pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Jordan Heat Map snapshot data")
    parser.add_argument("--days", type=int, default=90, help="Number of days of history to generate")
    parser.add_argument("--end-date", type=date.fromisoformat, default=None, help="End date (default: today)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    result = seed_snapshot_data(days=args.days, end_date=args.end_date)
    print(f"Seeded: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())