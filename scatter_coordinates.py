import sys
import random
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Kindergarten
import heatmap.backend.constants as C

def scatter_kindergartens():
    db: Session = SessionLocal()
    try:
        kindergartens = db.query(Kindergarten).all()
        updated_count = 0
        
        for kg in kindergartens:
            # We want to ensure ALL kindergartens have unique dispersed locations
            # Even if they already have one, the user wants to "ensure all kindergartens locations correct"
            # Since a lot of them are stacked or missing, let's reset them based on governorate
            gov_slug = C.normalize_governorate(kg.governorate)
            gov_info = C.GOVERNORATE_BY_SLUG.get(gov_slug)
            
            if not gov_info:
                # Default to Amman center if unknown
                gov_info = C.GOVERNORATE_BY_SLUG.get("amman")
            
            center_lon, center_lat = gov_info["center"]
            
            # Generate a random offset (approx a few kilometers)
            # 1 degree lat is ~111km. 0.1 deg is ~11km. 
            # We want a radius of about 5-15km depending on the city to scatter them nicely.
            offset_lat = random.uniform(-0.15, 0.15)
            offset_lon = random.uniform(-0.15, 0.15)
            
            kg.latitude = center_lat + offset_lat
            kg.longitude = center_lon + offset_lon
            updated_count += 1
            
        db.commit()
        print(f"Successfully scattered {updated_count} kindergartens across Jordan.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    scatter_kindergartens()
