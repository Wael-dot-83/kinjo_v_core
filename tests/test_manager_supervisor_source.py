"""D1/B5 — the primary supervisor of a class is sourced from SupervisorAssignment,
not the retired Class.supervisor_id column. Creating/ending an assignment must
immediately change the analytics."""
from datetime import date

import models
import validators
from manager_analytics import ManagerAnalyticsService as MA


def _supervisor(test_db, kg_id, username):
    u = models.User(username=username, email=f"{username}@t.com", hashed_password="x",
                    role=models.UserRole.SUPERVISOR, kindergarten_id=kg_id,
                    status=models.UserStatus.ACTIVE)
    test_db.add(u)
    test_db.commit()
    test_db.refresh(u)
    return u


def _assign(test_db, class_id, supervisor_id, primary=True, deleted=False):
    a = models.SupervisorAssignment(
        class_id=class_id, supervisor_id=supervisor_id, is_primary=primary,
        start_date=date(2026, 1, 1), deleted_at=(date(2026, 6, 1) if deleted else None))
    test_db.add(a)
    test_db.commit()
    test_db.refresh(a)
    return a


def test_active_primary_map_from_assignment(test_db, sample_kindergarten, sample_class):
    sup = _supervisor(test_db, sample_kindergarten.id, "sup_map")
    # no assignment yet
    assert validators.active_primary_supervisor_map(test_db, [sample_class.id]) == {}
    a = _assign(test_db, sample_class.id, sup.id)
    assert validators.active_primary_supervisor_map(test_db, [sample_class.id]) == {sample_class.id: sup.id}
    # soft-deleting the assignment drops it from the map
    a.deleted_at = date(2026, 6, 1)
    test_db.commit()
    assert validators.active_primary_supervisor_map(test_db, [sample_class.id]) == {}


def test_workload_reflects_assignment_lifecycle(test_db, sample_kindergarten, sample_class):
    kg = sample_kindergarten.id
    sup = _supervisor(test_db, kg, "sup_workload")

    def classes_for_sup():
        rows = MA.compute_supervisor_workload(test_db, kg)
        row = next((r for r in rows if r["supervisor_id"] == sup.id), None)
        return row["classes_count"] if row else 0

    # no assignment -> not counted
    assert classes_for_sup() == 0
    # create a primary assignment -> counted immediately
    a = _assign(test_db, sample_class.id, sup.id)
    assert classes_for_sup() == 1
    # end (soft-delete) the assignment -> back to 0
    a.deleted_at = date(2026, 6, 1)
    test_db.commit()
    assert classes_for_sup() == 0


def test_column_not_written_on_assignment(test_db, sample_kindergarten, sample_class):
    """Assigning a supervisor must not populate the legacy Class.supervisor_id."""
    sup = _supervisor(test_db, sample_kindergarten.id, "sup_col")
    _assign(test_db, sample_class.id, sup.id)
    test_db.refresh(sample_class)
    assert sample_class.supervisor_id is None
