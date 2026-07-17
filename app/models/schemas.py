from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List, Dict, Any

class DOSReportFilters(BaseModel):
    date_from: date = Field(default_factory=lambda: date.today().replace(day=1) - relativedelta(months=12))
    date_to: date = Field(default_factory=date.today)
    governorate: Optional[str] = None
    city: Optional[str] = None
    kindergarten_id: Optional[int] = None
    gender: Optional[str] = None  # 'M', 'F', or None
    age_from_months: Optional[int] = None
    age_to_months: Optional[int] = None
    enrollment_status: Optional[str] = "active"
    group_by: str = "national"
    time_grain: str = "monthly"
    geo_mode: Optional[str] = None

class ReportResponse(BaseModel):
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    warnings: List[str] = []
