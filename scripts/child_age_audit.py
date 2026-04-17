#!/usr/bin/env python3
"""
Audit and optionally remediate children outside the allowed age range.

Usage:
  python scripts/child_age_audit.py --dry-run
  python scripts/child_age_audit.py --withdraw-enrollments
"""
from datetime import date
import argparse

from sqlalchemy.orm import Session

import models
from database import SessionLocal
from child_age_policy import (
    get_child_age_bounds,
    calculate_age_days,
    calculate_age_months,
)
from config import settings


def fetch_out_of_range_children(db: Session):
    bounds = get_child_age_bounds(date.today())
    return db.query(models.Child).execution_options(
        include_out_of_range_children=True
    ).filter(
        (models.Child.date_of_birth < bounds.min_date)
        | (models.Child.date_of_birth > bounds.max_date)
    ).all(), bounds


def withdraw_active_enrollments(db: Session, child_ids: list[int]) -> int:
    if not child_ids:
        return 0

    active_statuses = set(settings.ACTIVE_LIKE_ENROLLMENT_STATUSES)
    enrollments = db.query(models.EnrollmentApplication).filter(
        models.EnrollmentApplication.child_id.in_(child_ids),
        models.EnrollmentApplication.status.in_(active_statuses),
    ).all()

    for enrollment in enrollments:
        enrollment.status = models.EnrollmentStatus.WITHDRAWN
        enrollment.enrollment_end_date = date.today()
    return len(enrollments)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit child age constraints.")
    parser.add_argument("--withdraw-enrollments", action="store_true", help="Withdraw active enrollments for out-of-range children.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes.")
    args = parser.parse_args()

    db: Session = SessionLocal()
    if args.withdraw_enrollments and not args.dry_run:
        db.info["skip_child_age_policy"] = True

    try:
        children, bounds = fetch_out_of_range_children(db)
        print(f"Allowed DOB range: {bounds.min_date.isoformat()} .. {bounds.max_date.isoformat()}")
        print(f"Out-of-range children: {len(children)}")

        for child in children:
            age_days = calculate_age_days(child.date_of_birth)
            age_months = calculate_age_months(child.date_of_birth)
            print(
                f"- Child {child.id}: {child.first_name} {child.last_name} | DOB={child.date_of_birth} | "
                f"{age_days} days, {age_months} months"
            )

        if args.withdraw_enrollments:
            if args.dry_run:
                print("Dry-run: no changes applied.")
            else:
                updated = withdraw_active_enrollments(db, [c.id for c in children])
                db.commit()
                print(f"Withdrawn enrollments: {updated}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
