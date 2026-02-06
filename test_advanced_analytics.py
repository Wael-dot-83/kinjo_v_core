import os
import sys
from datetime import date, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Kindergarten, Child, EnrollmentApplication, EnrollmentStatus, AttendanceLog, Incident, IncidentType, SeverityLevel, AnalyticsDimensionType, AnalyticsPeriodType
from analytics_service import AnalyticsService

# Setup DB connection
SQLALCHEMY_DATABASE_URL = "sqlite:///./kinjo.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def test_advanced_analytics_computation():
    db = SessionLocal()
    try:
        print("Starting Advanced Analytics Test...")
        
        # 1. Setup Test Data
        # Get or Create a Kindergarten
        kg = db.query(Kindergarten).first()
        if not kg:
            print("No Kindergarten found. Please seed DB first.")
            return

        print(f"Testing with Kindergarten: {kg.name_ar} (ID: {kg.id})")
        
        # Define Period
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # Ensure we have some attendance logs for trend calculation
        # (Assuming existing data or minimal seed exists, otherwise result will be 0)
        
        # 2. Run Computation
        print(f"Computing analytics for period: {start_date} to {end_date}")
        cache = AnalyticsService.compute_advanced_analytics(
            db,
            AnalyticsDimensionType.KINDERGARTEN,
            str(kg.id),
            AnalyticsPeriodType.MONTHLY,
            start_date,
            end_date
        )
        
        # 3. Verify Results
        print("\n=== Results ===")
        print(f"ID: {cache.id}")
        print(f"Attendance Rate: {cache.attendance_rate}%")
        print(f"Trend Slope: {cache.attendance_trend_slope}")
        print(f"Risk Score: {cache.risk_score}%")
        print(f"Correlation (Att vs Inc): {cache.attendance_incident_correlation}")
        print(f"Ratio Compliance: {cache.ratio_compliance_rate}%")
        
        # Simple assertions
        assert cache is not None
        assert cache.dimension_id == str(kg.id)
        print("\nTest Passed! Logic executed without errors.")
        
    except Exception as e:
        print(f"\nTest Failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_advanced_analytics_computation()
