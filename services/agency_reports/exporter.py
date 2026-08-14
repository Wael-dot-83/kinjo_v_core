"""Shared export helpers for agency reports.

Consolidates the CSV/JSON export logic that was previously in the standalone
``agency_reports_export.py``.  All agency services and API endpoints use this
single module for exports.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any

try:
    from csv_utils import escape_csv_formula
except Exception:  # pragma: no cover
    def escape_csv_formula(value: Any) -> Any:
        if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@"):
            return "'" + value
        return value


def _flatten_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for table in payload.get("tables", []):
        for row in table.get("rows", []) or []:
            if isinstance(row, dict):
                rows.append(row)
    if not rows and isinstance(payload.get("summary"), dict):
        rows.append(payload["summary"])
    return rows


def custom_report_to_csv(payload: dict[str, Any]) -> str:
    """CSV for a custom-report payload (scope header + KPIs + detail table).

    Arabic-friendly (UTF-8 BOM) with a formula-injection guard.
    """
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    scope = payload.get("scope", {})
    writer.writerow(["title", escape_csv_formula(payload.get("title", ""))])
    writer.writerow(["agency", escape_csv_formula(scope.get("agency_name_ar", scope.get("agency", "")))])
    writer.writerow(["level", escape_csv_formula(scope.get("level_name_ar", scope.get("level", "")))])
    writer.writerow(["start_date", escape_csv_formula(scope.get("start_date", ""))])
    writer.writerow(["end_date", escape_csv_formula(scope.get("end_date", ""))])
    writer.writerow(["generated_at", escape_csv_formula(payload.get("generated_at", ""))])
    writer.writerow([])
    writer.writerow(["المؤشر", "القيمة", "الوحدة"])
    for kpi in payload.get("kpis", []) or []:
        writer.writerow([
            escape_csv_formula(kpi.get("label_ar", "")),
            escape_csv_formula(kpi.get("value", "")),
            escape_csv_formula(kpi.get("unit_ar", "")),
        ])
    rows = payload.get("table", []) or []
    if rows:
        writer.writerow([])
        headers: list[str] = []
        for row in rows:
            for key in row.keys():
                if key not in headers:
                    headers.append(key)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([escape_csv_formula(row.get(h, "")) for h in headers])
    return output.getvalue()


def to_csv(payload: dict[str, Any]) -> str:
    """Return Arabic-friendly CSV with UTF-8 BOM and formula-injection guard."""
    rows = _flatten_rows(payload)
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    metadata = payload.get("metadata", {})
    writer.writerow(["agency_code", escape_csv_formula(metadata.get("agency_code", ""))])
    writer.writerow(["agency_name_ar", escape_csv_formula(metadata.get("agency_name_ar", ""))])
    writer.writerow(["report_code", escape_csv_formula(metadata.get("report_code", ""))])
    writer.writerow(["report_title_ar", escape_csv_formula(metadata.get("report_title_ar", ""))])
    writer.writerow(["generated_at", escape_csv_formula(metadata.get("generated_at", ""))])
    for key, label in (
        ("definition_ar", "تعريف التقرير"),
        ("data_source_ar", "مصدر البيانات"),
        ("geography_basis_ar", "الأساس الجغرافي"),
        ("units_note_ar", "وحدات القياس"),
        ("symbols_note_ar", "الرموز"),
    ):
        val = metadata.get(key)
        if val:
            writer.writerow([label, escape_csv_formula(val)])
    writer.writerow([])
    if not rows:
        writer.writerow(["status", "لا توجد بيانات متاحة للتصدير"])
        return output.getvalue()
    headers = list(rows[0].keys())
    col_labels = payload.get("column_labels", {}) or {}
    writer.writerow([col_labels.get(h, h) for h in headers])
    for row in rows:
        writer.writerow([escape_csv_formula(row.get(h, "")) for h in headers])
    total_row = payload.get("total_row")
    if isinstance(total_row, dict):
        writer.writerow([escape_csv_formula(total_row.get(h, "")) for h in headers])
    return output.getvalue()


def to_json(payload: dict[str, Any]) -> str:
    """Return JSON string with ensure_ascii=False for Arabic readability."""
    return json.dumps(payload, ensure_ascii=False, default=str)


def to_xlsx(payload: dict[str, Any]) -> bytes:
    """Export to Excel (.xlsx) using openpyxl (already a project dependency)."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Report"

    metadata = payload.get("metadata", {})
    ws.append(["agency_code", metadata.get("agency_code", "")])
    ws.append(["agency_name_ar", metadata.get("agency_name_ar", "")])
    ws.append(["report_code", metadata.get("report_code", "")])
    ws.append(["report_title_ar", metadata.get("report_title_ar", "")])
    ws.append(["generated_at", metadata.get("generated_at", "")])
    ws.append([])

    rows = _flatten_rows(payload)
    if not rows:
        ws.append(["status", "لا توجد بيانات متاحة للتصدير"])
    else:
        headers = list(rows[0].keys())
        col_labels = payload.get("column_labels", {}) or {}
        ws.append([col_labels.get(h, h) for h in headers])
        for row in rows:
            ws.append([row.get(h, "") for h in headers])
        total_row = payload.get("total_row")
        if isinstance(total_row, dict):
            ws.append([total_row.get(h, "") for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
