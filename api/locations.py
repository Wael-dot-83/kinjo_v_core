from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
import models

router = APIRouter(tags=["Locations"])

@router.get("/divisions")
def get_administrative_divisions(db: Session = Depends(get_db)):
    """Returns the 3-level hierarchical locations (Governorate -> District -> Area)"""
    divisions = db.query(models.AdministrativeDivision).all()
    
    hierarchy = {}
    for div in divisions:
        gov = div.governorate
        dist = div.district
        area = div.area
        
        if gov not in hierarchy:
            hierarchy[gov] = {}
        
        if dist not in hierarchy[gov]:
            hierarchy[gov][dist] = []
            
        if area not in hierarchy[gov][dist]:
            hierarchy[gov][dist].append(area)
            
    return {"divisions": hierarchy}
