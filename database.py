"""
Database configuration and session management
"""
import logging
import sqlite3
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base, with_loader_criteria, Session
from sqlalchemy.pool import StaticPool
from config import settings

logger = logging.getLogger(__name__)

# Validate production database configuration
def _validate_production_database():
    """Ensure production uses PostgreSQL (not SQLite)."""
    if settings.TESTING:
        return
    if settings.ENVIRONMENT.lower() == "production":
        if not settings.DATABASE_URL.startswith("postgresql"):
            raise RuntimeError(
                "CRITICAL: Production environment must use PostgreSQL. "
                f"DATABASE_URL must start with 'postgresql', got: {settings.DATABASE_URL[:30]}..."
            )
        logger.info("Production database validation: PostgreSQL confirmed")

_validate_production_database()

# Create database engine with appropriate settings for SQLite or PostgreSQL
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    _is_memory = settings.DATABASE_URL == "sqlite:///:memory:" or ":memory:" in settings.DATABASE_URL
    _engine_kwargs: dict = dict(
        connect_args=connect_args,
        echo=settings.DEBUG,
        pool_pre_ping=True,
    )
    if _is_memory:
        # StaticPool ensures all connections share the single in-memory DB
        # (required for tests and CI that use DATABASE_URL=sqlite:///:memory:)
        _engine_kwargs["poolclass"] = StaticPool
        _engine_kwargs.pop("pool_pre_ping", None)
    engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)

    # Ensure SQLite uses UTF-8 encoding
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        pragmas = (
            "PRAGMA encoding = 'UTF-8'",
            "PRAGMA foreign_keys = ON",
            "PRAGMA journal_mode = WAL",
            "PRAGMA synchronous = NORMAL",
            "PRAGMA temp_store = MEMORY",
            "PRAGMA cache_size = -20000",
            "PRAGMA busy_timeout = 5000",
        )
        for pragma in pragmas:
            try:
                cursor.execute(pragma)
            except (sqlite3.DatabaseError, AttributeError):
                # Keep startup resilient even if a specific pragma is unsupported.
                continue
        cursor.close()
else:
    # PostgreSQL with UTF-8 encoding options
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        echo=settings.DEBUG,
        connect_args={"client_encoding": "utf8"}
    )

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(Session, "do_orm_execute")
def _apply_child_age_policy(execute_state):
    """Apply global child age filter to all ORM SELECT queries."""
    if not execute_state.is_select:
        return

    if execute_state.execution_options.get("include_out_of_range_children", False):
        return

    import models
    from child_age_policy import build_child_age_filter

    child_model = models.Child

    stmt = execute_state.statement.options(
        with_loader_criteria(
            child_model,
            lambda cls: build_child_age_filter(cls.date_of_birth),
            include_aliases=True,
            track_closure_variables=False,
        )
    )

    related_models = [
        models.EnrollmentApplication,
        models.AttendanceLog,
        models.DailyReport,
        models.Incident,
        models.Observation,
        models.Portfolio,
        models.HealthAlert,
    ]

    child_filter = build_child_age_filter(child_model.date_of_birth)
    for model in related_models:
        stmt = stmt.options(
            with_loader_criteria(
                model,
                lambda cls, child_filter=child_filter: cls.child.has(child_filter),
                include_aliases=True,
                track_closure_variables=False,
            )
        )

    execute_state.statement = stmt


@event.listens_for(Session, "before_flush")
def _enforce_child_age_on_write(session, flush_context, instances):
    """Block writes that reference children outside the allowed age range."""
    if session.info.get("skip_child_age_policy"):
        return

    import models
    import validators

    child_ids = set()

    for obj in session.new.union(session.dirty):
        if isinstance(obj, models.Child):
            if obj.date_of_birth is not None:
                validators.validate_child_age_strict(obj.date_of_birth)
        child_id = getattr(obj, "child_id", None)
        if child_id is not None:
            child_ids.add(child_id)

    if not child_ids:
        return

    with session.no_autoflush:
        children = session.query(models.Child).execution_options(
            include_out_of_range_children=True
        ).filter(models.Child.id.in_(child_ids)).all()

    children_by_id = {child.id: child for child in children}
    for child_id in child_ids:
        child = children_by_id.get(child_id)
        if not child:
            raise validators.ValidationError("Child not found")
        validators.validate_child_age_strict(child.date_of_birth)

# Base class for all models
Base = declarative_base()
logger = logging.getLogger(__name__)


def get_db():
    """
    Database dependency for FastAPI
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database - create all tables
    """
    if settings.ENVIRONMENT.lower() == "production":
        logger.info("Skipping Base.metadata.create_all() in production; use Alembic migrations.")
        return
    Base.metadata.create_all(bind=engine)
    ensure_runtime_security_schema()


def ensure_runtime_security_schema():
    """Backfill local-dev security columns when Alembic has not run yet."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("users")}
    statements = []
    if "mfa_enabled" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN mfa_enabled BOOLEAN NOT NULL DEFAULT 0")
    if "mfa_secret" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN mfa_secret VARCHAR(255)")
    if "mfa_enrolled_at" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN mfa_enrolled_at DATETIME")
    if "mfa_last_verified_at" not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN mfa_last_verified_at DATETIME")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
