"""Audit exports must disclose/reject size limits instead of truncating silently."""

import pytest
from fastapi import HTTPException

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
