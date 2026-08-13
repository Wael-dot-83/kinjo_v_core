"""
Daily Report Analytics Module
=============================
Comprehensive analytics for DailyReport data: attendance, mood trends,
meal compliance, nap analytics, workflow metrics, health flags, and more.
Uses Pandas for aggregation and Plotly for interactive visualizations.

Endpoints mounted at /api/reports-analytics/...
Dashboard HTML at /reports/analytics
"""
from __future__ import annotations

import io
import csv
import json
import logging
from datetime import date, datetime, timedelta
from utils.time_utils import today_amman as _today
from typing import Optional, List, Dict, Any

import pandas as pd
import plotly
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, case, text, and_, or_, cast, Integer

from database import get_db
from dependencies import get_current_user
from models import (
    User, UserRole, DailyReport, DailyReportStatus,
    Child, Kindergarten, KindergartenStatus,
)

logger = logging.getLogger(__name__)

def _normalize_ui_language(value: Optional[str]) -> str:
    return "ar"


def _language_context_processor(request: Request) -> dict:
    lang = _normalize_ui_language(request.cookies.get("kinjo_lang"))
    # This module renders templates that extend base.html, which includes
    # components/impersonation_banner.html. That partial resolves `impersonation`
    # or falls back to a `get_impersonation()` global that is never registered, so
    # omitting the key here raises UndefinedError and the page 500s. The canonical
    # processor (scripts/compat/frontend_orig.py) supplies it; this one must too.
    # Decode only the signed, display-safe cookie — never request.state.
    from rbac import get_impersonation_context

    return {
        "ui_lang": lang,
        "ui_dir": "rtl" if lang == "ar" else "ltr",
        "impersonation": get_impersonation_context(request),
    }


templates = Jinja2Templates(
    directory="templates",
    context_processors=[_language_context_processor],
)
templates.env.auto_reload = True

router = APIRouter(prefix="/reports-analytics", tags=["Daily Report Analytics"])
frontend_router = APIRouter(include_in_schema=False)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    """Parse YYYY-MM-DD string."""
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def _hhmm_to_minutes(value: Any) -> int | None:
    """Convert 'HH:MM' to minutes since midnight.

    Missing values do not always arrive as ``None``. pandas >= 3 infers
    ``StringDtype(na_value=nan)`` for the ``arrival_time`` / ``leave_time``
    columns, so ``Series.apply`` hands this function a float ``nan`` for every
    SQL NULL — and ``nan`` is truthy, so a plain falsy check let it through and
    the endpoint died with ``'float' object has no attribute 'split'``.
    Anything that is not a parseable 'HH:MM' string is treated as missing.
    """
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":")
    if len(parts) < 2:
        return None
    try:
        hours, minutes = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= hours <= 23 and 0 <= minutes <= 59):
        return None
    return hours * 60 + minutes


def _minutes_to_hhmm(m: float | None) -> str:
    """Convert minutes since midnight back to 'HH:MM'."""
    if m is None or pd.isna(m):
        return "--:--"
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


# `daily_reports.mood` is free text, and two vocabularies are live in the
# database: the report form and supervisor roster write lowercase
# happy/normal/sad/tired/sick, while the bulk-seeded rows carry uppercase
# HAPPY/CALM/ENERGETIC/TIRED/UPSET. Everything downstream (labels, colours,
# the sick-rate KPI) must key off one canonical, case-folded value.
MOOD_UNKNOWN = "unknown"

MOOD_ORDER = ["happy", "calm", "energetic", "normal", "sad", "tired", "upset", "sick", MOOD_UNKNOWN]

_MOOD_ALIASES = {
    "content": "calm",
    "quiet": "calm",
    "active": "energetic",
    "neutral": "normal",
    "ok": "normal",
    "unhappy": "sad",
    "sleepy": "tired",
    "angry": "upset",
    "cranky": "upset",
    "ill": "sick",
    "unwell": "sick",
}


def _normalize_mood(value: Any) -> str:
    """Fold a raw `mood` cell to a canonical lowercase mood name.

    NULLs reach here as ``None`` or float ``nan`` (see `_hhmm_to_minutes`), and
    the column also holds empty strings; all of those become 'unknown'.
    """
    if not isinstance(value, str):
        return MOOD_UNKNOWN
    normalized = value.strip().lower()
    if not normalized:
        return MOOD_UNKNOWN
    normalized = _MOOD_ALIASES.get(normalized, normalized)
    return normalized


def _to_numeric(series: pd.Series) -> pd.Series:
    """Coerce a column to float64 so NULLs become NaN and `.mean()` skips them.

    Nullable integer columns arrive from SQLAlchemy as object dtype holding a
    mix of ints and ``None``; aggregating that raises or silently degrades.
    """
    return pd.to_numeric(series, errors="coerce")


def _enforce_analytics_rbac(user: User, kindergarten_ids: List[int] | None) -> List[int] | None:
    """
    Return allowed kindergarten IDs based on role.
    Admin sees all (or filtered).
    Manager and Supervisor see only their assigned kindergarten.
    Parent is forbidden.
    """
    if user.role == UserRole.PARENT:
        raise HTTPException(403, "Parents cannot access analytics dashboards")
    if user.role in (UserRole.MANAGER, UserRole.SUPERVISOR):
        assigned_kindergarten_id = user.kindergarten_id
        if user.role == UserRole.SUPERVISOR and user.supervisor_profile:
            assigned_kindergarten_id = user.supervisor_profile.kindergarten_id
        role_label = "Supervisor" if user.role == UserRole.SUPERVISOR else "Manager"
        if not assigned_kindergarten_id:
            raise HTTPException(403, f"{role_label} not assigned to a kindergarten")
        if kindergarten_ids and assigned_kindergarten_id not in kindergarten_ids:
            raise HTTPException(403, f"{role_label} can only view own kindergarten analytics")
        return [assigned_kindergarten_id]
    # Admin — allow all or filtered
    return kindergarten_ids if kindergarten_ids else None


# Columns every analytic in this module reads, verified mechanically against
# the AST (string constants and attribute names, so itertuples access counts).
# The ten columns outside this set exist only so `sample-data` and `export` can
# hand back a full row; fetching them for a summary transferred 4 MB of
# `activities` and `notes` per request for nothing.
_ANALYTICS_COLUMNS = (
    "child_id", "kindergarten_id", "date", "status",
    "submitted_at", "approved_at", "rejected_reason",
    "arrival_time", "leave_time", "mood", "health_notes",
    "breakfast", "snack", "milk", "lunch",
    "nap_duration_minutes", "bathroom_count", "diaper_wet", "diaper_soiled",
    "child_first_name", "child_last_name",
    "kindergarten_name_ar", "kindergarten_name_en",
)

_RAW_ROW_COLUMNS = (
    "id", "submitted_by", "approved_by", "sent_to_parent_at",
    "nap_start", "nap_end", "activities", "notes", "created_at", "child_dob",
)

_COLUMN_SOURCES = {
    "id": DailyReport.id,
    "child_id": DailyReport.child_id,
    "kindergarten_id": DailyReport.kindergarten_id,
    "date": DailyReport.date,
    "status": DailyReport.status,
    "submitted_by": DailyReport.submitted_by,
    "submitted_at": DailyReport.submitted_at,
    "approved_by": DailyReport.approved_by,
    "approved_at": DailyReport.approved_at,
    "sent_to_parent_at": DailyReport.sent_to_parent_at,
    "rejected_reason": DailyReport.rejected_reason,
    "arrival_time": DailyReport.arrival_time,
    "leave_time": DailyReport.leave_time,
    "mood": DailyReport.mood,
    "health_notes": DailyReport.health_notes,
    "breakfast": DailyReport.breakfast,
    "snack": DailyReport.snack,
    "milk": DailyReport.milk,
    "lunch": DailyReport.lunch,
    "nap_start": DailyReport.nap_start,
    "nap_end": DailyReport.nap_end,
    "nap_duration_minutes": DailyReport.nap_duration_minutes,
    "bathroom_count": DailyReport.bathroom_count,
    "diaper_wet": DailyReport.diaper_wet,
    "diaper_soiled": DailyReport.diaper_soiled,
    "activities": DailyReport.activities,
    "notes": DailyReport.notes,
    "created_at": DailyReport.created_at,
    "child_first_name": Child.first_name,
    "child_last_name": Child.last_name,
    "child_dob": Child.date_of_birth,
    "kindergarten_name_ar": Kindergarten.name_ar,
    "kindergarten_name_en": Kindergarten.name_en,
}

# The full projection, in its original column order — sample-data and export
# return these rows verbatim, so the order is part of their output.
_FULL_COLUMNS = (
    "id", "child_id", "kindergarten_id", "date", "status",
    "submitted_by", "submitted_at", "approved_by", "approved_at",
    "sent_to_parent_at", "rejected_reason",
    "arrival_time", "leave_time", "mood", "health_notes",
    "breakfast", "snack", "milk", "lunch",
    "nap_start", "nap_end", "nap_duration_minutes",
    "bathroom_count", "diaper_wet", "diaper_soiled",
    "activities", "notes", "created_at",
    "child_first_name", "child_last_name", "child_dob",
    "kindergarten_name_ar", "kindergarten_name_en",
)


def _load_reports_df(db: Session, date_from: date, date_to: date,
                     kindergarten_ids: List[int] | None = None,
                     child_ids: List[int] | None = None,
                     status_filter: str | None = None,
                     analytics_only: bool = False) -> pd.DataFrame:
    """
    Load DailyReport rows into a Pandas DataFrame with child/class info.

    `analytics_only` restricts the projection to the columns the analytics
    engine reads. Callers that hand raw rows back to the client (`sample-data`,
    `export`) must leave it False so their payloads keep every field.
    """
    columns = [c for c in _FULL_COLUMNS
               if not analytics_only or c in _ANALYTICS_COLUMNS]
    q = db.query(
        *[_COLUMN_SOURCES[c].label(c) for c in columns]
    ).join(Child, DailyReport.child_id == Child.id
    # Outer join: the name is only used for alert labels, and an inner join
    # would silently drop reports whose kindergarten row is gone.
    ).outerjoin(Kindergarten, DailyReport.kindergarten_id == Kindergarten.id
    ).filter(
        DailyReport.date >= date_from,
        DailyReport.date <= date_to,
    )

    if kindergarten_ids:
        q = q.filter(DailyReport.kindergarten_id.in_(kindergarten_ids))
    if child_ids:
        q = q.filter(DailyReport.child_id.in_(child_ids))
    if status_filter:
        q = q.filter(DailyReport.status == status_filter)

    rows = q.all()
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows, columns=columns)
    return _finalize_reports_df(df)


def _finalize_reports_df(df: pd.DataFrame) -> pd.DataFrame:
    """Derive the columns every analytic below depends on.

    Split out of `_load_reports_df` so the dtype handling can be tested without
    a database — this is where the pandas-3 NULL semantics bite.
    """
    df["child_name"] = (
        df["child_first_name"].fillna("").astype(str).str.strip()
        + " "
        + df["child_last_name"].fillna("").astype(str).str.strip()
    ).str.strip()
    df["status"] = df["status"].apply(lambda s: s.value if hasattr(s, "value") else str(s))
    df["mood"] = df["mood"].apply(_normalize_mood)
    df["arrival_minutes"] = _to_numeric(df["arrival_time"].apply(_hhmm_to_minutes))
    df["leave_minutes"] = _to_numeric(df["leave_time"].apply(_hhmm_to_minutes))
    for numeric_col in ("nap_duration_minutes", "bathroom_count"):
        df[numeric_col] = _to_numeric(df[numeric_col])
    df["date"] = pd.to_datetime(df["date"])
    return df


# ─── Analytics Computations ──────────────────────────────────────────────────

class DailyReportAnalytics:
    """Core analytics engine operating on a DataFrame of daily reports."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.total_reports = len(df)

    # ---- 1. Attendance Analytics ----
    def attendance_summary(self) -> Dict[str, Any]:
        """Avg arrival/leave times per kindergarten, total reports per day."""
        if self.df.empty:
            return {"total_reports": 0, "avg_arrival": "--:--", "avg_leave": "--:--",
                    "daily_counts": [], "kindergarten_breakdown": []}

        avg_arr = self.df["arrival_minutes"].mean()
        avg_lv = self.df["leave_minutes"].mean()
        daily = self.df.groupby(self.df["date"].dt.strftime("%Y-%m-%d")).size().reset_index(name="count")
        daily.columns = ["date", "count"]

        kg_breakdown = []
        for kg_id, grp in self.df.groupby("kindergarten_id"):
            kg_breakdown.append({
                "kindergarten_id": int(kg_id),
                "total_reports": len(grp),
                "avg_arrival": _minutes_to_hhmm(grp["arrival_minutes"].mean()),
                "avg_leave": _minutes_to_hhmm(grp["leave_minutes"].mean()),
                "unique_children": int(grp["child_id"].nunique()),
            })

        return {
            "total_reports": self.total_reports,
            "avg_arrival": _minutes_to_hhmm(avg_arr),
            "avg_leave": _minutes_to_hhmm(avg_lv),
            "daily_counts": [
                {"date": str(r["date"]), "count": int(r["count"])}
                for r in daily.to_dict("records")
            ],
            "kindergarten_breakdown": kg_breakdown,
        }

    # ---- 2. Status Funnel ----
    def status_funnel(self) -> Dict[str, Any]:
        """Count by status + conversion rates."""
        if self.df.empty:
            return {"status_counts": {}, "conversion_rates": {}}

        # Cast out of numpy scalars: FastAPI's encoder cannot serialize int64.
        counts = {str(k): int(v) for k, v in self.df["status"].value_counts().items()}
        total = self.total_reports
        draft = counts.get("DRAFT", 0)
        submitted = counts.get("SUBMITTED", 0)
        approved = counts.get("APPROVED", 0)
        sent = counts.get("SENT_TO_PARENT", 0)
        rejected = counts.get("REJECTED", 0) + counts.get("RETURNED", 0)

        non_draft = total - draft
        return {
            "status_counts": counts,
            "conversion_rates": {
                "draft_to_submitted": round((non_draft / total * 100) if total else 0, 1),
                "submitted_to_approved": round(
                    (approved + sent) / (submitted + approved + sent + rejected) * 100, 1
                ) if (submitted + approved + sent + rejected) else None,
                "approved_to_sent": round(sent / (approved + sent) * 100, 1) if (approved + sent) else None,
                "rejection_rate": round((rejected / total * 100) if total else 0, 1),
            }
        }

    # ---- 3. Mood Trends ----
    def mood_trends(self) -> Dict[str, Any]:
        """Mood distribution overall + by day."""
        if self.df.empty:
            return {"overall": {}, "daily": []}

        # `mood` is already canonical (see `_normalize_mood`): lowercase, with
        # NULL/blank folded to 'unknown', so both the form vocabulary
        # (happy/normal/sad/tired/sick) and the seeded one
        # (HAPPY/CALM/ENERGETIC/TIRED/UPSET) land in the same buckets.
        moods = self.df["mood"].fillna(MOOD_UNKNOWN)
        overall = {
            str(k): round(float(v) * 100, 1)
            for k, v in moods.value_counts(normalize=True).items()
        }

        daily_group = (
            self.df.groupby([self.df["date"].dt.strftime("%Y-%m-%d"), "mood"])
            .size()
            .unstack(fill_value=0)
        )
        daily_list = []
        for dt, row in daily_group.iterrows():
            entry: Dict[str, Any] = {"date": str(dt)}
            entry.update({str(mood): int(count) for mood, count in row.items()})
            daily_list.append(entry)

        return {"overall": overall, "daily": daily_list}

    # ---- 4. Meal Completion ----
    def meal_completion(self) -> Dict[str, Any]:
        """Percentage of children eating each meal."""
        if self.df.empty:
            return {"breakfast": None, "snack": None, "milk": None, "lunch": None, "daily": []}

        meals = ["breakfast", "snack", "milk", "lunch"]
        rates = {}
        for m in meals:
            observed = self.df[m].dropna()
            rates[m] = round(observed.sum() / len(observed) * 100, 1) if len(observed) else None

        daily = []
        for dt, grp in self.df.groupby(self.df["date"].dt.strftime("%Y-%m-%d")):
            entry = {"date": dt, "total": len(grp)}
            for m in meals:
                observed = grp[m].dropna()
                entry[m] = round(observed.sum() / len(observed) * 100, 1) if len(observed) else None
            daily.append(entry)

        return {**rates, "daily": daily}

    # ---- 5. Nap Analytics ----
    def nap_analytics(self) -> Dict[str, Any]:
        """Avg nap duration, % nappers."""
        if self.df.empty:
            return {"avg_duration": None, "nap_rate": None, "by_kindergarten": []}

        nappers = self.df[self.df["nap_duration_minutes"].notna() & (self.df["nap_duration_minutes"] > 0)]
        avg_dur = nappers["nap_duration_minutes"].mean() if len(nappers) else None
        nap_rate = round(len(nappers) / self.total_reports * 100, 1) if self.total_reports else 0

        # Two whole-column aggregates instead of one frame slice per
        # kindergarten. Slicing inside the loop re-took every column for each
        # of the 446 production kindergartens and cost 0.95s of a 2.5s summary;
        # the aggregate below is 0.04s and yields the same numbers.
        totals = self.df.groupby("kindergarten_id").size()
        napper_stats = (
            nappers.groupby("kindergarten_id")["nap_duration_minutes"]
            .agg(["size", "mean"])
            .reindex(totals.index)
        )

        by_kg = []
        for kg_id, total, count, mean in zip(
            totals.index, totals.to_numpy(),
            napper_stats["size"].to_numpy(), napper_stats["mean"].to_numpy(),
        ):
            total = int(total)
            count = 0 if pd.isna(count) else int(count)
            by_kg.append({
                "kindergarten_id": int(kg_id),
                "avg_duration": round(mean, 1) if count else None,
                "nap_rate": round(count / total * 100, 1) if total else 0,
            })

        return {
            "avg_duration": round(avg_dur, 1) if avg_dur is not None else None,
            "nap_rate": nap_rate,
            "by_kindergarten": by_kg,
        }

    # ---- 6. Bathroom/Diaper Incidents ----
    def diaper_bathroom(self) -> Dict[str, Any]:
        """Daily totals and trends for bathroom/diaper events."""
        if self.df.empty:
            return {"avg_bathroom": None, "wet_rate": None, "soiled_rate": None, "daily": []}

        bathroom_observed = self.df["bathroom_count"].dropna()
        wet_observed = self.df["diaper_wet"].dropna()
        soiled_observed = self.df["diaper_soiled"].dropna()
        avg_bath = bathroom_observed.mean() if len(bathroom_observed) else None
        wet_rate = round(wet_observed.sum() / len(wet_observed) * 100, 1) if len(wet_observed) else None
        soiled_rate = round(soiled_observed.sum() / len(soiled_observed) * 100, 1) if len(soiled_observed) else None

        daily = []
        for dt, grp in self.df.groupby(self.df["date"].dt.strftime("%Y-%m-%d")):
            daily.append({
                "date": dt,
                "total_bathroom": int(grp["bathroom_count"].fillna(0).sum()),
                "wet_count": int(grp["diaper_wet"].fillna(False).sum()),
                "soiled_count": int(grp["diaper_soiled"].fillna(False).sum()),
            })

        return {
            "avg_bathroom": round(avg_bath, 1) if avg_bath is not None else None,
            "wet_rate": wet_rate,
            "soiled_rate": soiled_rate,
            "daily": daily,
        }

    # ---- 7. Workflow Metrics ----
    def workflow_metrics(self) -> Dict[str, Any]:
        """Submission-to-approval time, rejection analysis."""
        if self.df.empty:
            return {"avg_approval_hours": None, "rejection_rate": None, "top_rejection_reasons": [], "daily_approvals": []}

        # Time from submitted_at to approved_at
        approved = self.df[(self.df["submitted_at"].notna()) & (self.df["approved_at"].notna())].copy()
        if len(approved):
            approved["approval_time_hrs"] = (
                pd.to_datetime(approved["approved_at"]) - pd.to_datetime(approved["submitted_at"])
            ).dt.total_seconds() / 3600
            avg_hrs = approved["approval_time_hrs"].mean()
        else:
            avg_hrs = None

        # Rejections
        rejected = self.df[self.df["status"].isin(["REJECTED", "RETURNED"])]
        rej_rate = round(len(rejected) / self.total_reports * 100, 1) if self.total_reports else 0

        # Top rejection reasons
        if len(rejected) and rejected["rejected_reason"].notna().any():
            reasons = rejected["rejected_reason"].dropna().value_counts().head(5).to_dict()
        else:
            reasons = {}

        return {
            "avg_approval_hours": round(avg_hrs, 2) if avg_hrs is not None else None,
            "rejection_rate": rej_rate,
            "top_rejection_reasons": [{"reason": str(k), "count": int(v)} for k, v in reasons.items()],
        }

    # ---- 8. Health Flags ----
    MAX_FLAGGED_CHILDREN = 25

    def health_flags(self) -> Dict[str, Any]:
        """Flag sick moods + keyword search in health_notes."""
        if self.df.empty:
            return {"sick_count": 0, "sick_rate": None, "flagged_keywords": [], "flagged_children": []}

        keywords = ["fever", "حمى", "cough", "سعال", "vomit", "قيء", "rash", "طفح", "allergy", "حساسية",
                     "diarrhea", "إسهال", "pain", "ألم", "injury", "إصابة"]

        sick = self.df[self.df["mood"] == "sick"]
        sick_rate = round(len(sick) / self.total_reports * 100, 1) if self.total_reports else 0

        # Keyword flags in health_notes. When every note is NULL the column is
        # numeric (all-NaN), and the .str accessor raises on it — so work on an
        # explicitly string-typed copy of the non-null notes only.
        flagged = []
        notes = self.df["health_notes"].dropna().astype(str)
        if len(notes):
            for kw in keywords:
                count = int(notes.str.contains(kw, case=False, na=False, regex=False).sum())
                if count:
                    flagged.append({"keyword": kw, "count": count})

        # Children flagged multi-day sick — capped, and with a single name
        # lookup instead of one full-frame mask per child.
        sick_children = []
        if len(sick):
            names = sick.drop_duplicates("child_id").set_index("child_id")["child_name"].to_dict()
            child_sick_days = sick.groupby("child_id").size()
            multi_day = child_sick_days[child_sick_days >= 2].sort_values(ascending=False)
            for cid, days in multi_day.head(self.MAX_FLAGGED_CHILDREN).items():
                sick_children.append({
                    "child_id": int(cid),
                    "child_name": names.get(cid) or f"#{int(cid)}",
                    "sick_days": int(days),
                })

        return {
            "sick_count": int(len(sick)),
            "sick_rate": sick_rate,
            "flagged_keywords": flagged,
            "flagged_children": sick_children,
        }

    # ---- 9. Anomaly Detection ----
    #
    # Alert volume has to be bounded. On production data the default 9-day
    # window covers 446 kindergartens and 15,529 children, and an unbounded
    # absence rule emitted 11,562 alerts — a multi-megabyte payload and an
    # unreadable wall of banners. Each rule is capped and the remainder is
    # reported as a single roll-up alert.
    MAX_ALERTS_PER_RULE = 25

    def _kindergarten_names(self) -> Dict[int, tuple[str, str]]:
        """kindergarten_id -> (Arabic name, English name), falling back to '#id'."""
        if self.df.empty or "kindergarten_name_ar" not in self.df.columns:
            return {}
        # drop_duplicates keeps the first row per kindergarten in frame order —
        # the same row the old per-group `grp.iloc[0]` selected, since groupby
        # preserves the original order within each group. One pass instead of
        # 446 group slices.
        first_rows = self.df.drop_duplicates("kindergarten_id").sort_values("kindergarten_id")
        names = {}
        for kg_id, ar, en in zip(
            first_rows["kindergarten_id"].to_numpy(),
            first_rows["kindergarten_name_ar"].to_numpy(),
            first_rows["kindergarten_name_en"].to_numpy(),
        ):
            ar = ar if isinstance(ar, str) and ar.strip() else f"#{int(kg_id)}"
            en = en if isinstance(en, str) and en.strip() else ar
            names[int(kg_id)] = (ar, en)
        return names

    def _kg_label(self, kg_id: int, names: Dict[int, tuple[str, str]], english: bool = False) -> str:
        ar, en = names.get(int(kg_id), (f"#{int(kg_id)}", f"#{int(kg_id)}"))
        return en if english else ar

    def detect_anomalies(self, date_from: date, date_to: date) -> List[Dict[str, Any]]:
        """Flag: children with low attendance, high rejection, low meal rates."""
        alerts: List[Dict[str, Any]] = []
        if self.df.empty:
            return alerts

        kg_names = self._kindergarten_names()

        # ---- Children attending far fewer days than their kindergarten operated.
        # The denominator is the number of days the kindergarten actually filed
        # reports, not the calendar span: weekends and holidays inside the range
        # are not absences, and counting them flagged children with perfect
        # attendance.
        kg_operating_days = self.df.groupby("kindergarten_id")["date"].nunique()
        child_days = (
            self.df.groupby(["kindergarten_id", "child_id"])["date"]
            .nunique()
            .reset_index(name="present_days")
        )
        child_days["operating_days"] = child_days["kindergarten_id"].map(kg_operating_days)
        child_days["absent_days"] = child_days["operating_days"] - child_days["present_days"]
        # absent more than 40% of operating days, and at least 3 days
        child_days["threshold"] = (child_days["operating_days"] * 0.4).clip(lower=3)
        absentees = child_days[
            (child_days["operating_days"] >= 3)
            & (child_days["absent_days"] >= child_days["threshold"])
        ].sort_values(["absent_days", "child_id"], ascending=[False, True])

        # One name lookup for all of them — the previous per-child mask over the
        # full frame was O(children × rows) and dominated the request time.
        child_names = (
            self.df.drop_duplicates("child_id").set_index("child_id")["child_name"].to_dict()
        )

        for row in absentees.head(self.MAX_ALERTS_PER_RULE).itertuples(index=False):
            cid = int(row.child_id)
            name = child_names.get(cid) or f"#{cid}"
            absent_days = int(row.absent_days)
            operating_days = int(row.operating_days)
            alerts.append({
                "type": "absence",
                "severity": "high",
                "message": f"الطفل '{name}' غائب {absent_days} من {operating_days} أيام دوام",
                "message_en": f"Child '{name}' absent {absent_days} of {operating_days} operating days",
                "child_id": cid,
                "kindergarten_id": int(row.kindergarten_id),
            })

        hidden = max(len(absentees) - self.MAX_ALERTS_PER_RULE, 0)
        if hidden:
            alerts.append({
                "type": "absence_more",
                "severity": "high",
                "message": f"و{hidden} طفلاً آخر بنسبة حضور منخفضة",
                "message_en": f"and {hidden} more children with low attendance",
                "count": hidden,
            })

        # ---- Kindergartens with a high rejection rate (>20%)
        #
        # Four whole-column aggregates, then a walk over the 446 aggregated
        # rows. The previous per-kindergarten frame slices cost 0.55s; these
        # cost ~0.05s and produce the same counts in the same key order
        # (groupby sorts by kindergarten_id, as the old loop did).
        report_counts = self.df.groupby("kindergarten_id").size()
        rejected_counts = (
            self.df["status"].isin(["REJECTED", "RETURNED"])
            .groupby(self.df["kindergarten_id"]).sum()
        )
        breakfast = self.df["breakfast"]
        # Only reports that actually recorded breakfast count — a NULL is an
        # unfilled field, not a skipped meal.
        breakfast_observed_counts = breakfast.notna().groupby(self.df["kindergarten_id"]).sum()
        breakfast_eaten_counts = (
            breakfast.fillna(False).astype(bool).groupby(self.df["kindergarten_id"]).sum()
        )

        rejection_alerts: List[Dict[str, Any]] = []
        low_meal_alerts: List[Dict[str, Any]] = []
        for kg_id, report_count in zip(report_counts.index, report_counts.to_numpy()):
            report_count = int(report_count)
            if report_count < 5:
                continue
            kg_id = int(kg_id)
            name_ar = self._kg_label(kg_id, kg_names)
            name_en = self._kg_label(kg_id, kg_names, english=True)

            rejected = int(rejected_counts.at[kg_id])
            if rejected / report_count > 0.2:
                rate = round(rejected / report_count * 100, 1)
                rejection_alerts.append({
                    "type": "high_rejection",
                    "severity": "medium",
                    "message": f"حضانة {name_ar}: نسبة رفض عالية {rate}%",
                    "message_en": f"Kindergarten {name_en} has a {rate}% rejection rate",
                    "kindergarten_id": kg_id,
                    "rate": rate,
                })

            breakfast_observed = int(breakfast_observed_counts.at[kg_id])
            if breakfast_observed >= 5:
                bf_rate = round(int(breakfast_eaten_counts.at[kg_id]) / breakfast_observed * 100, 1)
                if bf_rate < 50:
                    low_meal_alerts.append({
                        "type": "low_meal",
                        "severity": "medium",
                        "message": f"حضانة {name_ar}: نسبة الإفطار منخفضة {bf_rate}% — يُقترح تغيير قائمة الطعام",
                        "message_en": f"Kindergarten {name_en} has a {bf_rate}% breakfast rate — suggest a menu change",
                        "kindergarten_id": kg_id,
                        "rate": bf_rate,
                    })

        for bucket, more_type, msg_ar, msg_en in (
            (rejection_alerts, "high_rejection_more", "حضانة أخرى بنسبة رفض عالية", "more kindergartens with a high rejection rate"),
            (low_meal_alerts, "low_meal_more", "حضانة أخرى بنسبة إفطار منخفضة", "more kindergartens with a low breakfast rate"),
        ):
            bucket.sort(key=lambda a: a["rate"], reverse=(more_type == "high_rejection_more"))
            alerts.extend(bucket[: self.MAX_ALERTS_PER_RULE])
            hidden = max(len(bucket) - self.MAX_ALERTS_PER_RULE, 0)
            if hidden:
                alerts.append({
                    "type": more_type,
                    "severity": "medium",
                    "message": f"و{hidden} {msg_ar}",
                    "message_en": f"and {hidden} {msg_en}",
                    "count": hidden,
                })

        return alerts

    # ---- Full Dashboard Summary ----
    def full_summary(self, date_from: date, date_to: date) -> Dict[str, Any]:
        """Complete analytics payload."""
        return {
            "period": {"from": str(date_from), "to": str(date_to)},
            "total_reports": self.total_reports,
            "attendance": self.attendance_summary(),
            "status_funnel": self.status_funnel(),
            "mood_trends": self.mood_trends(),
            "meal_completion": self.meal_completion(),
            "nap_analytics": self.nap_analytics(),
            "diaper_bathroom": self.diaper_bathroom(),
            "workflow_metrics": self.workflow_metrics(),
            "health_flags": self.health_flags(),
            "anomalies": self.detect_anomalies(date_from, date_to),
        }


# ─── Plotly Visualization Generators ──────────────────────────────────────────

class DailyReportViz:
    """Generate Plotly charts from analytics data."""

    # Covers both live mood vocabularies (see `_normalize_mood`).
    COLORS = {
        "happy": "#28a745",
        "calm": "#20c997",
        "energetic": "#0dcaf0",
        "normal": "#6c757d",
        "sad": "#ffc107",
        "tired": "#fd7e14",
        "upset": "#d63384",
        "sick": "#dc3545",
        "unknown": "#adb5bd",
    }

    MOOD_LABELS = {
        "happy": "سعيد",
        "calm": "هادئ",
        "energetic": "نشيط",
        "normal": "عادي",
        "sad": "حزين",
        "tired": "متعب",
        "upset": "منزعج",
        "sick": "مريض",
        "unknown": "غير محدد",
    }

    MOOD_LABELS_EN = {
        "happy": "Happy",
        "calm": "Calm",
        "energetic": "Energetic",
        "normal": "Normal",
        "sad": "Sad",
        "tired": "Tired",
        "upset": "Upset",
        "sick": "Sick",
        "unknown": "Unknown",
    }

    @staticmethod
    def _to_json(fig: go.Figure) -> str:
        """Serialize figure to JSON for frontend rendering."""
        return json.loads(plotly.io.to_json(fig))

    @staticmethod
    def _t(lang: str, ar: str, en: str) -> str:
        """Pick a chart string for the requested UI language (Arabic default)."""
        return en if lang == "en" else ar

    @classmethod
    def _mood_label(cls, key: str, lang: str = "ar") -> str:
        table = cls.MOOD_LABELS_EN if lang == "en" else cls.MOOD_LABELS
        return table.get(key, key)

    @classmethod
    def mood_pie(cls, mood_data: Dict[str, float], lang: str = "ar") -> dict:
        """Pie chart: mood distribution percentages."""
        labels = [cls._mood_label(k, lang) for k in mood_data.keys()]
        values = list(mood_data.values())
        colors = [cls.COLORS.get(k, "#adb5bd") for k in mood_data.keys()]

        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            textinfo="label+percent",
            hole=0.4,
        )])
        fig.update_layout(
            title=dict(text=cls._t(lang, "توزيع المزاج", "Mood distribution"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            font=dict(family="Cairo"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def mood_line(cls, daily_moods: List[Dict], lang: str = "ar") -> dict:
        """Line chart: mood trends over time."""
        if not daily_moods:
            return {}
        df = pd.DataFrame(daily_moods).set_index("date")
        fig = go.Figure()
        # Iterate the canonical vocabulary, not a hardcoded subset: the seeded
        # moods (calm/energetic/upset) were silently dropped and the chart came
        # back empty for every kindergarten using them.
        for mood in MOOD_ORDER:
            if mood in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[mood],
                    name=cls._mood_label(mood, lang),
                    mode="lines+markers",
                    line=dict(color=cls.COLORS.get(mood)),
                ))
        fig.update_layout(
            title=dict(text=cls._t(lang, "اتجاهات المزاج اليومية", "Daily mood trends"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "التاريخ", "Date"),
            yaxis_title=cls._t(lang, "عدد الأطفال", "Children"),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
            legend=dict(orientation="h", y=-0.15),
        )
        return cls._to_json(fig)

    MEAL_LABELS = {
        "breakfast": ("الإفطار", "Breakfast"),
        "snack": ("وجبة خفيفة", "Snack"),
        "milk": ("الحليب", "Milk"),
        "lunch": ("الغداء", "Lunch"),
    }

    @classmethod
    def meal_bar(cls, meal_data: Dict[str, float], lang: str = "ar") -> dict:
        """Bar chart: meal compliance rates."""
        meals = ["breakfast", "snack", "milk", "lunch"]
        names = [cls._t(lang, *cls.MEAL_LABELS[k]) for k in meals]
        # A meal with no observations is unknown, not 0% — plot nothing for it.
        values = [meal_data.get(k) for k in meals]
        colors = ["#0d6efd", "#6610f2", "#20c997", "#fd7e14"]

        fig = go.Figure(data=[go.Bar(
            x=names, y=values,
            marker_color=colors,
            text=["—" if v is None else f"{v}%" for v in values],
            textposition="auto",
        )])
        fig.update_layout(
            title=dict(text=cls._t(lang, "نسب تناول الوجبات", "Meal completion rates"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            yaxis_title=cls._t(lang, "النسبة (%)", "Percentage (%)"), yaxis=dict(range=[0, 100]),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def status_funnel_chart(cls, status_counts: Dict[str, int], lang: str = "ar") -> dict:
        """Funnel chart: report workflow status."""
        status_labels = {
            "DRAFT": ("مسودة", "Draft"),
            "SUBMITTED": ("مقدم", "Submitted"),
            "APPROVED": ("معتمد", "Approved"),
            "SENT_TO_PARENT": ("مرسل لولي الأمر", "Sent to parent"),
            "REJECTED": ("مرفوض", "Rejected"),
            "RETURNED": ("معاد", "Returned"),
        }
        order = ["DRAFT", "SUBMITTED", "APPROVED", "SENT_TO_PARENT", "REJECTED", "RETURNED"]
        present = [s for s in order if status_counts.get(s, 0) > 0]
        labels = [cls._t(lang, *status_labels[s]) if s in status_labels else s for s in present]
        values = [status_counts.get(s, 0) for s in present]

        fig = go.Figure(go.Funnel(
            y=labels, x=values,
            textinfo="value+percent initial",
            marker=dict(color=["#6c757d", "#0d6efd", "#198754", "#0dcaf0", "#dc3545", "#fd7e14"][:len(labels)]),
        ))
        fig.update_layout(
            title=dict(text=cls._t(lang, "مسار حالة التقرير", "Report status funnel"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            font=dict(family="Cairo"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def attendance_line(cls, daily_counts: List[Dict], lang: str = "ar") -> dict:
        """Line chart: daily attendance count."""
        if not daily_counts:
            return {}
        df = pd.DataFrame(daily_counts)
        fig = go.Figure(data=[go.Scatter(
            x=df["date"], y=df["count"],
            mode="lines+markers+text",
            text=df["count"].astype(str),
            textposition="top center",
            line=dict(color="#0d6efd", width=3),
            marker=dict(size=8),
        )])
        fig.update_layout(
            title=dict(text=cls._t(lang, "تقارير الحضور اليومية", "Daily attendance reports"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "التاريخ", "Date"),
            yaxis_title=cls._t(lang, "عدد التقارير", "Reports"),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def rejection_bar(cls, reasons: List[Dict], lang: str = "ar") -> dict:
        """Horizontal bar chart: top rejection reasons."""
        if not reasons:
            return {}
        df = pd.DataFrame(reasons)
        fig = go.Figure(data=[go.Bar(
            y=df["reason"], x=df["count"],
            orientation="h",
            marker_color="#dc3545",
            text=df["count"].astype(str),
            textposition="auto",
        )])
        fig.update_layout(
            title=dict(text=cls._t(lang, "أسباب الرفض الأكثر شيوعاً", "Most common rejection reasons"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "العدد", "Count"),
            font=dict(family="Cairo"),
            margin=dict(l=200, r=20, t=50, b=40),
            height=max(200, len(reasons) * 50 + 100),
        )
        return cls._to_json(fig)

    @classmethod
    def nap_histogram(cls, nap_durations: pd.Series, lang: str = "ar") -> dict:
        """Histogram: nap duration distribution."""
        valid = nap_durations.dropna()
        if valid.empty:
            return {}
        fig = go.Figure(data=[go.Histogram(
            x=valid, nbinsx=10,
            marker_color="#6f42c1",
        )])
        fig.update_layout(
            title=dict(text=cls._t(lang, "توزيع مدة القيلولة (دقيقة)", "Nap duration distribution (minutes)"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "المدة (دقيقة)", "Duration (minutes)"),
            yaxis_title=cls._t(lang, "العدد", "Count"),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=300,
        )
        return cls._to_json(fig)

    @classmethod
    def diaper_trend(cls, daily_data: List[Dict], lang: str = "ar") -> dict:
        """Stacked bar chart: bathroom + diaper trends."""
        if not daily_data:
            return {}
        df = pd.DataFrame(daily_data)
        fig = go.Figure()
        fig.add_trace(go.Bar(name=cls._t(lang, "دخول الحمام", "Bathroom visits"),
                             x=df["date"], y=df["total_bathroom"], marker_color="#0d6efd"))
        fig.add_trace(go.Bar(name=cls._t(lang, "حفاض مبلل", "Wet diapers"),
                             x=df["date"], y=df["wet_count"], marker_color="#ffc107"))
        fig.add_trace(go.Bar(name=cls._t(lang, "حفاض متسخ", "Soiled diapers"),
                             x=df["date"], y=df["soiled_count"], marker_color="#fd7e14"))
        fig.update_layout(
            barmode="group",
            title=dict(text=cls._t(lang, "اتجاه الحمام والحفاضات", "Bathroom and diaper trend"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "التاريخ", "Date"),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
            legend=dict(orientation="h", y=-0.15),
        )
        return cls._to_json(fig)

    @classmethod
    def meal_trend_line(cls, daily_meals: List[Dict], lang: str = "ar") -> dict:
        """Multi-line chart: meal compliance over days."""
        if not daily_meals:
            return {}
        df = pd.DataFrame(daily_meals)
        colors = {"breakfast": "#0d6efd", "snack": "#6610f2", "milk": "#20c997", "lunch": "#fd7e14"}
        fig = go.Figure()
        for meal in ["breakfast", "snack", "milk", "lunch"]:
            if meal in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df[meal],
                    name=cls._t(lang, *cls.MEAL_LABELS[meal]),
                    mode="lines+markers",
                    line=dict(color=colors[meal]),
                ))
        fig.update_layout(
            title=dict(text=cls._t(lang, "اتجاه الوجبات اليومية", "Daily meal trend"),
                       x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title=cls._t(lang, "التاريخ", "Date"),
            yaxis_title=cls._t(lang, "النسبة (%)", "Percentage (%)"),
            yaxis=dict(range=[0, 100]),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
            legend=dict(orientation="h", y=-0.15),
        )
        return cls._to_json(fig)


# ─── SQL Queries (Reference / Documentation) ─────────────────────────────────

SQL_QUERIES = {
    "1_daily_attendance": """
-- Daily attendance: average arrival/leave per kindergarten
SELECT
    kindergarten_id,
    date,
    COUNT(*) AS total_children,
    COUNT(DISTINCT child_id) AS unique_children,
    AVG(CAST(SUBSTR(arrival_time, 1, 2) AS INTEGER) * 60 + CAST(SUBSTR(arrival_time, 4, 2) AS INTEGER)) AS avg_arrival_min,
    AVG(CAST(SUBSTR(leave_time, 1, 2) AS INTEGER) * 60 + CAST(SUBSTR(leave_time, 4, 2) AS INTEGER)) AS avg_leave_min
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
  AND (:kg_id IS NULL OR kindergarten_id = :kg_id)
GROUP BY kindergarten_id, date
ORDER BY date;
""",

    "2_status_funnel": """
-- Status funnel with conversion rates
SELECT
    status,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
GROUP BY status
ORDER BY CASE status
    WHEN 'DRAFT' THEN 1 WHEN 'SUBMITTED' THEN 2
    WHEN 'APPROVED' THEN 3 WHEN 'SENT_TO_PARENT' THEN 4
    WHEN 'REJECTED' THEN 5 WHEN 'RETURNED' THEN 6
END;
""",

    "3_mood_trends": """
-- Mood distribution per day (pivot-ready)
SELECT
    date,
    mood,
    COUNT(*) AS cnt,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(PARTITION BY date), 1) AS pct
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
  AND mood IS NOT NULL
GROUP BY date, mood
ORDER BY date, mood;
""",

    "4_meal_completion": """
-- Meal completion rates
SELECT
    ROUND(SUM(CASE WHEN breakfast = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS breakfast_pct,
    ROUND(SUM(CASE WHEN snack = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS snack_pct,
    ROUND(SUM(CASE WHEN milk = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS milk_pct,
    ROUND(SUM(CASE WHEN lunch = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS lunch_pct
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to;
""",

    "5_nap_analytics": """
-- Nap analytics: avg duration, napper percentage
SELECT
    kindergarten_id,
    COUNT(*) AS total,
    SUM(CASE WHEN nap_duration_minutes > 0 THEN 1 ELSE 0 END) AS nappers,
    ROUND(AVG(CASE WHEN nap_duration_minutes > 0 THEN nap_duration_minutes END), 1) AS avg_nap_min,
    ROUND(SUM(CASE WHEN nap_duration_minutes > 0 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS nap_pct
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
GROUP BY kindergarten_id;
""",

    "6_diaper_bathroom": """
-- Bathroom/diaper daily incident totals
SELECT
    date,
    SUM(bathroom_count) AS total_bathroom,
    SUM(CASE WHEN diaper_wet = 1 THEN 1 ELSE 0 END) AS wet_count,
    SUM(CASE WHEN diaper_soiled = 1 THEN 1 ELSE 0 END) AS soiled_count
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
GROUP BY date
ORDER BY date;
""",

    "7_workflow_metrics": """
-- Workflow: avg submission-to-approval time + rejection analysis
SELECT
    AVG(JULIANDAY(approved_at) - JULIANDAY(submitted_at)) * 24 AS avg_approval_hours,
    SUM(CASE WHEN status IN ('REJECTED', 'RETURNED') THEN 1 ELSE 0 END) AS rejection_count,
    ROUND(SUM(CASE WHEN status IN ('REJECTED', 'RETURNED') THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS rejection_pct
FROM daily_reports
WHERE date BETWEEN :date_from AND :date_to
  AND submitted_at IS NOT NULL;
""",

    "8_health_flags": """
-- Health flags: sick mood + keyword search
SELECT
    dr.child_id,
    c.first_name || ' ' || c.last_name AS child_name,
    COUNT(*) AS sick_days,
    GROUP_CONCAT(dr.health_notes, '; ') AS health_notes_combined
FROM daily_reports dr
JOIN children c ON dr.child_id = c.id
WHERE dr.date BETWEEN :date_from AND :date_to
  AND (dr.mood = 'sick' OR dr.health_notes LIKE '%fever%' OR dr.health_notes LIKE '%cough%'
       OR dr.health_notes LIKE '%حمى%' OR dr.health_notes LIKE '%سعال%')
GROUP BY dr.child_id
ORDER BY sick_days DESC;
""",

    "9_child_absence_flag": """
-- Absent children: had a report in the period but missing days
WITH date_range AS (
    SELECT DISTINCT date FROM daily_reports WHERE date BETWEEN :date_from AND :date_to
),
child_presence AS (
    SELECT child_id, COUNT(DISTINCT date) AS present_days
    FROM daily_reports
    WHERE date BETWEEN :date_from AND :date_to
    GROUP BY child_id
)
SELECT
    cp.child_id,
    c.first_name || ' ' || c.last_name AS child_name,
    cp.present_days,
    (SELECT COUNT(*) FROM date_range) - cp.present_days AS absent_days
FROM child_presence cp
JOIN children c ON cp.child_id = c.id
WHERE absent_days >= 3
ORDER BY absent_days DESC;
""",

    "10_kindergarten_heatmap": """
-- Kindergarten x child metric heatmap
SELECT
    k.name_ar AS kindergarten_name,
    dr.kindergarten_id,
    COUNT(*) AS report_count,
    ROUND(AVG(CASE WHEN dr.mood = 'happy' THEN 1 ELSE 0 END) * 100, 1) AS happy_pct,
    ROUND(AVG(CASE WHEN dr.breakfast = 1 THEN 1 ELSE 0 END) * 100, 1) AS breakfast_pct,
    ROUND(AVG(COALESCE(dr.nap_duration_minutes, 0)), 1) AS avg_nap_min,
    ROUND(AVG(dr.bathroom_count), 1) AS avg_bathroom
FROM daily_reports dr
JOIN kindergartens k ON dr.kindergarten_id = k.id
WHERE dr.date BETWEEN :date_from AND :date_to
GROUP BY dr.kindergarten_id;
""",
}


# ─── API Endpoints ───────────────────────────────────────────────────────────

@router.get("/summary")
def get_analytics_summary(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    kindergarten_id: Optional[int] = Query(None),
    child_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full analytics summary JSON."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)
    child_ids = [child_id] if child_id else None

    df = _load_reports_df(db, d_from, d_to, kg_ids, child_ids, status, analytics_only=True)
    analytics = DailyReportAnalytics(df)
    return analytics.full_summary(d_from, d_to)


@router.get("/charts")
def get_analytics_charts(
    request: Request,
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    kindergarten_id: Optional[int] = Query(None),
    lang: Optional[str] = Query(None, description="Chart label language: ar or en"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All Plotly chart JSONs for frontend rendering."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)
    # Chart titles, axes and legends live inside the Plotly payload, so the
    # language has to be resolved server-side. An explicit ?lang wins — the
    # caller is the dashboard telling us which language it rendered itself in.
    # Without one, defer to the site-wide language policy for the cookie.
    requested = (lang or "").strip().lower()
    ui_lang = requested if requested in {"ar", "en"} else _normalize_ui_language(
        request.cookies.get("kinjo_lang")
    )

    df = _load_reports_df(db, d_from, d_to, kg_ids, analytics_only=True)
    if df.empty:
        return {"charts": {}, "message": "No data for the selected period"}

    analytics = DailyReportAnalytics(df)
    summary = analytics.full_summary(d_from, d_to)

    charts = {
        "mood_pie": DailyReportViz.mood_pie(summary["mood_trends"]["overall"], ui_lang),
        "mood_line": DailyReportViz.mood_line(summary["mood_trends"]["daily"], ui_lang),
        "meal_bar": DailyReportViz.meal_bar(summary["meal_completion"], ui_lang),
        "meal_trend": DailyReportViz.meal_trend_line(summary["meal_completion"]["daily"], ui_lang),
        "status_funnel": DailyReportViz.status_funnel_chart(summary["status_funnel"]["status_counts"], ui_lang),
        "attendance_line": DailyReportViz.attendance_line(summary["attendance"]["daily_counts"], ui_lang),
        "rejection_bar": DailyReportViz.rejection_bar(summary["workflow_metrics"]["top_rejection_reasons"], ui_lang),
        "nap_histogram": DailyReportViz.nap_histogram(df["nap_duration_minutes"], ui_lang),
        "diaper_trend": DailyReportViz.diaper_trend(summary["diaper_bathroom"]["daily"], ui_lang),
    }
    return {"charts": charts}


@router.get("/export")
def export_analytics(
    date_from: str = Query(...),
    date_to: str = Query(...),
    format: str = Query("csv", description="csv or json"),
    kindergarten_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Export raw analytics data as CSV or JSON."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)
    df = _load_reports_df(db, d_from, d_to, kg_ids)

    if df.empty:
        raise HTTPException(404, "No data for the selected period")

    # Convert datetime columns for serialization
    for col in ["date", "submitted_at", "approved_at", "sent_to_parent_at", "created_at", "child_dob"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    # Replace NaN with None for JSON compliance
    df = df.where(df.notna(), None)

    if format == "json":
        records = df.to_dict("records")
        content = json.dumps(records, ensure_ascii=False, indent=2, default=str)
        return StreamingResponse(
            io.BytesIO(content.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=analytics_{date_from}_{date_to}.json"},
        )

    # CSV with BOM for Arabic/Excel
    buf = io.StringIO()
    buf.write("\ufeff")
    df.to_csv(buf, index=False)
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=analytics_{date_from}_{date_to}.csv"},
    )


@router.get("/sql-queries")
def list_sql_queries(user: User = Depends(get_current_user)):
    """Return all reference SQL queries for documentation."""
    if user.role not in [UserRole.ADMIN, UserRole.SUPERVISOR]:
        raise HTTPException(403, "Only admin/supervisor can view SQL queries")
    return {"queries": SQL_QUERIES}


@router.get("/anomalies")
def get_anomalies(
    date_from: str = Query(...),
    date_to: str = Query(...),
    kindergarten_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get anomaly alerts."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)
    df = _load_reports_df(db, d_from, d_to, kg_ids)
    analytics = DailyReportAnalytics(df)
    return {"anomalies": analytics.detect_anomalies(d_from, d_to)}


@router.get("/sample-data")
def get_sample_data(
    date_from: str = Query(...),
    date_to: str = Query(...),
    kindergarten_id: Optional[int] = Query(None),
    limit: int = Query(10),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return top N rows of raw report data."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)
    df = _load_reports_df(db, d_from, d_to, kg_ids)
    if df.empty:
        return {"rows": [], "total": 0}

    sample = df.head(limit).copy()
    for col in ["date", "submitted_at", "approved_at", "sent_to_parent_at", "created_at", "child_dob"]:
        if col in sample.columns:
            sample[col] = sample[col].astype(str)

    # Replace NaN/NaT with None for JSON compliance
    records = json.loads(sample.to_json(orient="records", default_handler=str))

    return {"rows": records, "total": len(df)}


# ─── Frontend Route ──────────────────────────────────────────────────────────

@frontend_router.get("/reports/analytics", response_class=HTMLResponse)
def analytics_dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Render the interactive analytics dashboard HTML page."""
    if user.role == UserRole.PARENT:
        raise HTTPException(403, "Parents cannot access analytics dashboards")

    # Get available kindergartens for filter dropdown
    if user.role in (UserRole.MANAGER, UserRole.SUPERVISOR):
        allowed_ids = _enforce_analytics_rbac(user, None)
        kindergartens = db.query(Kindergarten).filter(Kindergarten.id.in_(allowed_ids)).all()
    else:
        kindergartens = db.query(Kindergarten).filter(Kindergarten.status == KindergartenStatus.ACTIVE).all()

    return templates.TemplateResponse(
        request=request,
        name="reports/analytics_dashboard.html",
        context={
            "user": user,
            "kindergartens": kindergartens,
            "default_date_from": (_today() - timedelta(days=8)).isoformat(),
            "default_date_to": _today().isoformat(),
        }
    )
