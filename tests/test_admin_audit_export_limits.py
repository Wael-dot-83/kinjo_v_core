"""Audit exports must disclose/reject size limits instead of truncating silently."""

import pytest
from fastapi import HTTPException
from sqlalchemy import event

import audit_service
import models


def test_audit_export_rejects_oversize_result_instead_of_truncating(
    test_db, admin_user
):
    test_db.bulk_insert_mappings(
        models.AuditLog,
        [
            {"action": "LIMIT_TEST", "entity_type": "AuditLog"}
            for _ in range(audit_service.MAX_AUDIT_EXPORT_ROWS + 1)
        ],
    )
    test_db.commit()

    with pytest.raises(HTTPException) as exc_info:
        audit_service._export_audit_logs(
            format="json",
            period="all",
            action="LIMIT_TEST",
            entity_type=None,
            user=None,
            date=None,
            current_user=admin_user,
            db=test_db,
        )

    assert exc_info.value.status_code == 422
    assert "more than 5,000 rows" in exc_info.value.detail
    assert test_db.query(models.AuditLog).filter(
        models.AuditLog.action == "LIMIT_TEST"
    ).count() == audit_service.MAX_AUDIT_EXPORT_ROWS + 1


def test_audit_export_limit_uses_one_bounded_snapshot_query(
    test_db, admin_user
):
    test_db.add_all(
        [
            models.AuditLog(action="ONE_QUERY_TEST", entity_type="AuditLog")
            for _ in range(3)
        ]
    )
    test_db.commit()
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        normalized = statement.lower()
        if normalized.lstrip().startswith("select") and "audit_logs" in normalized:
            statements.append(normalized)

    event.listen(test_db.bind, "before_cursor_execute", capture)
    try:
        response = audit_service._export_audit_logs(
            format="json",
            period="all",
            action="ONE_QUERY_TEST",
            entity_type=None,
            user=None,
            date=None,
            current_user=admin_user,
            db=test_db,
        )
    finally:
        event.remove(test_db.bind, "before_cursor_execute", capture)

    assert response.status_code == 200
    assert len(statements) == 1
    assert "count(" not in statements[0]
    assert "limit" in statements[0]
