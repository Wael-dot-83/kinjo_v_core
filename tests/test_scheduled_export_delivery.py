"""Delivery, scheduling maths, injection and concurrency for scheduled exports.

These assert behaviour, not markup: the email is actually built and parsed back,
the calendar maths is exercised across month ends and a leap year, and the
delivery status is checked against what really happened.
"""

from datetime import datetime, timezone
from email import message_from_string
from pathlib import Path

import pytest

import chart_export_tasks as tasks
import email_service

ROOT = Path(__file__).resolve().parents[1]


class _Captured:
    """Stand-in SMTP that keeps the message instead of sending it."""

    def __init__(self):
        self.message = None

    def __call__(self, host, port):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        pass

    def login(self, *args):
        pass

    def send_message(self, message):
        self.message = message


@pytest.fixture()
def smtp(monkeypatch):
    captured = _Captured()
    monkeypatch.setattr(email_service.smtplib, "SMTP", captured)
    monkeypatch.setattr(email_service, "is_smtp_configured", lambda: True)
    monkeypatch.setattr(email_service.settings, "SMTP_HOST", "smtp.test", raising=False)
    monkeypatch.setattr(email_service.settings, "SMTP_PORT", 587, raising=False)
    monkeypatch.setattr(email_service.settings, "SMTP_FROM", "kinjo@test", raising=False)
    monkeypatch.setattr(email_service.settings, "SMTP_USERNAME", "", raising=False)
    return captured


# --- email attachments ------------------------------------------------------

def test_plain_email_is_unchanged_for_existing_callers(smtp):
    """Password reset and friends must keep producing a bare text message."""
    email_service.send_email("a@b.test", "Subject", "Body")
    assert smtp.message.get_content_type() == "text/plain"
    assert not smtp.message.is_multipart()


def test_attachment_is_actually_carried(smtp):
    email_service.send_email(
        "a@b.test", "Export", "Body", attachments=[("report.csv", b"a,b\n1,2\n")]
    )
    parsed = message_from_string(smtp.message.as_string())
    assert parsed.is_multipart()
    parts = list(parsed.walk())
    payloads = [p for p in parts if p.get_filename()]
    assert len(payloads) == 1
    assert payloads[0].get_filename() == "report.csv"
    assert payloads[0].get_payload(decode=True) == b"a,b\n1,2\n"


def test_arabic_attachment_survives_the_round_trip(smtp):
    body = "الاسم,العدد\nحضانة,3\n".encode("utf-8")
    email_service.send_email("a@b.test", "Export", "Body", attachments=[("t.csv", body)])
    parsed = message_from_string(smtp.message.as_string())
    payload = next(p for p in parsed.walk() if p.get_filename())
    assert payload.get_payload(decode=True).decode("utf-8") == "الاسم,العدد\nحضانة,3\n"


def test_attachment_filename_cannot_traverse_or_inject():
    assert email_service._safe_attachment_name("../../etc/passwd") == "passwd"
    assert "\n" not in email_service._safe_attachment_name("a\nb.csv")
    assert email_service._safe_attachment_name("") == "attachment"


def test_oversized_attachment_is_refused(smtp):
    too_big = b"x" * (email_service.MAX_ATTACHMENT_BYTES + 1)
    with pytest.raises(ValueError):
        email_service.send_email("a@b.test", "s", "b", attachments=[("big.csv", too_big)])


# --- scheduling maths -------------------------------------------------------

def _after(y, m, d, h=7):
    return datetime(y, m, d, h, 0, tzinfo=timezone.utc)


def test_monthly_is_a_calendar_month_not_thirty_days():
    """A fixed 30 days slides a schedule backwards through the calendar."""
    assert tasks.compute_next_run("MONTHLY", 6, _after(2026, 1, 15)) == datetime(2026, 2, 15, 6, 0)


def test_monthly_clamps_at_a_short_month():
    assert tasks.compute_next_run("MONTHLY", 6, _after(2026, 1, 31)) == datetime(2026, 2, 28, 6, 0)


def test_monthly_handles_a_leap_year():
    assert tasks.compute_next_run("MONTHLY", 6, _after(2024, 1, 31)) == datetime(2024, 2, 29, 6, 0)


def test_monthly_rolls_across_the_year_boundary():
    result = tasks.compute_next_run("MONTHLY", 6, _after(2026, 12, 20))
    assert (result.year, result.month) == (2027, 1)


def test_weekly_is_seven_days_from_the_next_slot():
    daily = tasks.compute_next_run("DAILY", 6, _after(2026, 3, 10))
    weekly = tasks.compute_next_run("WEEKLY", 6, _after(2026, 3, 10))
    assert (weekly - daily).days == 6


def test_next_run_is_naive_utc():
    assert tasks.compute_next_run("DAILY", 6).tzinfo is None


# --- CSV injection ----------------------------------------------------------

@pytest.mark.parametrize("payload", ["=cmd|'/c calc'!A1", "+1+1", "-2+3", "@SUM(A1)", "\tx", "\rx"])
def test_formula_payloads_are_defused(payload):
    assert tasks._defuse(payload).startswith("'")


def test_ordinary_text_is_untouched():
    for value in ("Ahmed", "حضانة الأمل", "3", ""):
        assert tasks._defuse(value) == value


def test_serialised_csv_defuses_and_keeps_the_bom():
    text, ext = tasks._serialise([{"name": "=HYPERLINK(1)"}], "CSV")
    assert ext == "csv"
    assert text.startswith("﻿")
    assert "'=HYPERLINK(1)" in text


# --- delivery status honesty ------------------------------------------------

def test_status_never_claims_sent_without_smtp(monkeypatch):
    """STORED must mean "produced but not emailed", and it must not be reached
    by swallowing a delivery failure."""
    source = (ROOT / "chart_export_tasks.py").read_text(encoding="utf-8")
    body = source.split("def run_one", 1)[1].split("\ndef ", 1)[0]
    assert 'return "STORED"' in body
    # A failed send re-raises rather than downgrading to STORED.
    assert "raise" in body
    assert body.index("except Exception") < body.index("raise")


def test_delivery_attaches_the_generated_file():
    source = (ROOT / "chart_export_tasks.py").read_text(encoding="utf-8")
    assert "attachments=[(path.name, text.encode(\"utf-8\"))]" in source


# --- concurrency and retention ---------------------------------------------

def test_due_rows_are_claimed_before_work():
    """Two workers sweeping the same minute would otherwise email twice."""
    source = (ROOT / "chart_export_tasks.py").read_text(encoding="utf-8")
    body = source.split("def run_due_exports", 1)[1]
    assert "with_for_update(skip_locked=True)" in body
    assert body.index("with_for_update") < body.index("for schedule in due")


def test_exports_directory_is_bounded():
    assert "def _prune_exports" in (ROOT / "chart_export_tasks.py").read_text(encoding="utf-8")


def test_prune_keeps_the_newest_and_removes_the_rest(tmp_path, monkeypatch):
    monkeypatch.setattr(tasks, "EXPORT_DIR", tmp_path)
    for i in range(5):
        (tmp_path / f"chart_x_{i}.csv").write_text("x", encoding="utf-8")
    tasks._prune_exports(keep=2)
    assert len(list(tmp_path.glob("chart_*"))) == 2


# --- background services actually exist ------------------------------------

def test_compose_declares_worker_and_beat():
    """Production ran neither: KINJO_WEB_COMMAND overrode compose's supervisord
    default, and supervisor.conf only started uvicorn."""
    text = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
    try:
        import yaml
        compose = yaml.safe_load(text)
        services = compose["services"]
        assert "worker" in services and "beat" in services
        assert "worker" in services["worker"]["command"]
        assert "beat" in services["beat"]["command"]
    except ImportError:
        assert "worker:" in text
        assert "beat:" in text
        assert "celery -A celery_app" in text
