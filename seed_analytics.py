import os
import random
import math
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import statistics
from sqlalchemy.orm import Session
from database import SessionLocal
from models import (
    Kindergarten, AnalyticsDimensionCache, AdvancedAnalyticsCache, 
    AnalyticsDimensionType, AnalyticsPeriodType
)

# --- Data Science Helpers ---

def calculate_linear_trend(values):
    """Calculates the slope (trend) of an array of values using simple linear regression."""
    if len(values) < 2: return 0.0
    n = len(values)
    x = list(range(n))
    y = values
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi*yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi**2 for xi in x)
    denominator = (n * sum_x2 - sum_x**2)
    if denominator == 0: return 0.0
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    return slope

def calculate_pearson_correlation(x, y):
    """Calculates Pearson correlation coefficient between two arrays."""
    if len(x) != len(y) or len(x) < 2: return 0.0
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    numerator = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    denom_x = sum((xi - mean_x)**2 for xi in x)
    denom_y = sum((yi - mean_y)**2 for yi in y)
    if denom_x == 0 or denom_y == 0: return 0.0
    return numerator / math.sqrt(denom_x * denom_y)

def calculate_z_score(val, mean, std_dev):
    """Calculates standardization Z-score."""
    if std_dev == 0: return 0.0
    return (val - mean) / std_dev

# --- Mock Data Seeding ---

def seed_analytics():
    db = SessionLocal()
    try:
        # Clear existing caches to ensure clean run
        db.query(AnalyticsDimensionCache).delete()
        db.query(AdvancedAnalyticsCache).delete()
        db.commit()

        kgs = db.query(Kindergarten).all()
        if not kgs:
            print("No kindergartens found. Cannot run analytics.")
            return

        today = date.today()
        # Generate last 6 months
        months = [(today - relativedelta(months=i)).replace(day=1) for i in range(5, -1, -1)]
        
        # We will hold aggregated data to calculate higher levels
        city_data = {}
        gov_data = {}
        network_data = {}

        print(f"Generating analytics for {len(kgs)} Kindergartens over 6 months...")

        # 1. GENERATE BASE KG DATA
        for kg in kgs:
            # We want each KG to have some consistent identity over time
            base_capacity = random.randint(30, 150)
            base_enrollment = min(base_capacity, random.randint(int(base_capacity*0.4), int(base_capacity*0.95)))
            base_gov_score = random.randint(40, 95)
            
            # Trend direction: 1 = improving, -1 = declining, 0 = stable
            trend_dir = random.choice([1, 1, 0, -1])

            attendance_history = []
            incident_history = []
            ratio_history = []
            
            for m_idx, month_dt in enumerate(months):
                # Apply slight trend over time
                current_enrollment = int(base_enrollment + (m_idx * trend_dir * random.randint(1, 3)))
                current_enrollment = min(base_capacity, max(10, current_enrollment))
                
                enroll_rate = (current_enrollment / base_capacity) * 100
                
                # Attendance
                absent_pct = random.uniform(0.02, 0.15) if trend_dir > 0 else random.uniform(0.05, 0.25)
                actual_att = int(current_enrollment * (1 - absent_pct))
                att_rate = (actual_att / current_enrollment) * 100 if current_enrollment > 0 else 0
                attendance_history.append(att_rate)
                
                # Incidents
                incidents = random.randint(0, 3) if base_gov_score > 70 else random.randint(2, 8)
                inc_rate = (incidents / current_enrollment) * 100 if current_enrollment > 0 else 0
                incident_history.append(inc_rate)
                
                # Compliance / Ratio
                ratio_comp = random.uniform(0.8, 1.0) if base_gov_score > 70 else random.uniform(0.5, 0.9)
                ratio_history.append(ratio_comp)
                
                gov_score = min(100, max(0, base_gov_score + (m_idx * trend_dir * 2) + random.randint(-5, 5)))
                
                # Insert dimension cache
                dim = AnalyticsDimensionCache(
                    dimension_type=AnalyticsDimensionType.KINDERGARTEN,
                    dimension_id=str(kg.id),
                    period_type=AnalyticsPeriodType.MONTHLY,
                    period_date=month_dt,
                    total_capacity=base_capacity,
                    total_enrolled=current_enrollment,
                    enrollment_rate=enroll_rate,
                    expected_attendance=current_enrollment,
                    actual_attendance=actual_att,
                    attendance_rate=att_rate,
                    total_incidents=incidents,
                    high_severity_incidents=int(incidents * 0.2),
                    incident_rate_per_100=inc_rate,
                    total_staff=max(2, int(current_enrollment / 10)),
                    ratio_compliance_rate=ratio_comp * 100,
                    final_governance_score=gov_score
                )
                db.add(dim)

                # Aggregations prep
                def agg(d, key):
                    if key not in d: d[key] = {}
                    if month_dt not in d[key]:
                        d[key][month_dt] = {
                            "cap": 0, "enr": 0, "exp_att": 0, "act_att": 0, 
                            "inc": 0, "gov_scores": []
                        }
                    m = d[key][month_dt]
                    m["cap"] += base_capacity
                    m["enr"] += current_enrollment
                    m["exp_att"] += current_enrollment
                    m["act_att"] += actual_att
                    m["inc"] += incidents
                    m["gov_scores"].append(gov_score)

                agg(city_data, f"{kg.governorate}_{kg.district}")
                agg(gov_data, kg.governorate)
                agg(network_data, "JORDAN")

            # Compute Advanced Predictive Metrics for this KG
            att_trend = calculate_linear_trend(attendance_history)
            corr_staff_inc = calculate_pearson_correlation(ratio_history, incident_history)
            
            adv = AdvancedAnalyticsCache(
                dimension_type=AnalyticsDimensionType.KINDERGARTEN,
                dimension_id=str(kg.id),
                period_type=AnalyticsPeriodType.MONTHLY,
                period_start=months[0],
                period_end=months[-1],
                attendance_rate=statistics.mean(attendance_history),
                incident_rate_per_100=statistics.mean(incident_history),
                attendance_trend_slope=att_trend,
                staffing_quality_correlation=corr_staff_inc,
                risk_score=100 - base_gov_score + (statistics.mean(incident_history)*5)
            )
            db.add(adv)

        # 2. GENERATE AGGREGATIONS (CITY, GOV, NETWORK)
        def process_agg(agg_data, dim_type):
            for dim_id, months_dict in agg_data.items():
                hist_att = []
                hist_inc = []
                for m_dt in months:
                    m = months_dict[m_dt]
                    if m["cap"] == 0: continue
                    enr_rate = (m["enr"] / m["cap"]) * 100
                    att_rate = (m["act_att"] / m["exp_att"]) * 100 if m["exp_att"] > 0 else 0
                    inc_rate = (m["inc"] / m["enr"]) * 100 if m["enr"] > 0 else 0
                    avg_gov = sum(m["gov_scores"]) / len(m["gov_scores"]) if m["gov_scores"] else 0
                    
                    hist_att.append(att_rate)
                    hist_inc.append(inc_rate)

                    db.add(AnalyticsDimensionCache(
                        dimension_type=dim_type,
                        dimension_id=dim_id,
                        period_type=AnalyticsPeriodType.MONTHLY,
                        period_date=m_dt,
                        total_capacity=m["cap"],
                        total_enrolled=m["enr"],
                        enrollment_rate=enr_rate,
                        expected_attendance=m["exp_att"],
                        actual_attendance=m["act_att"],
                        attendance_rate=att_rate,
                        total_incidents=m["inc"],
                        incident_rate_per_100=inc_rate,
                        final_governance_score=avg_gov
                    ))

                # Advanced cache for aggregated level
                if hist_att:
                    db.add(AdvancedAnalyticsCache(
                        dimension_type=dim_type,
                        dimension_id=dim_id,
                        period_type=AnalyticsPeriodType.MONTHLY,
                        period_start=months[0],
                        period_end=months[-1],
                        attendance_rate=statistics.mean(hist_att),
                        incident_rate_per_100=statistics.mean(hist_inc),
                        attendance_trend_slope=calculate_linear_trend(hist_att)
                    ))

        process_agg(city_data, AnalyticsDimensionType.DISTRICT)
        process_agg(gov_data, AnalyticsDimensionType.GOVERNORATE)
        process_agg(network_data, AnalyticsDimensionType.NETWORK)

        db.commit()
        print("Data Science KPIs & Seeded Historical Data successfully generated!")

    except Exception as e:
        db.rollback()
        print(f"Error seeding analytics: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_analytics()
