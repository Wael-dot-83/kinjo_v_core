import sys
import os
import pandas as pd
from sqlalchemy.orm import Session

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import AdministrativeDivision

sys.stdout.reconfigure(encoding='utf-8')

def seed_divisions():
    excel_path = r'C:\Users\waelj\OneDrive - zuj.edu.jo\Desktop\التقسيمات_الإدارية_الأردنية_من_النظام.xlsx'
    
    print(f"Reading {excel_path}...")
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"Failed to read excel: {e}")
        return

    # Drop duplicates just in case
    df = df.drop_duplicates()
    
    db = SessionLocal()
    try:
        # Clear existing data
        db.query(AdministrativeDivision).delete()
        print("Cleared existing administrative divisions.")
        
        # Insert new data
        records = []
        for index, row in df.iterrows():
            gov = str(row['المحافظة']).strip()
            dist = str(row['قصبة / لواء']).strip()
            area = str(row['المنطقة']).strip()
            
            # Skip empty rows if any
            if not gov or gov == 'nan':
                continue
                
            records.append(
                AdministrativeDivision(
                    governorate=gov,
                    district=dist,
                    area=area
                )
            )
            
        if records:
            db.bulk_save_objects(records)
            db.commit()
            print(f"Successfully seeded {len(records)} administrative divisions.")
        else:
            print("No valid records found in excel sheet.")
            
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_divisions()
