"""Regression net for the /api/heatmap security repair.

The legacy heat map ETL router shipped mounted with no guard at all. Every route
under /api/heatmap answered anonymous callers, and `POST /pipeline/run` took a
caller-supplied `csv_path` straight into `pd.read_csv()` — then echoed the parsed
rows back through pydantic validation errors, which made it an unauthenticated
arbitrary-file-read primitive for any CSV-parsable file on the host.

The authorization half is asserted by tests/test_admin_authz_sweep.py, which now
drives /api/heatmap as part of ADMIN_JSON_PREFIXES. This module pins the parts a
route-level sweep cannot see: that the source allowlist rejects caller-controlled
paths, and that validation output never quotes the content it read.
"""
from __future__ import annotations

import pandas as pd
import pytest

from conftest import bearer_headers
from heatmap.backend.analytics.stats import rolling_health_alert_hotspot
from heatmap.backend.api.router import PIPELINE_SOURCES
from heatmap.backend.etl.validate import (
    VALID_ADMIN_IDS,
    _safe_admin_id,
    summarize_validation_error,
    validate_records,
)

# A path that exists on the host but is not a designated source. The point is that
# the allowlist refuses it on the key, never reaching the filesystem at all.
OFF_LIMITS_PATHS = [
    "../../../etc/passwd",
    r"C:\Windows\win.ini",
    "/etc/passwd",
    str(PIPELINE_SOURCES["sample"]),  # even a real source path, passed as a path
]


# ---------------------------------------------------------------------------
# Source allowlist
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_source", OFF_LIMITS_PATHS)
def test_pipeline_run_rejects_caller_supplied_paths(client, admin_token, bad_source):
    """Only opaque allowlist keys are accepted; a path is never a valid source."""
    resp = client.post(
        "/api/heatmap/pipeline/run",
        params={"source": bad_source},
        headers=bearer_headers(admin_token),
    )
    assert resp.status_code == 400, (
        f"source={bad_source!r} answered {resp.status_code}; a caller-supplied path "
        "must be refused by the allowlist"
    )
    # The rejection must not leak whether the path exists on disk.
    assert "Unknown source" in resp.json()["detail"]


def test_pipeline_run_ignores_legacy_csv_path_parameter(client, admin_token):
    """The removed `csv_path` parameter must not be honoured if a caller still sends it."""
    resp = client.post(
        "/api/heatmap/pipeline/run",
        params={"csv_path": r"C:\Windows\win.ini"},
        headers=bearer_headers(admin_token),
    )
    # csv_path is not a parameter any more, so the endpoint falls through to its
    # default server-side source and never consults the supplied path.
    assert resp.status_code in (200, 404)
    assert "win.ini" not in resp.text


def test_pipeline_sources_are_all_inside_the_data_directory():
    """No allowlist entry may point outside the heat map data directory."""
    from heatmap.backend.api.router import DATA_DIR

    for key, path in PIPELINE_SOURCES.items():
        resolved = path.resolve()
        assert DATA_DIR.resolve() in resolved.parents, (
            f"PIPELINE_SOURCES[{key!r}] resolves to {resolved}, outside {DATA_DIR}"
        )


# ---------------------------------------------------------------------------
# Validation errors must never quote the content they read
# ---------------------------------------------------------------------------

def test_validation_errors_do_not_echo_row_content():
    """A row's values must never appear in the error payload.

    `str(ValidationError)` embeds `input_value=...`. When the server parsed the row
    out of a file, echoing it back is what turned validation output into a file read.

    The row below is deliberately shaped like a real record with one unparsable
    field, because that is the case pydantic reports *in full*: it renders
    `input_value='SECRET-CELL-VALUE'` verbatim. A row of entirely unknown columns
    is a weaker probe — pydantic truncates the whole-dict repr with an ellipsis, so
    a long value can be partially hidden by accident rather than by the fix.
    """
    secret = "SECRET-CELL-VALUE"
    _, errors = validate_records([
        {"date": "2026-06-01", "admin_id": "JO-AM", "kindergartens_active": secret}
    ])

    assert errors, "a malformed row should produce an error entry"
    blob = str(errors)
    assert secret not in blob, f"row content leaked into the error payload: {blob[:200]}"
    assert "input_value" not in blob
    # It must still be useful: field names and error types survive.
    assert "kindergartens_active" in blob
    assert "int_parsing" in blob or "missing" in blob


def test_validation_errors_do_not_leak_even_a_truncated_prefix():
    """Pydantic's whole-dict repr truncates mid-value, which still leaks a prefix."""
    secret = "s3cr3t-p@ssw0rd-with-a-long-tail"
    _, errors = validate_records([{"leaked_column": secret, "another": "AKIA-FAKE-KEY"}])

    blob = str(errors)
    assert "s3cr3t" not in blob, f"leaked a truncated prefix of the row: {blob[:200]}"
    assert "AKIA-FAKE-KEY" not in blob
    assert "input_value" not in blob


def test_summarize_validation_error_reports_fields_not_values():
    class _Model(__import__("pydantic").BaseModel):
        count: int

    try:
        _Model(count="not-a-number-9999")
    except Exception as exc:  # pydantic.ValidationError
        summary = summarize_validation_error(exc)

    assert "count" in summary            # which field failed
    assert "not-a-number-9999" not in summary  # but never the value


def test_summarize_validation_error_hides_non_pydantic_messages():
    """Arbitrary exceptions may carry data in their message, so only the type escapes."""
    summary = summarize_validation_error(ValueError("row contained s3cr3t"))
    assert summary == "ValueError"
    assert "s3cr3t" not in summary


@pytest.mark.parametrize("value", ["JO-AM", "JO-AQ"])
def test_safe_admin_id_passes_known_codes(value):
    assert value in VALID_ADMIN_IDS
    assert _safe_admin_id(value) == value


@pytest.mark.parametrize("value", ["../../etc/passwd", "s3cr3t", "", None, 12345])
def test_safe_admin_id_drops_anything_unrecognised(value):
    """Only the fixed Jordan vocabulary may be reflected back to a caller."""
    assert _safe_admin_id(value) is None


# ---------------------------------------------------------------------------
# Hotspot analytics degrade instead of 500-ing
# ---------------------------------------------------------------------------

def test_hotspots_return_empty_when_coverage_column_is_absent():
    """compute_dataframe() drops absences_health_alerts; that is a gap, not a fault.

    This previously raised KeyError and surfaced as a 500 on
    GET /api/heatmap/analytics/hotspots.
    """
    frame = pd.DataFrame(
        [
            {"admin_id": "JO-AM", "date": "2026-06-01", "kindergarten_status": 90.0},
            {"admin_id": "JO-AM", "date": "2026-06-02", "kindergarten_status": 91.0},
        ]
    )
    assert "absences_health_alerts" not in frame.columns
    assert rolling_health_alert_hotspot(frame) == []


def test_hotspots_still_compute_when_the_column_is_present():
    """The guard must not silently disable the feature when data does exist."""
    rows = []
    # A flat baseline followed by a sharp rise, which is what the detector looks for.
    for day, value in enumerate([1, 1, 1, 1, 1, 1, 40, 40, 40], start=1):
        rows.append(
            {
                "admin_id": "JO-AM",
                "date": f"2026-06-{day:02d}",
                "absences_health_alerts": value,
            }
        )
    hotspots = rolling_health_alert_hotspot(pd.DataFrame(rows))
    assert hotspots, "a >50% rise over the rolling window should be reported"
    assert hotspots[0]["admin_id"] == "JO-AM"
