import random
import uuid
from datetime import date, timedelta
from sqlalchemy.orm import Session
from database import SessionLocal
from models import (
    User, UserRole, UserStatus, ParentProfile, Child, Gender, Kindergarten, EnrollmentApplication, EnrollmentStatus
)
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def seed_demographics():
    db = SessionLocal()
    try:
        kgs = db.query(Kindergarten).all()
        if not kgs:
            print("No kindergartens found. Please seed KGs first.")
            return
            
        print(f"Loaded {len(kgs)} Kindergartens.")
        
        # 1. Ensure a System Parent exists to hold all the children
        parent_user = db.query(User).filter(User.email == "system_parent@demo.com").first()
        if not parent_user:
            parent_user = User(
                email="system_parent@demo.com",
                username="system_parent",
                hashed_password=hash_password("password123"),
                role=UserRole.PARENT,
                status=UserStatus.ACTIVE,
                full_name="System Parent",
                phone_number="0700000000"
            )
            db.add(parent_user)
            db.commit()
            db.refresh(parent_user)
            
        parent_profile = db.query(ParentProfile).filter(ParentProfile.user_id == parent_user.id).first()
        if not parent_profile:
            parent_profile = ParentProfile(
                user_id=parent_user.id,
                first_name="System",
                last_name="Parent",
                phone_number="0700000000",
                gender=Gender.MALE,
                nationality="Jordanian",
                national_id="0000000000",
                home_governorate="Amman",
                home_district="Amman",
                home_area="Center",
                home_address_line="System Address"
            )
            db.add(parent_profile)
            db.commit()
            db.refresh(parent_profile)
            
        parent_id = parent_profile.id
        
        # Clean existing mock children
        print("Cleaning existing children...")
        db.query(EnrollmentApplication).delete()
        db.query(Child).filter(Child.parent_id == parent_id).delete()
        db.commit()

        # 2. Generate Children and Enrollments
        total_children = 12000
        print(f"Generating {total_children} children and distributing across {len(kgs)} Kindergartens...")
        
        children = []
        enrollments = []
        
        today = date.today()
        names = ["Ahmad", "Omar", "Sara", "Layan", "Yousef", "Ali", "Tala", "Jana", "Zaid", "Mira", "Karam", "Salma"]
        
        # Assign density weights to Kindergartens so some have many children, some have few
        kg_weights = [random.randint(10, 150) for _ in kgs]
        
        for i in range(total_children):
            # Age distribution: mostly 3-5 years old
            age_years = random.choices(
                [1, 2, 3, 4, 5, 6], 
                weights=[0.05, 0.15, 0.35, 0.30, 0.10, 0.05]
            )[0]
            
            days_offset = random.randint(0, 365)
            dob = today - timedelta(days=(age_years * 365) + days_offset)
            
            gender = random.choice([Gender.MALE, Gender.FEMALE])
            first_name = f"{random.choice(names)}_{i}"
            
            child = Child(
                public_id=str(uuid.uuid4()),
                parent_id=parent_id,
                first_name=first_name,
                last_name="Demo",
                gender=gender,
                date_of_birth=dob,
                father_name="System Demo",
                mother_first_name="Sys",
                mother_last_name="Demo",
                mother_nationality="Jordanian"
            )
            children.append(child)
        
        # Bulk save children to get IDs
        db.bulk_save_objects(children)
        db.commit()
        
        # Retrieve them to map enrollments
        saved_children = db.query(Child).filter(Child.parent_id == parent_id).all()
        
        for idx, child in enumerate(saved_children):
            # Select a KG based on weighted distribution (Simulate real density)
            selected_kg = random.choices(kgs, weights=kg_weights, k=1)[0]
            
            enrollment = EnrollmentApplication(
                public_id=str(uuid.uuid4()),
                child_id=child.id,
                kindergarten_id=selected_kg.id,
                status=EnrollmentStatus.ACTIVE,
                is_active=True,
                source="WEB"
            )
            enrollments.append(enrollment)
            
            if len(enrollments) >= 2000:
                db.bulk_save_objects(enrollments)
                db.commit()
                enrollments = []
                
        if enrollments:
            db.bulk_save_objects(enrollments)
            db.commit()
            
        print("Successfully generated Demographic distribution data.")
        
    except Exception as e:
        db.rollback()
        print(f"Error seeding demographics: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_demographics()
