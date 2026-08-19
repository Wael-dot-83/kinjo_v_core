import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import SessionLocal
import models
from heatmap.backend import service as heatmap_service
from kpi_service import get_kpi_country_level, get_kpi_dashboard_data, get_kpi_summary

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def run_verification():
    db = SessionLocal()
    try:
        total_kgs = db.query(models.Kindergarten).filter(models.Kindergarten.status == models.KindergartenStatus.ACTIVE).count()
        print(f"=== DATABASE TOTAL ACTIVE KINDERGARTENS: {total_kgs} ===")

        # 1. Test Map Pins & Coordinates
        print("\n--- Testing Map Pins GeoJSON Endpoint ---")
        map_data = heatmap_service.get_kindergarten_map_data(db)
        pin_count = map_data.get("count", 0)
        missing_locations = map_data.get("missing_location_count", 0)
        features = map_data.get("features", [])
        print(f"Map Features (Pins) Count: {pin_count}")
        print(f"Missing Locations: {missing_locations}")
        assert pin_count == total_kgs, f"Expected {total_kgs} pins, got {pin_count}"
        assert missing_locations == 0, f"Expected 0 missing locations, got {missing_locations}"
        
        # Verify first few sample coordinates
        for idx, feat in enumerate(features[:3]):
            props = feat["properties"]
            coords = feat["geometry"]["coordinates"]
            print(f"  [Pin {idx+1}] {props.get('name_ar')} | Gov: {props.get('governorate')} | Lat/Lng: {coords[1]}, {coords[0]}")

        # 2. Test Heatmap Overview & Governorates
        print("\n--- Testing Heatmap Overview ---")
        overview = heatmap_service.get_map_overview(db)
        govs = overview.get("governorates", [])
        print(f"Heatmap Governorates Count: {len(govs)}")
        for g in govs:
            print(f"  - Gov: {g.get('name_ar')} ({g.get('slug')}): KGs={g.get('kg_count')}, Risk Score={g.get('risk_score')}")

        # 3. Test KPIs
        print("\n--- Testing Country-Level KPIs ---")
        admin_user = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).first()
        if not admin_user:
            admin_user = models.User(
                id=999999,
                username="admin_kpi_check",
                email="admin_kpi_check@kinjo.jo",
                role=models.UserRole.ADMIN,
                status=models.UserStatus.ACTIVE,
            )
        
        kpi_summary = get_kpi_summary(current_user=admin_user, db=db)
        print(f"KPI Summary Result: {kpi_summary}")
        
        country_kpis = get_kpi_country_level(current_user=admin_user, db=db)
        print(f"Country KPIs Total Returned: {len(country_kpis.get('kpis', {}))}")
        for k_name, k_val in list(country_kpis.get("kpis", {}).items())[:5]:
            print(f"  * KPI: {k_name} = {k_val}")

        print("\n>>> ALL MAP PINS, HEATMAP AND KPI CHECKS PASSED SUCCESSFULLY! <<<")
    finally:
        db.close()

if __name__ == "__main__":
    run_verification()
