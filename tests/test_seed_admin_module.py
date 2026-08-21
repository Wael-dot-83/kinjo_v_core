"""
Tests for Admin Module Seed Data Generator
==========================================
Verifies that scripts/seed_admin_module.py generates complete, robust, and
deterministic seed data covering all admin module features, metrics, filters,
and edge cases across the network.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from scripts.seed_admin_module import seed_admin_module, GOVERNORATES


def test_seed_admin_module_creates_all_cases(tmp_path):
    db_path = tmp_path / "test_admin_seed.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        summary = seed_admin_module(db, force=False)
        assert summary["admin_user"] == "admin"
        assert summary["governorates_covered"] == 12

        # 1. Admin user verification
        admin = db.query(models.User).filter(models.User.role == models.UserRole.ADMIN).first()
        assert admin is not None
        assert admin.username == "admin"
        assert admin.status == models.UserStatus.ACTIVE

        # 2. Regional Supervisors verification
        supervisors = db.query(models.User).filter(models.User.role == models.UserRole.SUPERVISOR).all()
        assert len(supervisors) >= 5

        # 3. Kindergartens across all 12 governorates
        kgs = db.query(models.Kindergarten).all()
        assert len(kgs) >= 15
        govs_in_db = {k.governorate for k in kgs}
        for gov in GOVERNORATES:
            assert gov in govs_in_db, f"Governorate '{gov}' missing from seeded kindergartens"

        # Check status diversity (ACTIVE, DRAFT, FROZEN)
        kg_statuses = {k.status for k in kgs}
        assert models.KindergartenStatus.ACTIVE in kg_statuses
        assert models.KindergartenStatus.DRAFT in kg_statuses
        assert models.KindergartenStatus.FROZEN in kg_statuses

        # 4. Classes and Age Groups (including KG2 eligibility)
        classes = db.query(models.Class).all()
        assert len(classes) >= 20
        class_names = [c.name_ar for c in classes]
        assert any("KG2" in name or "المستوى الثاني" in name for name in class_names)

        # 5. Enrollments across all statuses and sources
        enrollments = db.query(models.EnrollmentApplication).all()
        assert len(enrollments) >= 40
        enr_statuses = {e.status for e in enrollments}
        assert models.EnrollmentStatus.ACTIVE in enr_statuses
        assert models.EnrollmentStatus.SUBMITTED in enr_statuses
        assert models.EnrollmentStatus.PENDING_REVIEW in enr_statuses
        assert models.EnrollmentStatus.ACCEPTED in enr_statuses
        assert models.EnrollmentStatus.REJECTED in enr_statuses
        assert models.EnrollmentStatus.DRAFT in enr_statuses

        enr_sources = {e.source for e in enrollments}
        assert {"WEB", "MOBILE", "OFFICE"}.issubset(enr_sources)

        # 6. Attendance Logs
        att_logs = db.query(models.AttendanceLog).all()
        assert len(att_logs) >= 100
        att_statuses = {a.status for a in att_logs}
        assert models.AttendanceStatus.PRESENT in att_statuses
        assert models.AttendanceStatus.ABSENT in att_statuses

        # 7. Daily Reports & Canonical Moods
        reports = db.query(models.DailyReport).all()
        assert len(reports) >= 30
        moods_in_db = {r.mood for r in reports}
        for mood in ["HAPPY", "CALM", "ENERGETIC", "TIRED", "FUSSY", "SAD"]:
            assert mood in moods_in_db, f"Mood '{mood}' missing from daily reports"

        # 8. Incidents across all 4 severity tiers
        incidents = db.query(models.Incident).all()
        assert len(incidents) >= 6
        severities = {i.severity_level for i in incidents}
        assert models.SeverityLevel.LOW in severities
        assert models.SeverityLevel.MEDIUM in severities
        assert models.SeverityLevel.HIGH in severities
        assert models.SeverityLevel.CRITICAL in severities

        # 9. Scheduled Exports
        sched_exports = db.query(models.ScheduledChartExport).all()
        assert len(sched_exports) >= 3
        freqs = {s.frequency for s in sched_exports}
        assert {"DAILY", "WEEKLY", "MONTHLY"}.issubset(freqs)

        # 10. Audit Logs
        audits = db.query(models.AuditLog).all()
        assert len(audits) >= 5


def test_seed_admin_module_is_idempotent(tmp_path):
    """Running the seed twice on the same DB must succeed without duplication crashes."""
    db_path = tmp_path / "test_admin_seed_idempotent.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        # First run
        summary1 = seed_admin_module(db, force=False)
        assert summary1["kindergartens"] >= 15

        # Second run (idempotent without force)
        summary2 = seed_admin_module(db, force=False)
        assert summary2["kindergartens"] >= 15
