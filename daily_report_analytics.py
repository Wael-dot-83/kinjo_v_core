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
    normalized = (value or "ar").strip().lower()
    return normalized if normalized in {"ar", "en"} else "ar"


def _language_context_processor(request: Request) -> dict:
    lang = _normalize_ui_language(request.cookies.get("kinjo_lang"))
    return {"ui_lang": lang, "ui_dir": "rtl" if lang == "ar" else "ltr"}


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


def _hhmm_to_minutes(t: str | None) -> int | None:
    """Convert 'HH:MM' to minutes since midnight."""
    if not t:
        return None
    try:
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return None


def _minutes_to_hhmm(m: float | None) -> str:
    """Convert minutes since midnight back to 'HH:MM'."""
    if m is None or pd.isna(m):
        return "--:--"
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


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


def _load_reports_df(db: Session, date_from: date, date_to: date,
                     kindergarten_ids: List[int] | None = None,
                     child_ids: List[int] | None = None,
                     status_filter: str | None = None) -> pd.DataFrame:
    """
    Load DailyReport rows into a Pandas DataFrame with child/class info.
    """
    q = db.query(
        DailyReport.id,
        DailyReport.child_id,
        DailyReport.kindergarten_id,
        DailyReport.date,
        DailyReport.status,
        DailyReport.submitted_by,
        DailyReport.submitted_at,
        DailyReport.approved_by,
        DailyReport.approved_at,
        DailyReport.sent_to_parent_at,
        DailyReport.rejected_reason,
        DailyReport.arrival_time,
        DailyReport.leave_time,
        DailyReport.mood,
        DailyReport.health_notes,
        DailyReport.breakfast,
        DailyReport.snack,
        DailyReport.milk,
        DailyReport.lunch,
        DailyReport.nap_start,
        DailyReport.nap_end,
        DailyReport.nap_duration_minutes,
        DailyReport.bathroom_count,
        DailyReport.diaper_wet,
        DailyReport.diaper_soiled,
        DailyReport.activities,
        DailyReport.notes,
        DailyReport.created_at,
        Child.first_name.label("child_first_name"),
        Child.last_name.label("child_last_name"),
        Child.date_of_birth.label("child_dob"),
    ).join(Child, DailyReport.child_id == Child.id
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

    df = pd.DataFrame(rows, columns=[
        "id", "child_id", "kindergarten_id", "date", "status",
        "submitted_by", "submitted_at", "approved_by", "approved_at",
        "sent_to_parent_at", "rejected_reason",
        "arrival_time", "leave_time", "mood", "health_notes",
        "breakfast", "snack", "milk", "lunch",
        "nap_start", "nap_end", "nap_duration_minutes",
        "bathroom_count", "diaper_wet", "diaper_soiled",
        "activities", "notes", "created_at",
        "child_first_name", "child_last_name", "child_dob",
    ])
    df["child_name"] = df["child_first_name"] + " " + df["child_last_name"]
    df["status"] = df["status"].apply(lambda s: s.value if hasattr(s, "value") else str(s))
    df["arrival_minutes"] = df["arrival_time"].apply(_hhmm_to_minutes)
    df["leave_minutes"] = df["leave_time"].apply(_hhmm_to_minutes)
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
            "daily_counts": daily.to_dict("records"),
            "kindergarten_breakdown": kg_breakdown,
        }

    # ---- 2. Status Funnel ----
    def status_funnel(self) -> Dict[str, Any]:
        """Count by status + conversion rates."""
        if self.df.empty:
            return {"status_counts": {}, "conversion_rates": {}}

        counts = self.df["status"].value_counts().to_dict()
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
                "submitted_to_approved": round(((approved + sent) / (submitted + approved + sent + rejected) * 100)
                                               if (submitted + approved + sent + rejected) else 0, 1),
                "approved_to_sent": round((sent / (approved + sent) * 100) if (approved + sent) else 0, 1),
                "rejection_rate": round((rejected / total * 100) if total else 0, 1),
            }
        }

    # ---- 3. Mood Trends ----
    def mood_trends(self) -> Dict[str, Any]:
        """Mood distribution overall + by day."""
        if self.df.empty:
            return {"overall": {}, "daily": []}

        moods = self.df["mood"].fillna("unknown")
        overall = moods.value_counts(normalize=True).apply(lambda x: round(x * 100, 1)).to_dict()

        daily_moods = self.df.copy()
        daily_moods["mood"] = daily_moods["mood"].fillna("unknown")
        daily_group = daily_moods.groupby([daily_moods["date"].dt.strftime("%Y-%m-%d"), "mood"]).size().unstack(fill_value=0)
        daily_list = []
        for dt, row in daily_group.iterrows():
            entry = {"date": dt}
            entry.update(row.to_dict())
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

        by_kg = []
        for kg_id, grp in self.df.groupby("kindergarten_id"):
            kg_nappers = grp[grp["nap_duration_minutes"].notna() & (grp["nap_duration_minutes"] > 0)]
            by_kg.append({
                "kindergarten_id": int(kg_id),
                "avg_duration": round(kg_nappers["nap_duration_minutes"].mean(), 1) if len(kg_nappers) else None,
                "nap_rate": round(len(kg_nappers) / len(grp) * 100, 1) if len(grp) else 0,
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
            return {"avg_bathroom": 0, "wet_rate": 0, "soiled_rate": 0, "daily": []}

        avg_bath = self.df["bathroom_count"].fillna(0).mean()
        wet_rate = round(self.df["diaper_wet"].fillna(False).sum() / self.total_reports * 100, 1)
        soiled_rate = round(self.df["diaper_soiled"].fillna(False).sum() / self.total_reports * 100, 1)

        daily = []
        for dt, grp in self.df.groupby(self.df["date"].dt.strftime("%Y-%m-%d")):
            daily.append({
                "date": dt,
                "total_bathroom": int(grp["bathroom_count"].fillna(0).sum()),
                "wet_count": int(grp["diaper_wet"].fillna(False).sum()),
                "soiled_count": int(grp["diaper_soiled"].fillna(False).sum()),
            })

        return {
            "avg_bathroom": round(avg_bath, 1),
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
            "top_rejection_reasons": [{"reason": k, "count": int(v)} for k, v in reasons.items()],
        }

    # ---- 8. Health Flags ----
    def health_flags(self) -> Dict[str, Any]:
        """Flag sick moods + keyword search in health_notes."""
        if self.df.empty:
            return {"sick_count": 0, "sick_rate": None, "flagged_keywords": [], "flagged_children": []}

        keywords = ["fever", "حمى", "cough", "سعال", "vomit", "قيء", "rash", "طفح", "allergy", "حساسية",
                     "diarrhea", "إسهال", "pain", "ألم", "injury", "إصابة"]

        sick = self.df[self.df["mood"] == "sick"]
        sick_rate = round(len(sick) / self.total_reports * 100, 1) if self.total_reports else 0

        # Keyword flags in health_notes
        flagged = []
        notes_df = self.df[self.df["health_notes"].notna()]
        for kw in keywords:
            matches = notes_df[notes_df["health_notes"].str.contains(kw, case=False, na=False)]
            if len(matches):
                flagged.append({"keyword": kw, "count": len(matches)})

        # Children flagged multi-day sick
        sick_children = []
        if len(sick):
            child_sick_days = sick.groupby("child_id").size()
            multi_day = child_sick_days[child_sick_days >= 2]
            for cid, days in multi_day.items():
                child_row = sick[sick["child_id"] == cid].iloc[0]
                sick_children.append({
                    "child_id": int(cid),
                    "child_name": child_row["child_name"],
                    "sick_days": int(days),
                })

        return {
            "sick_count": len(sick),
            "sick_rate": sick_rate,
            "flagged_keywords": flagged,
            "flagged_children": sick_children,
        }

    # ---- 9. Anomaly Detection ----
    def detect_anomalies(self, date_from: date, date_to: date) -> List[Dict[str, Any]]:
        """Flag: child absent >3 days, high rejection kindergarten, low meal rates."""
        alerts = []
        if self.df.empty:
            return alerts

        num_days = (date_to - date_from).days + 1

        # Children with reports for less than 60% of the period
        child_days = self.df.groupby("child_id")["date"].nunique()
        absent_threshold = max(num_days * 0.4, 3)  # absent more than 40% or more than 3 days
        for cid, present_days in child_days.items():
            absent_days = num_days - present_days
            if absent_days >= absent_threshold:
                name = self.df[self.df["child_id"] == cid]["child_name"].iloc[0]
                alerts.append({
                    "type": "absence",
                    "severity": "high",
                    "message": f"طفل '{name}' غائب {absent_days} من {num_days} أيام",
                    "message_en": f"Child '{name}' absent {absent_days} of {num_days} days",
                    "child_id": int(cid),
                })

        # Kindergarten with high rejection rate (>20%)
        for kg_id, grp in self.df.groupby("kindergarten_id"):
            rej = grp[grp["status"].isin(["REJECTED", "RETURNED"])]
            if len(grp) >= 5 and len(rej) / len(grp) > 0.2:
                rate = round(len(rej) / len(grp) * 100, 1)
                alerts.append({
                    "type": "high_rejection",
                    "severity": "medium",
                    "message": f"حضانة #{kg_id} نسبة رفض عالية {rate}%",
                    "message_en": f"Kindergarten #{kg_id} has {rate}% rejection rate",
                    "kindergarten_id": int(kg_id),
                })

        # Low breakfast rate kindergarten (<50%)
        for kg_id, grp in self.df.groupby("kindergarten_id"):
            if len(grp) >= 5:
                bf_rate = grp["breakfast"].fillna(False).sum() / len(grp) * 100
                if bf_rate < 50:
                    alerts.append({
                        "type": "low_meal",
                        "severity": "medium",
                        "message": f"حضانة #{kg_id} نسبة الإفطار منخفضة {round(bf_rate, 1)}% — يُقترح تغيير قائمة الطعام",
                        "message_en": f"Kindergarten #{kg_id} has {round(bf_rate, 1)}% breakfast rate—suggest menu change",
                        "kindergarten_id": int(kg_id),
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

    COLORS = {
        "happy": "#28a745",
        "normal": "#6c757d",
        "sad": "#ffc107",
        "tired": "#fd7e14",
        "sick": "#dc3545",
        "unknown": "#adb5bd",
    }

    MOOD_LABELS = {
        "happy": "سعيد",
        "normal": "عادي",
        "sad": "حزين",
        "tired": "متعب",
        "sick": "مريض",
        "unknown": "غير محدد",
    }

    @staticmethod
    def _to_json(fig: go.Figure) -> str:
        """Serialize figure to JSON for frontend rendering."""
        return json.loads(plotly.io.to_json(fig))

    @classmethod
    def mood_pie(cls, mood_data: Dict[str, float]) -> dict:
        """Pie chart: mood distribution percentages."""
        labels = [cls.MOOD_LABELS.get(k, k) for k in mood_data.keys()]
        values = list(mood_data.values())
        colors = [cls.COLORS.get(k, "#adb5bd") for k in mood_data.keys()]

        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            marker=dict(colors=colors),
            textinfo="label+percent",
            hole=0.4,
        )])
        fig.update_layout(
            title=dict(text="توزيع المزاج", x=0.5, font=dict(size=16, family="Cairo")),
            font=dict(family="Cairo"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def mood_line(cls, daily_moods: List[Dict]) -> dict:
        """Line chart: mood trends over time."""
        if not daily_moods:
            return {}
        df = pd.DataFrame(daily_moods).set_index("date")
        fig = go.Figure()
        for mood in ["happy", "normal", "sad", "tired", "sick"]:
            if mood in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[mood],
                    name=cls.MOOD_LABELS.get(mood, mood),
                    mode="lines+markers",
                    line=dict(color=cls.COLORS.get(mood)),
                ))
        fig.update_layout(
            title=dict(text="اتجاهات المزاج اليومية", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="التاريخ", yaxis_title="عدد الأطفال",
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
            legend=dict(orientation="h", y=-0.15),
        )
        return cls._to_json(fig)

    @classmethod
    def meal_bar(cls, meal_data: Dict[str, float]) -> dict:
        """Bar chart: meal compliance rates."""
        meals_ar = {"breakfast": "الإفطار", "snack": "وجبة خفيفة", "milk": "الحليب", "lunch": "الغداء"}
        names = [meals_ar.get(k, k) for k in ["breakfast", "snack", "milk", "lunch"]]
        values = [meal_data.get(k, 0) for k in ["breakfast", "snack", "milk", "lunch"]]
        colors = ["#0d6efd", "#6610f2", "#20c997", "#fd7e14"]

        fig = go.Figure(data=[go.Bar(
            x=names, y=values,
            marker_color=colors,
            text=[f"{v}%" for v in values],
            textposition="auto",
        )])
        fig.update_layout(
            title=dict(text="نسب تناول الوجبات", x=0.5, font=dict(size=16, family="Cairo")),
            yaxis_title="النسبة (%)", yaxis=dict(range=[0, 100]),
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def status_funnel_chart(cls, status_counts: Dict[str, int]) -> dict:
        """Funnel chart: report workflow status."""
        status_ar = {
            "DRAFT": "مسودة", "SUBMITTED": "مقدم", "APPROVED": "معتمد",
            "SENT_TO_PARENT": "مرسل لولي الأمر", "REJECTED": "مرفوض", "RETURNED": "معاد",
        }
        order = ["DRAFT", "SUBMITTED", "APPROVED", "SENT_TO_PARENT", "REJECTED", "RETURNED"]
        labels = [status_ar.get(s, s) for s in order if status_counts.get(s, 0) > 0]
        values = [status_counts.get(s, 0) for s in order if status_counts.get(s, 0) > 0]

        fig = go.Figure(go.Funnel(
            y=labels, x=values,
            textinfo="value+percent initial",
            marker=dict(color=["#6c757d", "#0d6efd", "#198754", "#0dcaf0", "#dc3545", "#fd7e14"][:len(labels)]),
        ))
        fig.update_layout(
            title=dict(text="مسار حالة التقرير", x=0.5, font=dict(size=16, family="Cairo")),
            font=dict(family="Cairo"),
            margin=dict(l=20, r=20, t=50, b=20),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def attendance_line(cls, daily_counts: List[Dict]) -> dict:
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
            title=dict(text="تقارير الحضور اليومية", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="التاريخ", yaxis_title="عدد التقارير",
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
        )
        return cls._to_json(fig)

    @classmethod
    def rejection_bar(cls, reasons: List[Dict]) -> dict:
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
            title=dict(text="أسباب الرفض الأكثر شيوعاً", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="العدد",
            font=dict(family="Cairo"),
            margin=dict(l=200, r=20, t=50, b=40),
            height=max(200, len(reasons) * 50 + 100),
        )
        return cls._to_json(fig)

    @classmethod
    def nap_histogram(cls, nap_durations: pd.Series) -> dict:
        """Histogram: nap duration distribution."""
        valid = nap_durations.dropna()
        if valid.empty:
            return {}
        fig = go.Figure(data=[go.Histogram(
            x=valid, nbinsx=10,
            marker_color="#6f42c1",
        )])
        fig.update_layout(
            title=dict(text="توزيع مدة القيلولة (دقيقة)", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="المدة (دقيقة)", yaxis_title="العدد",
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=300,
        )
        return cls._to_json(fig)

    @classmethod
    def diaper_trend(cls, daily_data: List[Dict]) -> dict:
        """Stacked bar chart: bathroom + diaper trends."""
        if not daily_data:
            return {}
        df = pd.DataFrame(daily_data)
        fig = go.Figure()
        fig.add_trace(go.Bar(name="دخول الحمام", x=df["date"], y=df["total_bathroom"],
                             marker_color="#0d6efd"))
        fig.add_trace(go.Bar(name="حفاض مبلل", x=df["date"], y=df["wet_count"],
                             marker_color="#ffc107"))
        fig.add_trace(go.Bar(name="حفاض متسخ", x=df["date"], y=df["soiled_count"],
                             marker_color="#fd7e14"))
        fig.update_layout(
            barmode="group",
            title=dict(text="اتجاه الحمام والحفاضات", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="التاريخ",
            font=dict(family="Cairo"),
            margin=dict(l=40, r=20, t=50, b=40),
            height=350,
            legend=dict(orientation="h", y=-0.15),
        )
        return cls._to_json(fig)

    @classmethod
    def meal_trend_line(cls, daily_meals: List[Dict]) -> dict:
        """Multi-line chart: meal compliance over days."""
        if not daily_meals:
            return {}
        df = pd.DataFrame(daily_meals)
        meals_ar = {"breakfast": "الإفطار", "snack": "وجبة خفيفة", "milk": "الحليب", "lunch": "الغداء"}
        colors = {"breakfast": "#0d6efd", "snack": "#6610f2", "milk": "#20c997", "lunch": "#fd7e14"}
        fig = go.Figure()
        for meal in ["breakfast", "snack", "milk", "lunch"]:
            if meal in df.columns:
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df[meal],
                    name=meals_ar[meal],
                    mode="lines+markers",
                    line=dict(color=colors[meal]),
                ))
        fig.update_layout(
            title=dict(text="اتجاه الوجبات اليومية", x=0.5, font=dict(size=16, family="Cairo")),
            xaxis_title="التاريخ", yaxis_title="النسبة (%)",
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

    df = _load_reports_df(db, d_from, d_to, kg_ids, child_ids, status)
    analytics = DailyReportAnalytics(df)
    return analytics.full_summary(d_from, d_to)


@router.get("/charts")
def get_analytics_charts(
    date_from: str = Query(..., description="Start date YYYY-MM-DD"),
    date_to: str = Query(..., description="End date YYYY-MM-DD"),
    kindergarten_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """All Plotly chart JSONs for frontend rendering."""
    d_from = _parse_date(date_from)
    d_to = _parse_date(date_to)
    kg_ids = _enforce_analytics_rbac(user, [kindergarten_id] if kindergarten_id else None)

    df = _load_reports_df(db, d_from, d_to, kg_ids)
    if df.empty:
        return {"charts": {}, "message": "No data for the selected period"}

    analytics = DailyReportAnalytics(df)
    summary = analytics.full_summary(d_from, d_to)

    charts = {
        "mood_pie": DailyReportViz.mood_pie(summary["mood_trends"]["overall"]),
        "mood_line": DailyReportViz.mood_line(summary["mood_trends"]["daily"]),
        "meal_bar": DailyReportViz.meal_bar(summary["meal_completion"]),
        "meal_trend": DailyReportViz.meal_trend_line(summary["meal_completion"]["daily"]),
        "status_funnel": DailyReportViz.status_funnel_chart(summary["status_funnel"]["status_counts"]),
        "attendance_line": DailyReportViz.attendance_line(summary["attendance"]["daily_counts"]),
        "rejection_bar": DailyReportViz.rejection_bar(summary["workflow_metrics"]["top_rejection_reasons"]),
        "nap_histogram": DailyReportViz.nap_histogram(df["nap_duration_minutes"]),
        "diaper_trend": DailyReportViz.diaper_trend(summary["diaper_bathroom"]["daily"]),
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
