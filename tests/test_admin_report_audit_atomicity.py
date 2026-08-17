"""Contracts that keep Admin report actions and their audits durable."""

import inspect

import admin_reports_api


def function_source(function) -> str:
    return inspect.getsource(function)


def test_report_export_commits_its_audit_before_returning():
    source = function_source(admin_reports_api.export_report)
    audit = source.index("log_audit_event(")
    commit = source.index("db.commit()", audit)
    first_return = source.index("return payload")
    assert audit < commit < first_return


def test_incident_report_creation_commits_business_row_and_audit_atomically():
    source = function_source(admin_reports_api.generate_incident_report)
    add = source.index("db.add(report)")
    flush = source.index("db.flush()", add)
    audit = source.index("log_audit_event(", flush)
    commit = source.index("db.commit()", audit)
    assert add < flush < audit < commit
    assert "db.commit()\n        db.refresh(report)\n\n        log_audit_event" not in source


def test_incident_export_success_and_failure_audits_are_committed():
    source = function_source(admin_reports_api.export_incident_report_csv)
    success_audit = source.index("AuditAction.INCIDENT_REPORT_EXPORT,")
    success_commit = source.index("db.commit()", success_audit)
    failure_audit = source.index("AuditAction.INCIDENT_REPORT_EXPORT_FAILED,")
    failure_commit = source.index("db.commit()", failure_audit)
    assert success_audit < success_commit < failure_audit < failure_commit
    assert '"error_type": type(e).__name__' in source
    assert '"error_message": str(e)' not in source
