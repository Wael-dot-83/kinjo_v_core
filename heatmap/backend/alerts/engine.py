"""
Multi-channel alert engine.

Severity HIGH  → email + SMS + in-app
Severity MEDIUM → in-app + daily digest

Rules (from spec):
1. HIGH: sub_indicator > critical threshold AND beta_std >= 0.20
2. MEDIUM: |pearson_r| >= 0.70 but beta_std < 0.20
3. Health hotspot: rolling 3-day absences_health_alerts increase > 50% vs baseline → HIGH
"""
from __future__ import annotations
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

from ..etl.compute import SUB_INDICATOR_THRESHOLDS, INDICATOR_THRESHOLDS
from ..analytics.pearson import STRONG_CORRELATION_THRESHOLD
from ..analytics.ols import HIGH_IMPACT_THRESHOLD

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    HIGH   = "HIGH"
    MEDIUM = "MEDIUM"
    INFO   = "INFO"


@dataclass
class Alert:
    severity:      Severity
    admin_id:      str
    rule:          str
    message:       str
    meta:          dict[str, Any] = field(default_factory=dict)
    created_at:    str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    acknowledged:  bool = False
    id:            str = field(default_factory=lambda: _gen_id())


def _gen_id() -> str:
    import uuid
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# In-memory store (replace with DB/Redis in production)
# ---------------------------------------------------------------------------
_alert_store: list[Alert] = []


def get_alerts(unacknowledged_only: bool = False) -> list[Alert]:
    if unacknowledged_only:
        return [a for a in _alert_store if not a.acknowledged]
    return list(_alert_store)


def acknowledge_alert(alert_id: str) -> bool:
    for a in _alert_store:
        if a.id == alert_id:
            a.acknowledged = True
            return True
    return False


def _store_alert(alert: Alert) -> None:
    _alert_store.append(alert)
    if len(_alert_store) > 1000:
        _alert_store.pop(0)


# ---------------------------------------------------------------------------
# Dispatch channels
# ---------------------------------------------------------------------------

def _send_email(alert: Alert) -> None:
    """Send via SendGrid (or SMTP fallback)."""
    api_key = os.getenv("SENDGRID_API_KEY")
    recipient = os.getenv("ALERT_EMAIL_TO", "admin@kinjo.jo")
    sender = os.getenv("ALERT_EMAIL_FROM", "alerts@kinjo.jo")
    if not api_key:
        logger.warning("SENDGRID_API_KEY not set; skipping email for alert %s", alert.id)
        return
    payload = {
        "personalizations": [{"to": [{"email": recipient}]}],
        "from": {"email": sender},
        "subject": f"[{alert.severity}] Jordan Heatmap Alert — {alert.admin_id}",
        "content": [{"type": "text/plain", "value": alert.message}],
    }
    try:
        resp = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Email alert sent: %s", alert.id)
    except Exception as exc:
        logger.error("Email send failed: %s", exc)


def _send_sms(alert: Alert) -> None:
    """Send via Twilio."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token  = os.getenv("TWILIO_AUTH_TOKEN")
    from_num    = os.getenv("TWILIO_FROM_NUMBER")
    to_num      = os.getenv("ALERT_SMS_TO")
    if not all([account_sid, auth_token, from_num, to_num]):
        logger.warning("Twilio env vars not set; skipping SMS for alert %s", alert.id)
        return
    try:
        resp = httpx.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data={"From": from_num, "To": to_num, "Body": f"[{alert.severity}] {alert.message[:160]}"},
            auth=(account_sid, auth_token),
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("SMS alert sent: %s", alert.id)
    except Exception as exc:
        logger.error("SMS send failed: %s", exc)


def _send_inapp(alert: Alert) -> None:
    """Store in-app (and optionally push to a WebSocket room via POST)."""
    _store_alert(alert)
    ws_endpoint = os.getenv("INAPP_WS_PUSH_URL")
    if ws_endpoint:
        try:
            httpx.post(ws_endpoint, json={
                "id":       alert.id,
                "severity": alert.severity,
                "admin_id": alert.admin_id,
                "rule":     alert.rule,
                "message":  alert.message,
                "meta":     alert.meta,
                "created_at": alert.created_at,
            }, timeout=5)
        except Exception as exc:
            logger.warning("WebSocket push failed: %s", exc)


# ---------------------------------------------------------------------------
# Dispatch router
# ---------------------------------------------------------------------------

def dispatch_alert(alert: Alert) -> None:
    _send_inapp(alert)
    if alert.severity == Severity.HIGH:
        _send_email(alert)
        _send_sms(alert)
    logger.info("Alert dispatched [%s] %s: %s", alert.severity, alert.admin_id, alert.rule)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def evaluate_alerts(
    computed_row: dict[str, Any],
    stats_row: dict[str, Any] | None = None,
    hotspots: list[dict] | None = None,
) -> list[Alert]:
    """
    Evaluate alerting rules for a single computed data row.

    computed_row: output of compute.compute_row()
    stats_row:   optional row from stats with {sub_indicator, beta_std, pearson_r}
    hotspots:    output from rolling_health_alert_hotspot()
    """
    alerts: list[Alert] = []
    admin_id = computed_row.get("admin_id", "UNKNOWN")

    # Rule 1 + 2: sub-indicator threshold + statistical weight
    for sub, threshold in SUB_INDICATOR_THRESHOLDS.items():
        value = computed_row.get(sub)
        if value is None:
            continue
        exceeds_threshold = float(value) > threshold

        # look up statistical weights for this sub-indicator
        beta_std = None
        pearson_r = None
        if stats_row:
            if stats_row.get("sub_indicator") == sub:
                beta_std  = stats_row.get("beta_std")
                pearson_r = stats_row.get("pearson_r")

        # HIGH: threshold exceeded AND high OLS weight
        if exceeds_threshold and beta_std is not None and abs(float(beta_std)) >= HIGH_IMPACT_THRESHOLD:
            msg = (
                f"[HIGH] {admin_id}: {sub}={value} exceeds threshold {threshold} "
                f"AND beta_std={beta_std:.3f} ≥ {HIGH_IMPACT_THRESHOLD}"
            )
            a = Alert(
                severity=Severity.HIGH,
                admin_id=admin_id,
                rule="THRESHOLD_AND_HIGH_IMPACT",
                message=msg,
                meta={"sub_indicator": sub, "value": value, "threshold": threshold, "beta_std": beta_std},
            )
            alerts.append(a)
            dispatch_alert(a)

        # MEDIUM: strong correlation but low OLS weight
        elif (
            pearson_r is not None
            and abs(float(pearson_r)) >= STRONG_CORRELATION_THRESHOLD
            and (beta_std is None or abs(float(beta_std)) < HIGH_IMPACT_THRESHOLD)
        ):
            msg = (
                f"[MEDIUM] {admin_id}: {sub} has strong correlation r={pearson_r:.3f} "
                f"(beta_std={beta_std})"
            )
            a = Alert(
                severity=Severity.MEDIUM,
                admin_id=admin_id,
                rule="STRONG_CORRELATION_LOW_IMPACT",
                message=msg,
                meta={"sub_indicator": sub, "pearson_r": pearson_r, "beta_std": beta_std},
            )
            alerts.append(a)
            dispatch_alert(a)

    # Rule 3: health hotspot
    if hotspots:
        for hs in hotspots:
            if hs["admin_id"] == admin_id:
                msg = (
                    f"[HIGH] {admin_id}: health absence hotspot — "
                    f"{hs['pct_change']}% increase over 3-day rolling window "
                    f"(current_avg={hs['current_avg']}, baseline={hs['baseline_avg']})"
                )
                a = Alert(
                    severity=Severity.HIGH,
                    admin_id=admin_id,
                    rule="HEALTH_ABSENCE_HOTSPOT",
                    message=msg,
                    meta=hs,
                )
                alerts.append(a)
                dispatch_alert(a)

    return alerts
