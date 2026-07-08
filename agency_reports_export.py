"""Export helpers for official agency reports."""
from __future__ import annotations

import csv
import io
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
    writer.writerow([])
    if not rows:
        writer.writerow(["status", "لا توجد بيانات متاحة للتصدير"])
        return output.getvalue()
    headers = list(rows[0].keys())
    writer.writerow(headers)
    for row in rows:
        writer.writerow([escape_csv_formula(row.get(h, "")) for h in headers])
    return output.getvalue()
