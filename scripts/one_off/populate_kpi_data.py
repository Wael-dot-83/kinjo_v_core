#!/usr/bin/env python3
"""
KPI Data Population Script
Populates RatioCompliance data for existing kindergartens
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, timedelta
from database import SessionLocal
from kpi_service import KPIService

def populate_all_ratio_compliance():
    """Populate ratio compliance data for all kindergartens"""
    db = SessionLocal()
    try:
        # Get all kindergartens
        from models import Kindergarten
        kindergartens = db.query(Kindergarten).all()

        if not kindergartens:
            print("No kindergartens found")
            return

        # Populate data for last 30 days for each kindergarten
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

        for kg in kindergartens:
            print(f"Populating ratio compliance for {kg.name_en} (ID: {kg.id})")
            try:
                KPIService.populate_ratio_compliance_for_period(db, kg.id, start_date, end_date)
                print(f"  âœ“ Completed for {kg.name_en}")
            except (RuntimeError, ValueError, TypeError, AttributeError, OSError) as e:
                print(f"  âœ— Error for {kg.name_en}: {e}")

        print("Ratio compliance data population completed")

    finally:
        db.close()

if __name__ == "__main__":
    populate_all_ratio_compliance()
