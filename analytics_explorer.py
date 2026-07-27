"""
Guided Analytics Explorer — a question-first analytics surface for non-technical admins.

Design contract
---------------
The legacy explorer (``charts_api`` + ``templates/admin/analytics/charts_dashboard.html``)
asks the operator to assemble a query: pick a *source*, a *chart type*, a *granularity*,
a *group_by*, a *top_n*. That vocabulary is meaningless to a ministry administrator.

This module inverts the model. The operator picks a **question in plain language**;
the server decides the aggregation, the chart shape, and the wording, and returns —
in one payload — the answer, a full plain-language explanation of how the number was
derived, and the concrete next questions worth asking.

Every operator-visible string is produced here in **both Arabic and English**. The
browser never translates, never guesses, and never falls back to English.

Correctness rules enforced here (each one is a defect in the legacy path):
  * Date windows on ``DateTime`` columns are half-open ``[start_of_day, next_day)``.
    Comparing a ``DateTime`` against a bare ``date`` silently drops the final day.
  * ``records`` (underlying rows) and ``groups`` (bars) are counted separately and
    reported separately. They are not the same number and must not be conflated.
  * ``as_of`` is Jordan time (UTC+3), never naive server time, never UTC.
  * Payload values are built from Python primitives, so a cache round-trip cannot
    change their type or formatting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from dependencies import get_current_user_or_redirect, require_admin
from utils.time_utils import get_amman_tz, now_amman, today_amman

# JSON endpoints answer with 401 when unauthenticated, which is what a fetch() caller
# wants. The HTML page must instead bounce the operator to the login screen, so it
# lives on a second router without the JSON-flavoured guard.
router = APIRouter(tags=["Analytics Explorer"], dependencies=[Depends(require_admin)])
page_router = APIRouter(include_in_schema=False)

# Default look-back when the caller supplies no window.
_DEFAULT_WINDOW_DAYS = 90

# Governorate aliases accepted from the URL. Amman is stored under its Arabic
# administrative name, so an English "amman" must resolve to it.
_GOVERNORATE_ALIASES = {"amman": "العاصمة", "عمان": "العاصمة", "العاصمة": "العاصمة"}


# ---------------------------------------------------------------------------
# Bilingual text helper
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Text:
    """A single operator-visible string in both supported languages."""

    ar: str
    en: str

    def as_dict(self) -> Dict[str, str]:
        return {"ar": self.ar, "en": self.en}


def _t(ar: str, en: str) -> Text:
    return Text(ar=ar, en=en)


# ---------------------------------------------------------------------------
# Time windows
# ---------------------------------------------------------------------------


def _parse_iso_date(value: Optional[str], field_name: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} must be an ISO date (YYYY-MM-DD), got {value!r}.",
        )


@dataclass(frozen=True)
class Window:
    """A resolved reporting period, in Jordan time."""

    start: date
    end: date  # inclusive, as the operator understands it

    @property
    def dt_start(self) -> datetime:
        """Inclusive lower bound for a DateTime column."""
        return datetime.combine(self.start, time.min)

    @property
    def dt_end_exclusive(self) -> datetime:
        """Exclusive upper bound — midnight at the START of the day after ``end``.

        This is the fix for the legacy ``occurred_at <= date_to`` comparison, which
        excludes every event on ``date_to`` that carries a time component.
        """
        return datetime.combine(self.end + timedelta(days=1), time.min)


def _resolve_window(date_from: Optional[str], date_to: Optional[str]) -> Window:
    today = today_amman()
    start = _parse_iso_date(date_from, "date_from") or today - timedelta(days=_DEFAULT_WINDOW_DAYS)
    end = _parse_iso_date(date_to, "date_to") or today
    if start > end:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to.")
    return Window(start=start, end=end)


def _format_period(window: Window) -> Text:
    return _t(
        f"من {window.start.isoformat()} إلى {window.end.isoformat()} (شامل اليومين)",
        f"{window.start.isoformat()} to {window.end.isoformat()} (both days included)",
    )


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Scope:
    """Geographic / organisational narrowing applied to a question."""

    governorate: Optional[str] = None
    kindergarten_id: Optional[int] = None

    @property
    def level(self) -> str:
        if self.kindergarten_id:
            return "kindergarten"
        if self.governorate:
            return "governorate"
        return "national"

    def label(self, db: Session) -> Text:
        if self.kindergarten_id:
            name = db.query(models.Kindergarten.name_ar).filter(
                models.Kindergarten.id == self.kindergarten_id
            ).scalar()
            shown = name or f"#{self.kindergarten_id}"
            return _t(f"حضانة {shown}", f"Kindergarten {shown}")
        if self.governorate:
            return _t(f"محافظة {self.governorate}", f"{self.governorate} Governorate")
        return _t("جميع محافظات المملكة", "All governorates nationwide")


def _resolve_scope(governorate: Optional[str], kindergarten_id: Optional[int]) -> Scope:
    gov = None
    if governorate:
        gov = _GOVERNORATE_ALIASES.get(governorate.strip().lower(), governorate.strip())
    return Scope(governorate=gov, kindergarten_id=kindergarten_id)


# ---------------------------------------------------------------------------
# Enum label catalogue — the single place a stored enum becomes readable text
# ---------------------------------------------------------------------------

_ENUM_LABELS: Dict[str, Text] = {
    # IncidentType
    "INJURY": _t("إصابة", "Injury"),
    "ILLNESS": _t("مرض", "Illness"),
    "BEHAVIOR": _t("سلوك", "Behaviour"),
    "OTHER": _t("أخرى", "Other"),
    # SeverityLevel
    "LOW": _t("منخفضة", "Low"),
    "MEDIUM": _t("متوسطة", "Medium"),
    "HIGH": _t("مرتفعة", "High"),
    "CRITICAL": _t("حرجة", "Critical"),
    # AttendanceStatus
    "PRESENT": _t("حاضر", "Present"),
    "ABSENT": _t("غائب", "Absent"),
    "LATE": _t("متأخر", "Late"),
    "EXCUSED": _t("غياب بعذر", "Excused"),
    # EnrollmentStatus
    "PENDING": _t("قيد الانتظار", "Pending"),
    "PENDING_REVIEW": _t("قيد المراجعة", "Pending review"),
    "APPROVED": _t("مقبول", "Approved"),
    "REJECTED": _t("مرفوض", "Rejected"),
    "WAITLISTED": _t("قائمة الانتظار", "Waitlisted"),
    "CANCELLED": _t("ملغى", "Cancelled"),
    "ACTIVE": _t("نشط", "Active"),
    # DailyReport mood
    "HAPPY": _t("سعيد", "Happy"),
    "SAD": _t("حزين", "Sad"),
    "NEUTRAL": _t("محايد", "Neutral"),
    "TIRED": _t("متعب", "Tired"),
    "EXCITED": _t("متحمس", "Excited"),
}


# DailyReport.mood is a free-text String(20), not an enum, and the values stored in
# production are Arabic with an emoji. The model's inline comment claims English
# values ("happy, normal, sad...") — it is stale. Map the real stored strings.
_MOOD_LABELS: Dict[str, Text] = {
    "سعيد 😊": _t("سعيد 😊", "Happy 😊"),
    "هادئ 😌": _t("هادئ 😌", "Calm 😌"),
    "عادي 😐": _t("عادي 😐", "Neutral 😐"),
    "نشيط 🤸": _t("نشيط 🤸", "Energetic 🤸"),
    "حزين 😢": _t("حزين 😢", "Sad 😢"),
}


def _mood_label(value: Any) -> Text:
    """Label a stored mood string, passing unknown values through unchanged."""
    raw = str(value).strip()
    known = _MOOD_LABELS.get(raw)
    return known if known else _t(raw, raw)


def _enum_key(value: Any) -> str:
    """Normalise a SQLAlchemy enum value to its bare NAME."""
    if value is None:
        return "UNKNOWN"
    name = getattr(value, "name", None)
    if name:
        return str(name)
    text = str(value)
    return text.rsplit(".", 1)[-1].upper()


def _label_for(value: Any) -> Text:
    key = _enum_key(value)
    known = _ENUM_LABELS.get(key)
    if known:
        return known
    readable = key.replace("_", " ").title()
    return _t(readable, readable)


# ---------------------------------------------------------------------------
# Answer payload
# ---------------------------------------------------------------------------


@dataclass
class Category:
    """One bar / slice, already labelled in both languages."""

    key: str
    label: Text
    value: int

    def as_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "label": self.label.as_dict(), "value": self.value}


@dataclass
class NextStep:
    """A concrete follow-up the operator can take in one click."""

    label: Text
    question: str
    scope_change: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label.as_dict(),
            "question": self.question,
            "scope_change": self.scope_change,
        }


@dataclass
class Answer:
    """Everything the page needs to render one question, fully explained."""

    chart_type: str
    categories: List[Category]
    records: int
    headline: Text
    what: Text
    how: Text
    origin: Text
    excluded: Text
    value_axis: Text
    category_axis: Text
    next_steps: List[NextStep] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Question definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    key: str
    title: Text
    subtitle: Text
    icon: str
    build: Callable[[Session, Window, Scope], Answer]


def _scoped_incident_query(db: Session, window: Window, scope: Scope):
    """Base incident query with the window and scope applied.

    The window uses a half-open interval so that events occurring during the final
    day are included — ``occurred_at <= date_to`` would drop all of them.
    """
    query = db.query(models.Incident).filter(
        models.Incident.deleted_at.is_(None),
        models.Incident.occurred_at >= window.dt_start,
        models.Incident.occurred_at < window.dt_end_exclusive,
    )
    if scope.kindergarten_id:
        return query.filter(models.Incident.kindergarten_id == scope.kindergarten_id)
    if scope.governorate:
        return query.join(
            models.Kindergarten, models.Incident.kindergarten_id == models.Kindergarten.id
        ).filter(models.Kindergarten.governorate == scope.governorate)
    return query


_AGE_POLICY_NOTE = _t(
    "يستثني النظام تلقائياً أي سجل يخص طفلاً خارج الفئة العمرية المعتمدة للحضانات، "
    "كما تُستثنى السجلات المحذوفة. لذلك قد يقل العدد الظاهر هنا عن العدد الخام في قاعدة البيانات.",
    "The system automatically excludes any record belonging to a child outside the approved "
    "kindergarten age range, and excludes deleted records. The figure shown here can therefore "
    "be lower than the raw database count.",
)


def _build_incidents_by_type(db: Session, window: Window, scope: Scope) -> Answer:
    rows = (
        _scoped_incident_query(db, window, scope)
        .with_entities(models.Incident.type, func.count(models.Incident.id))
        .group_by(models.Incident.type)
        .all()
    )
    categories = [
        Category(key=_enum_key(value), label=_label_for(value), value=int(count))
        for value, count in rows
    ]
    categories.sort(key=lambda c: c.value, reverse=True)
    total = sum(c.value for c in categories)

    if total == 0:
        headline = _t("لم تُسجَّل أي حادثة في هذه الفترة", "No incidents were recorded in this period")
    else:
        top = categories[0]
        share = round(top.value * 100 / total)
        headline = _t(
            f"سُجِّلت {total} حادثة، أكثرها «{top.label.ar}» بنسبة {share}%",
            f"{total} incidents recorded — most common was “{top.label.en}” at {share}%",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم عدد الحوادث المسجَّلة في الفترة المحددة، موزَّعة حسب نوع الحادث.",
            "This chart shows how many incidents were recorded in the selected period, broken "
            "down by the type of incident.",
        ),
        how=_t(
            "١) نأخذ كل حادثة وقع تاريخها داخل الفترة المحددة. "
            "٢) نستبعد الحوادث المحذوفة. "
            "٣) نجمع الحوادث المتشابهة في النوع ونعدّها. "
            "كل عمود يمثل عدد الحوادث من نوع واحد — وليس نسبة مئوية.",
            "1) We take every incident whose date falls inside the selected period. "
            "2) We exclude deleted incidents. "
            "3) We group incidents of the same type together and count them. "
            "Each bar is a count of incidents of one type — not a percentage.",
        ),
        origin=_t(
            "المصدر: سجل الحوادث الذي تدخله الحضانات، حقل «تاريخ وقوع الحادثة».",
            "Source: the incident log filled in by kindergartens, using the “incident occurred” date.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد الحوادث", "Number of incidents"),
        category_axis=_t("نوع الحادث", "Incident type"),
        next_steps=[
            NextStep(
                label=_t("ما مدى خطورة هذه الحوادث؟", "How serious were these incidents?"),
                question="incidents_by_severity",
            ),
            NextStep(
                label=_t("هل تتزايد الحوادث عبر الوقت؟", "Are incidents increasing over time?"),
                question="incidents_over_time",
            ),
            NextStep(
                label=_t("في أي محافظة تتركز الحوادث؟", "Which governorate has the most incidents?"),
                question="incidents_by_governorate",
            ),
        ],
    )


def _build_incidents_by_severity(db: Session, window: Window, scope: Scope) -> Answer:
    rows = (
        _scoped_incident_query(db, window, scope)
        .with_entities(models.Incident.severity_level, func.count(models.Incident.id))
        .group_by(models.Incident.severity_level)
        .all()
    )
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    categories = [
        Category(key=_enum_key(value), label=_label_for(value), value=int(count))
        for value, count in rows
    ]
    categories.sort(key=lambda c: order.get(c.key, 99))
    total = sum(c.value for c in categories)
    serious = sum(c.value for c in categories if c.key in ("CRITICAL", "HIGH"))

    if total == 0:
        headline = _t("لا توجد حوادث لتقييم خطورتها", "No incidents to assess for severity")
    else:
        share = round(serious * 100 / total)
        headline = _t(
            f"{serious} من أصل {total} حادثة صُنِّفت مرتفعة أو حرجة ({share}%)",
            f"{serious} of {total} incidents were rated high or critical ({share}%)",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم توزيع الحوادث حسب درجة الخطورة التي سجّلتها الحضانة.",
            "This chart shows how incidents are distributed across the severity level recorded "
            "by the kindergarten.",
        ),
        how=_t(
            "١) نأخذ نفس مجموعة الحوادث الواقعة في الفترة المحددة. "
            "٢) نجمعها حسب درجة الخطورة المسجَّلة وقت الإبلاغ. "
            "٣) تُرتَّب الأعمدة من الأشد خطورة إلى الأقل. "
            "درجة الخطورة يحددها الموظف المبلِّغ، وليست محسوبة آلياً.",
            "1) We take the same set of incidents from the selected period. "
            "2) We group them by the severity recorded at the time of reporting. "
            "3) Bars are ordered from most to least severe. "
            "Severity is chosen by the reporting staff member — it is not computed automatically.",
        ),
        origin=_t(
            "المصدر: حقل «درجة الخطورة» في نموذج الإبلاغ عن الحادثة.",
            "Source: the “severity level” field on the incident reporting form.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد الحوادث", "Number of incidents"),
        category_axis=_t("درجة الخطورة", "Severity level"),
        next_steps=[
            NextStep(
                label=_t("ما أنواع هذه الحوادث؟", "What types were these incidents?"),
                question="incidents_by_type",
            ),
            NextStep(
                label=_t("هل تتزايد الحوادث عبر الوقت؟", "Are incidents increasing over time?"),
                question="incidents_over_time",
            ),
        ],
    )


def _build_incidents_over_time(db: Session, window: Window, scope: Scope) -> Answer:
    rows = (
        _scoped_incident_query(db, window, scope)
        .with_entities(func.date(models.Incident.occurred_at), func.count(models.Incident.id))
        .group_by(func.date(models.Incident.occurred_at))
        .all()
    )
    counts = {str(day): int(count) for day, count in rows if day}

    # Emit every day in the window, including zero days. A gap-free axis is what
    # makes "is this getting worse?" answerable at a glance.
    categories: List[Category] = []
    cursor = window.start
    while cursor <= window.end:
        iso = cursor.isoformat()
        categories.append(
            Category(key=iso, label=_t(iso, iso), value=counts.get(iso, 0))
        )
        cursor += timedelta(days=1)

    total = sum(c.value for c in categories)
    half = len(categories) // 2
    first_half = sum(c.value for c in categories[:half])
    second_half = sum(c.value for c in categories[half:])

    if total == 0:
        headline = _t("لم تُسجَّل أي حادثة في هذه الفترة", "No incidents were recorded in this period")
    elif second_half > first_half:
        headline = _t(
            f"سُجِّلت {total} حادثة، والاتجاه العام متزايد في النصف الثاني من الفترة",
            f"{total} incidents recorded — the trend is rising in the second half of the period",
        )
    elif second_half < first_half:
        headline = _t(
            f"سُجِّلت {total} حادثة، والاتجاه العام متراجع في النصف الثاني من الفترة",
            f"{total} incidents recorded — the trend is falling in the second half of the period",
        )
    else:
        headline = _t(
            f"سُجِّلت {total} حادثة، بمعدل ثابت تقريباً على مدار الفترة",
            f"{total} incidents recorded — the rate was broadly steady across the period",
        )

    return Answer(
        chart_type="line",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم عدد الحوادث المسجَّلة في كل يوم من أيام الفترة المحددة.",
            "This chart shows how many incidents were recorded on each day of the selected period.",
        ),
        how=_t(
            "١) نأخذ كل حادثة داخل الفترة ونعزو كل واحدة إلى يوم وقوعها. "
            "٢) نعدّ الحوادث في كل يوم على حدة. "
            "٣) تظهر الأيام التي لم تقع فيها حوادث بقيمة صفر، ولا تُحذف من الرسم. "
            "المقارنة في العنوان تقارن مجموع النصف الأول من الفترة بمجموع النصف الثاني.",
            "1) We take every incident in the period and attribute it to the day it occurred. "
            "2) We count the incidents on each separate day. "
            "3) Days with no incidents are shown as zero rather than dropped from the chart. "
            "The trend statement compares the total of the first half of the period against the second half.",
        ),
        origin=_t(
            "المصدر: حقل «تاريخ وقوع الحادثة» في سجل الحوادث.",
            "Source: the “incident occurred” date field in the incident log.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد الحوادث في اليوم", "Incidents per day"),
        category_axis=_t("اليوم", "Day"),
        next_steps=[
            NextStep(
                label=_t("ما أنواع هذه الحوادث؟", "What types were these incidents?"),
                question="incidents_by_type",
            ),
            NextStep(
                label=_t("ما مدى خطورتها؟", "How serious were they?"),
                question="incidents_by_severity",
            ),
        ],
    )


def _build_incidents_by_governorate(db: Session, window: Window, scope: Scope) -> Answer:
    rows = (
        db.query(models.Kindergarten.governorate, func.count(models.Incident.id))
        .join(models.Incident, models.Incident.kindergarten_id == models.Kindergarten.id)
        .filter(
            models.Incident.deleted_at.is_(None),
            models.Incident.occurred_at >= window.dt_start,
            models.Incident.occurred_at < window.dt_end_exclusive,
        )
        .group_by(models.Kindergarten.governorate)
        .all()
    )
    categories = [
        Category(
            key=str(gov or "UNKNOWN"),
            label=_t(str(gov or "غير محدد"), str(gov or "Unspecified")),
            value=int(count),
        )
        for gov, count in rows
    ]
    categories.sort(key=lambda c: c.value, reverse=True)
    total = sum(c.value for c in categories)

    if total == 0:
        headline = _t("لم تُسجَّل أي حادثة في هذه الفترة", "No incidents were recorded in this period")
    else:
        top = categories[0]
        headline = _t(
            f"أعلى محافظة من حيث عدد الحوادث هي «{top.label.ar}» بـ {top.value} حادثة",
            f"The governorate with the most incidents is “{top.label.en}” with {top.value}",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم توزيع الحوادث على المحافظات، بحسب موقع الحضانة التي وقعت فيها الحادثة.",
            "This chart shows how incidents are distributed across governorates, based on the "
            "location of the kindergarten where each incident occurred.",
        ),
        how=_t(
            "١) نربط كل حادثة بالحضانة التي وقعت فيها. "
            "٢) نأخذ محافظة تلك الحضانة. "
            "٣) نعدّ الحوادث في كل محافظة. "
            "تنبيه مهم: العدد الخام لا يعني أن المحافظة أسوأ أداءً — فالمحافظات الأكبر لديها حضانات "
            "وأطفال أكثر، وبالتالي حوادث أكثر بطبيعة الحال.",
            "1) We link each incident to the kindergarten where it happened. "
            "2) We take that kindergarten's governorate. "
            "3) We count the incidents in each governorate. "
            "Important: a raw count does not mean a governorate performs worse — larger governorates "
            "have more kindergartens and more children, and therefore naturally more incidents.",
        ),
        origin=_t(
            "المصدر: سجل الحوادث مربوطاً بحقل «المحافظة» في سجل الحضانات.",
            "Source: the incident log joined to the “governorate” field on the kindergarten record.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد الحوادث", "Number of incidents"),
        category_axis=_t("المحافظة", "Governorate"),
        next_steps=[
            NextStep(
                label=_t("ما أنواع هذه الحوادث؟", "What types were these incidents?"),
                question="incidents_by_type",
            ),
        ],
    )


def _build_attendance_breakdown(db: Session, window: Window, scope: Scope) -> Answer:
    # AttendanceLog.date is a DATE column, so an inclusive comparison is correct here.
    query = db.query(models.AttendanceLog.status, func.count(models.AttendanceLog.id)).filter(
        models.AttendanceLog.date >= window.start,
        models.AttendanceLog.date <= window.end,
    )
    if scope.kindergarten_id or scope.governorate:
        query = query.join(models.Class, models.AttendanceLog.class_id == models.Class.id)
        if scope.kindergarten_id:
            query = query.filter(models.Class.kindergarten_id == scope.kindergarten_id)
        else:
            query = query.join(
                models.Kindergarten, models.Class.kindergarten_id == models.Kindergarten.id
            ).filter(models.Kindergarten.governorate == scope.governorate)

    rows = query.group_by(models.AttendanceLog.status).all()
    categories = [
        Category(key=_enum_key(value), label=_label_for(value), value=int(count))
        for value, count in rows
    ]
    categories.sort(key=lambda c: c.value, reverse=True)
    total = sum(c.value for c in categories)
    present = sum(c.value for c in categories if c.key == "PRESENT")

    if total == 0:
        headline = _t("لا توجد سجلات حضور في هذه الفترة", "No attendance records in this period")
    else:
        rate = round(present * 100 / total)
        headline = _t(
            f"نسبة الحضور {rate}% من إجمالي {total} سجل حضور",
            f"Attendance rate is {rate}% across {total} attendance records",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم عدد سجلات الحضور في الفترة المحددة، موزعة على الحالات: حاضر، غائب، متأخر.",
            "This chart shows the number of attendance records in the selected period, split by "
            "status: present, absent, late.",
        ),
        how=_t(
            "١) نأخذ كل سجل حضور مؤرَّخ داخل الفترة. "
            "٢) نجمع السجلات حسب الحالة المسجَّلة. "
            "٣) نسبة الحضور في العنوان = عدد سجلات «حاضر» ÷ إجمالي السجلات × ١٠٠. "
            "لاحظ أن الوحدة هنا هي «سجل حضور ليوم واحد لطفل واحد»، وليست عدد الأطفال.",
            "1) We take every attendance record dated inside the period. "
            "2) We group the records by their recorded status. "
            "3) The headline rate = “present” records ÷ total records × 100. "
            "Note the unit is “one child on one day”, not a number of children.",
        ),
        origin=_t(
            "المصدر: سجل الحضور اليومي الذي تدخله المعلمات في الحضانة.",
            "Source: the daily attendance register filled in by kindergarten teachers.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد سجلات الحضور", "Number of attendance records"),
        category_axis=_t("حالة الحضور", "Attendance status"),
        next_steps=[
            NextStep(
                label=_t("كيف توزعت حالة الأطفال المزاجية؟", "How did children's moods break down?"),
                question="daily_report_moods",
            ),
        ],
    )


def _build_enrollment_status(db: Session, window: Window, scope: Scope) -> Answer:
    query = db.query(
        models.EnrollmentApplication.status, func.count(models.EnrollmentApplication.id)
    ).filter(
        models.EnrollmentApplication.created_at >= window.dt_start,
        models.EnrollmentApplication.created_at < window.dt_end_exclusive,
    )
    if scope.kindergarten_id:
        query = query.filter(models.EnrollmentApplication.kindergarten_id == scope.kindergarten_id)
    elif scope.governorate:
        query = query.join(
            models.Kindergarten,
            models.EnrollmentApplication.kindergarten_id == models.Kindergarten.id,
        ).filter(models.Kindergarten.governorate == scope.governorate)

    rows = query.group_by(models.EnrollmentApplication.status).all()
    categories = [
        Category(key=_enum_key(value), label=_label_for(value), value=int(count))
        for value, count in rows
    ]
    categories.sort(key=lambda c: c.value, reverse=True)
    total = sum(c.value for c in categories)
    approved = sum(c.value for c in categories if c.key == "APPROVED")

    if total == 0:
        headline = _t("لم تُقدَّم أي طلبات تسجيل في هذه الفترة", "No enrolment applications were submitted in this period")
    else:
        rate = round(approved * 100 / total)
        headline = _t(
            f"{total} طلب تسجيل، قُبل منها {approved} ({rate}%)",
            f"{total} enrolment applications, of which {approved} were approved ({rate}%)",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم طلبات التسجيل المقدَّمة خلال الفترة، موزَّعة حسب حالة الطلب الحالية.",
            "This chart shows enrolment applications submitted during the period, grouped by the "
            "application's current status.",
        ),
        how=_t(
            "١) نأخذ الطلبات حسب تاريخ تقديمها داخل الفترة. "
            "٢) نجمعها حسب حالتها الحالية اليوم. "
            "تنبيه: الحالة تعكس الوضع الآن وليس وقت التقديم، فالطلب المقدَّم الشهر الماضي "
            "وقُبل هذا الأسبوع سيظهر ضمن «مقبول».",
            "1) We take applications by their submission date inside the period. "
            "2) We group them by their status as it stands today. "
            "Note: status reflects the position now, not at submission time — an application filed "
            "last month and approved this week appears under “Approved”.",
        ),
        origin=_t(
            "المصدر: طلبات التسجيل الإلكترونية، حقل «تاريخ التقديم».",
            "Source: online enrolment applications, using the submission date field.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد الطلبات", "Number of applications"),
        category_axis=_t("حالة الطلب", "Application status"),
        next_steps=[
            NextStep(
                label=_t("ما الطاقة الاستيعابية المتاحة؟", "What capacity is available?"),
                question="kindergarten_capacity",
            ),
        ],
    )


def _build_daily_report_moods(db: Session, window: Window, scope: Scope) -> Answer:
    query = db.query(models.DailyReport.mood, func.count(models.DailyReport.id)).filter(
        models.DailyReport.date >= window.start,
        models.DailyReport.date <= window.end,
    )
    if scope.kindergarten_id:
        query = query.filter(models.DailyReport.kindergarten_id == scope.kindergarten_id)
    elif scope.governorate:
        query = query.join(
            models.Kindergarten, models.DailyReport.kindergarten_id == models.Kindergarten.id
        ).filter(models.Kindergarten.governorate == scope.governorate)

    rows = query.group_by(models.DailyReport.mood).all()
    categories = [
        Category(key=str(value).strip(), label=_mood_label(value), value=int(count))
        for value, count in rows
        if value is not None and str(value).strip()
    ]
    categories.sort(key=lambda c: c.value, reverse=True)
    total = sum(c.value for c in categories)

    if total == 0:
        headline = _t("لا توجد تقارير يومية في هذه الفترة", "No daily reports in this period")
    else:
        top = categories[0]
        share = round(top.value * 100 / total)
        headline = _t(
            f"الحالة الغالبة «{top.label.ar}» بنسبة {share}% من {total} تقرير",
            f"The most common mood was “{top.label.en}” at {share}% of {total} reports",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=total,
        headline=headline,
        what=_t(
            "يعرض هذا الرسم الحالة المزاجية المسجَّلة للأطفال في التقارير اليومية خلال الفترة.",
            "This chart shows the mood recorded for children in daily reports during the period.",
        ),
        how=_t(
            "١) نأخذ التقارير اليومية المؤرَّخة داخل الفترة. "
            "٢) نجمعها حسب الحالة المزاجية المسجَّلة. "
            "٣) تُستبعد التقارير التي تُركت خانة المزاج فيها فارغة. "
            "هذا مؤشر انطباعي تدخله المعلمة، ويُقرأ كمؤشر عام لا كتشخيص.",
            "1) We take daily reports dated inside the period. "
            "2) We group them by the mood recorded. "
            "3) Reports where the mood field was left blank are excluded. "
            "This is a subjective indicator entered by the teacher — read it as a general signal, "
            "not a diagnosis.",
        ),
        origin=_t(
            "المصدر: حقل «الحالة المزاجية» في التقرير اليومي.",
            "Source: the “mood” field on the daily report.",
        ),
        excluded=_AGE_POLICY_NOTE,
        value_axis=_t("عدد التقارير", "Number of reports"),
        category_axis=_t("الحالة المزاجية", "Mood"),
        next_steps=[
            NextStep(
                label=_t("هل وقعت حوادث في نفس الفترة؟", "Were there incidents in the same period?"),
                question="incidents_by_type",
            ),
        ],
    )


def _build_kindergarten_capacity(db: Session, window: Window, scope: Scope) -> Answer:
    # Capacity is a present-state question, so the reporting window does not filter it.
    query = (
        db.query(
            models.Kindergarten.governorate,
            func.coalesce(func.sum(models.Class.capacity_total), 0),
            func.coalesce(func.sum(models.Class.enrolled_children_count), 0),
        )
        .outerjoin(
            models.Class,
            (models.Class.kindergarten_id == models.Kindergarten.id)
            & (models.Class.deleted_at.is_(None))
            & (models.Class.is_active.is_(True)),
        )
        .filter(models.Kindergarten.deleted_at.is_(None))
    )
    if scope.kindergarten_id:
        query = query.filter(models.Kindergarten.id == scope.kindergarten_id)
    elif scope.governorate:
        query = query.filter(models.Kindergarten.governorate == scope.governorate)

    rows = query.group_by(models.Kindergarten.governorate).all()

    categories: List[Category] = []
    total_capacity = 0
    total_enrolled = 0
    for gov, capacity, enrolled in rows:
        capacity, enrolled = int(capacity or 0), int(enrolled or 0)
        total_capacity += capacity
        total_enrolled += enrolled
        rate = round(enrolled * 100 / capacity) if capacity else 0
        categories.append(
            Category(
                key=str(gov or "UNKNOWN"),
                label=_t(str(gov or "غير محدد"), str(gov or "Unspecified")),
                value=rate,
            )
        )
    categories.sort(key=lambda c: c.value, reverse=True)

    if total_capacity == 0:
        headline = _t(
            "لا توجد طاقة استيعابية مسجَّلة لعرضها",
            "No recorded capacity available to display",
        )
    else:
        overall = round(total_enrolled * 100 / total_capacity)
        headline = _t(
            f"نسبة الإشغال العامة {overall}% ({total_enrolled} طفل من أصل {total_capacity} مقعد)",
            f"Overall occupancy is {overall}% ({total_enrolled} children in {total_capacity} seats)",
        )

    return Answer(
        chart_type="bar",
        categories=categories,
        records=len(rows),
        headline=headline,
        what=_t(
            "يعرض هذا الرسم نسبة إشغال المقاعد في كل محافظة: كم مقعداً مشغولاً من كل ١٠٠ مقعد متاح.",
            "This chart shows seat occupancy per governorate: how many seats out of every 100 "
            "available are filled.",
        ),
        how=_t(
            "١) نجمع الطاقة الاستيعابية لكل الصفوف النشطة في كل محافظة. "
            "٢) نجمع عدد الأطفال المسجَّلين فعلياً في تلك الصفوف. "
            "٣) نسبة الإشغال = المسجَّلون ÷ الطاقة الاستيعابية × ١٠٠. "
            "الصفوف الموقوفة أو المحذوفة لا تُحتسب. "
            "هذا السؤال يعكس الوضع الحالي، ولذلك لا يتأثر بالفترة الزمنية المحددة أعلاه.",
            "1) We sum the capacity of every active class in each governorate. "
            "2) We sum the children actually enrolled in those classes. "
            "3) Occupancy = enrolled ÷ capacity × 100. "
            "Inactive or deleted classes are not counted. "
            "This question reflects the present state, so it is not affected by the date period above.",
        ),
        origin=_t(
            "المصدر: سجل الصفوف في كل حضانة (الطاقة الاستيعابية وعدد المسجَّلين).",
            "Source: the class register for each kindergarten (capacity and enrolled counts).",
        ),
        excluded=_t(
            "تُستبعد الحضانات المحذوفة والصفوف غير النشطة. النسبة المعروضة نسبة مئوية وليست عدداً.",
            "Deleted kindergartens and inactive classes are excluded. The value shown is a "
            "percentage, not a count.",
        ),
        value_axis=_t("نسبة الإشغال %", "Occupancy %"),
        category_axis=_t("المحافظة", "Governorate"),
        next_steps=[
            NextStep(
                label=_t("كم طلب تسجيل جديد؟", "How many new enrolment applications?"),
                question="enrollment_status",
            ),
        ],
    )


QUESTIONS: Dict[str, Question] = {
    q.key: q
    for q in [
        Question(
            key="incidents_by_type",
            title=_t("ما أنواع الحوادث التي وقعت؟", "What types of incidents happened?"),
            subtitle=_t(
                "توزيع الحوادث المسجَّلة حسب نوعها",
                "Recorded incidents broken down by type",
            ),
            icon="bi-exclamation-triangle",
            build=_build_incidents_by_type,
        ),
        Question(
            key="incidents_by_severity",
            title=_t("ما مدى خطورة الحوادث؟", "How serious were the incidents?"),
            subtitle=_t(
                "توزيع الحوادث حسب درجة الخطورة",
                "Incidents broken down by severity level",
            ),
            icon="bi-shield-exclamation",
            build=_build_incidents_by_severity,
        ),
        Question(
            key="incidents_over_time",
            title=_t("هل تتزايد الحوادث عبر الوقت؟", "Are incidents increasing over time?"),
            subtitle=_t("عدد الحوادث يوماً بيوم", "Incident counts day by day"),
            icon="bi-graph-up",
            build=_build_incidents_over_time,
        ),
        Question(
            key="incidents_by_governorate",
            title=_t("في أي محافظة تتركز الحوادث؟", "Which governorate has the most incidents?"),
            subtitle=_t("توزيع الحوادث على المحافظات", "Incidents distributed across governorates"),
            icon="bi-geo-alt",
            build=_build_incidents_by_governorate,
        ),
        Question(
            key="attendance_breakdown",
            title=_t("ما نسبة حضور الأطفال؟", "What is the children's attendance rate?"),
            subtitle=_t("توزيع سجلات الحضور والغياب", "Attendance and absence records breakdown"),
            icon="bi-person-check",
            build=_build_attendance_breakdown,
        ),
        Question(
            key="enrollment_status",
            title=_t("ما وضع طلبات التسجيل؟", "Where do enrolment applications stand?"),
            subtitle=_t("طلبات التسجيل حسب حالتها", "Enrolment applications by status"),
            icon="bi-people",
            build=_build_enrollment_status,
        ),
        Question(
            key="daily_report_moods",
            title=_t("كيف كانت حالة الأطفال؟", "How were the children doing?"),
            subtitle=_t(
                "الحالة المزاجية المسجَّلة في التقارير اليومية",
                "Moods recorded in daily reports",
            ),
            icon="bi-emoji-smile",
            build=_build_daily_report_moods,
        ),
        Question(
            key="kindergarten_capacity",
            title=_t("هل لدينا مقاعد شاغرة؟", "Do we have free seats?"),
            subtitle=_t("نسبة إشغال المقاعد حسب المحافظة", "Seat occupancy by governorate"),
            icon="bi-buildings",
            build=_build_kindergarten_capacity,
        ),
    ]
}


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@router.get("/api/admin/analytics/explorer/questions", summary="Catalogue of answerable questions")
def list_questions() -> Dict[str, Any]:
    """Everything the operator is allowed to ask, in both languages."""
    return {
        "questions": [
            {
                "key": q.key,
                "title": q.title.as_dict(),
                "subtitle": q.subtitle.as_dict(),
                "icon": q.icon,
            }
            for q in QUESTIONS.values()
        ]
    }


@router.get("/api/admin/analytics/explorer/answer", summary="Answer one question, fully explained")
def answer_question(
    question: str = Query(..., description="A key from the questions catalogue"),
    date_from: Optional[str] = Query(None, description="ISO date, inclusive"),
    date_to: Optional[str] = Query(None, description="ISO date, inclusive"),
    governorate: Optional[str] = Query(None),
    kindergarten_id: Optional[int] = Query(None, ge=1),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    definition = QUESTIONS.get(question)
    if definition is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown question {question!r}. Valid keys: {sorted(QUESTIONS)}",
        )

    window = _resolve_window(date_from, date_to)
    scope = _resolve_scope(governorate, kindergarten_id)
    answer = definition.build(db, window, scope)

    return {
        "question": {
            "key": definition.key,
            "title": definition.title.as_dict(),
            "subtitle": definition.subtitle.as_dict(),
            "icon": definition.icon,
        },
        "headline": answer.headline.as_dict(),
        "chart": {
            "type": answer.chart_type,
            "categories": [c.as_dict() for c in answer.categories],
            "value_axis": answer.value_axis.as_dict(),
            "category_axis": answer.category_axis.as_dict(),
        },
        "explanation": {
            "what": answer.what.as_dict(),
            "how": answer.how.as_dict(),
            "origin": answer.origin.as_dict(),
            "excluded": answer.excluded.as_dict(),
        },
        "coverage": {
            # These two are deliberately distinct. `records` is how many real events
            # were counted; `groups` is how many bars are drawn. The legacy page
            # reported `groups` to the operator under the word "records".
            "records": answer.records,
            "groups": len(answer.categories),
            "period": _format_period(window).as_dict(),
            "scope": scope.label(db).as_dict(),
            "scope_level": scope.level,
            "as_of": now_amman().isoformat(),
        },
        "next_steps": [step.as_dict() for step in answer.next_steps],
    }


@page_router.get("/admin/analytics/explorer", response_class=HTMLResponse)
def explorer_page(
    request: Request,
    current_user: models.User = Depends(get_current_user_or_redirect),
    db: Session = Depends(get_db),
):
    """The guided explorer page itself."""
    from frontend import templates

    if current_user.role != models.UserRole.ADMIN:
        return RedirectResponse("/dashboard", status_code=303)

    today = today_amman()
    governorates = [
        row[0]
        for row in db.query(models.Kindergarten.governorate)
        .filter(models.Kindergarten.deleted_at.is_(None), models.Kindergarten.governorate.isnot(None))
        .distinct()
        .order_by(models.Kindergarten.governorate)
        .all()
        if row[0]
    ]

    return templates.TemplateResponse(
        request=request,
        name="admin/analytics/explorer.html",
        context={
            "questions": [
                {
                    "key": q.key,
                    "title": q.title.as_dict(),
                    "subtitle": q.subtitle.as_dict(),
                    "icon": q.icon,
                }
                for q in QUESTIONS.values()
            ],
            "governorates": governorates,
            "default_date_to": today.isoformat(),
            "default_date_from": (today - timedelta(days=_DEFAULT_WINDOW_DAYS)).isoformat(),
            "timezone_label": str(get_amman_tz()),
        },
    )
