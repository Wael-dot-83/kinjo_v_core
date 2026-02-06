import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Setup path
sys.path.append(os.getcwd())

import models
from models import Message, MessageThreadType, User, UserRole, UserStatus
from database import Base

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./data/kinjo.db"
if not os.path.exists("./data/kinjo.db"):
     print("WARNING: ./data/kinjo.db NOT FOUND! Defaulting to kinjo_dev.db")
     if os.path.exists("kinjo_dev.db"):
         SQLALCHEMY_DATABASE_URL = "sqlite:///./kinjo_dev.db"

print(f"Using database: {SQLALCHEMY_DATABASE_URL}")

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

def test_insert_message():
    print("Testing Message insertion...")
    try:
        # Get a user to be sender
        sender = db.query(User).filter(User.role == UserRole.ADMIN).first()
        if not sender:
            # Create a fake sender if none exists
            print("No admin found, creating one...")
            sender = User(username="debug_admin", email="debug@test.com", role=UserRole.ADMIN, status=UserStatus.ACTIVE, hashed_password="pw")
            db.add(sender)
            db.commit()
            db.refresh(sender)
        
        print(f"Sender ID: {sender.id}")

        # Mimic the data causing crash
        subject = "Test Message"
        message_body = "This is a test."
        target_mode = "ALL_MANAGERS"
        roles = ["MANAGER"]
        
        print("Creating message object...")
        # Create message object
        message = Message(
            thread_type=models.MessageThreadType.ANNOUNCEMENT,
            sender_id=sender.id,
            kindergarten_id=None,
            subject=subject,
            message_body=message_body,
            recipient_id=None,
            allow_replies=True,
            target_mode=target_mode,
            target_roles=roles, # List[str]
            target_governorates=None,
            target_kindergarten_ids=None,
            target_search=None,
            recipient_count=1
        )

        print("Adding message to session...")
        db.add(message)
        print("Flushing...")
        db.flush()
        print(f"Message ID: {message.id}")
        
        print("Committing...")
        db.commit()
        print("Success! Message inserted.")
        
        # Test audit log
        print("Testing log_audit_event mock...")
        from admin_security import log_audit_event
        log_audit_event(
            db=db,
            action="DEBUG_TEST",
            actor=sender,
            target_type="Message",
            target_ids=message.id,
            metadata={"test": "data"}
        )
        print("Audit log success.")
        
    except Exception as e:
        print("FAILED!")
        with open("debug_error.txt", "w") as f:
            if hasattr(e, 'orig'):
                f.write(f"Original error: {e.orig}\n")
            import traceback
            f.write(traceback.format_exc())
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_insert_message()
