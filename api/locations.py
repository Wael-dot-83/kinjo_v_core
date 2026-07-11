from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
import models
from services.jordan_locations import (
    get_all_governorates,
    get_governorate_by_key,
    get_areas_for_governorate,
    get_area_by_key,
    is_valid_governorate,
    is_valid_area_for_governorate,
    normalize_governorate,
    normalize_area,
)

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


@router.get("/jordan")
def get_jordan_locations():
    """Return all canonical Jordan governorates with their areas."""
    data = []
    for gov in get_all_governorates():
        areas = get_areas_for_governorate(gov["key"])
        data.append({
            "key": gov["key"],
            "name_ar": gov["name_ar"],
            "name_en": gov["name_en"],
            "areas": [
                {
                    "key": a["key"],
                    "name_ar": a["name_ar"],
                    "name_en": a["name_en"],
                }
                for a in areas
            ],
        })
    return {"data": data}


@router.get("/jordan/governorates")
def list_governorates():
    """Return all canonical governorates."""
    governorates = []
    for gov in get_all_governorates():
        governorates.append({
            "key": gov["key"],
            "name_ar": gov["name_ar"],
            "name_en": gov["name_en"],
        })
    return {"data": {"governorates": governorates}}


@router.get("/jordan/governorates/{governorate_key}/areas")
def list_areas(governorate_key: str):
    """Return all areas/cities for a governorate."""
    gov = get_governorate_by_key(governorate_key)
    if not gov:
        raise HTTPException(status_code=404, detail="Governorate not found")
    areas = get_areas_for_governorate(governorate_key)
    return {
        "data": {
            "governorate": {
                "key": gov["key"],
                "name_ar": gov["name_ar"],
                "name_en": gov["name_en"],
            },
            "areas": [
                {
                    "key": a["key"],
                    "name_ar": a["name_ar"],
                    "name_en": a["name_en"],
                }
                for a in areas
            ],
        }
    }


@router.get("/jordan/validate")
def validate_location(
    governorate: str | None = None,
    area: str | None = None,
):
    """Validate governorate and/or area values against canonical source."""
    result = {"valid": True}
    if governorate is not None:
        if not is_valid_governorate(governorate):
            result["valid"] = False
            result["governorate_error"] = f"Invalid governorate: {governorate}"
        else:
            gov_key = None
            gov_ar = normalize_governorate(governorate)
            for g in get_all_governorates():
                if g["name_ar"] == gov_ar:
                    gov_key = g["key"]
                    break
            result["governorate"] = gov_ar
            if area is not None:
                if not is_valid_area_for_governorate(gov_key or "", area):
                    result["valid"] = False
                    result["area_error"] = f"Invalid area for {gov_ar}: {area}"
                else:
                    result["area"] = normalize_area(gov_key or "", area)
    return result
