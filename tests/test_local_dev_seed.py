import importlib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from database import Base
from models import Kindergarten, KindergartenStatus, User, UserRole, UserStatus


def test_ensure_local_dev_seed_data_creates_default_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "TESTING", False)

    import scripts.seed_local as seed_local_module

    seed_local_module = importlib.reload(seed_local_module)

    db_path = tmp_path / "local-dev-seed.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        created = seed_local_module.ensure_local_dev_seed_data(db)
        assert created is True

        admin = db.query(User).filter(User.username == "admin").one()
        assert admin.role == UserRole.ADMIN
        assert admin.status == UserStatus.ACTIVE
        assert admin.hashed_password

        manager = db.query(User).filter(User.username == "manager1").one()
        assert manager.role == UserRole.MANAGER
        assert manager.kindergarten_id is not None

        kindergarten = db.query(Kindergarten).first()
        assert kindergarten is not None
        assert kindergarten.status == KindergartenStatus.ACTIVE

    with TestingSessionLocal() as db:
        assert seed_local_module.ensure_local_dev_seed_data(db) is False
