"""D2 — SupervisorAssignment carries composite indexes matching the active-
assignment query patterns (class_id|supervisor_id, deleted_at)."""
import models


def _index_column_sets(table):
    return {tuple(c.name for c in ix.columns) for ix in table.indexes}


def test_supervisor_assignment_has_composite_indexes():
    sets = _index_column_sets(models.SupervisorAssignment.__table__)
    assert ("class_id", "deleted_at") in sets
    assert ("supervisor_id", "deleted_at") in sets


def test_attendance_log_still_has_composite_indexes():
    # D3 was already satisfied; guard against regression.
    sets = _index_column_sets(models.AttendanceLog.__table__)
    assert ("child_id", "date", "status") in sets
    assert ("class_id", "date") in sets
