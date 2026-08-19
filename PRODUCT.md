# KinJo — Product Context

> **Status: derived, not dictated.** Everything below was read out of the
> codebase, `CLAUDE.md`, and the shipped UI. It is accurate about *what the
> software does*; it is inference about *who it is for and why*, and the
> sections marked **[confirm]** are the ones a product owner should correct
> rather than inherit. Impeccable reads this file before designing, so a wrong
> assumption here propagates into every future design decision.

---

## What it is

A kindergarten administration platform for Jordan. It connects the people who
run kindergartens, the supervisors who staff them, the parents whose children
attend, and a regulator-facing layer that monitors compliance and quality
across the network.

The product is bilingual with **Arabic as the default language and RTL as the
default direction**. English is a full second language, not a fallback.

## Who uses it

Four roles, from `UserRole` in `models.py`:

| Role | What success looks like for them |
|---|---|
| **Parent** | Sees their child's day — attendance, daily report, observations, health alerts. Applies for enrolment. |
| **Supervisor** | Runs a class. Files the daily report, logs attendance and incidents, records observations. |
| **Manager** | Runs a kindergarten. Watches their KPIs, staffing, enrolment pipeline and compliance. |
| **Admin** | Oversees the whole network. Compliance, quality bands, cross-kindergarten analytics, agency reporting. |

There is at most **one active manager per kindergarten** — a unique index, not
a convention. Adopt an existing manager rather than creating one.

## The domain

`Kindergarten · Child · Class · SupervisorAssignment · EnrollmentApplication ·
WaitlistEntry · AttendanceLog · DailyReport · Incident · Observation ·
CurriculumOutcome · Portfolio · HealthAlert · OperatingCalendar · Message`

The **daily report** is the heartbeat. `data_quality_score` is the percentage
of active kindergartens that filed a report in the last 7 days — a *compliance*
measure, not an attendance rate. KPI computation is authoritative in
`kpi_service.py` and must never be reimplemented inside an endpoint.

## Non-negotiable constraints

**Jordan time, UTC+3.** Every operational date is a Jordan date, via the
`_JORDAN_TZ` helper. `date.today()` and `datetime.now(timezone.utc)` are
wrong for anything user-facing — a report filed at 01:00 Amman time belongs to
the previous UTC day, and cache keys carrying a date must use the Jordan date.

**Bilingual by construction.** Any string that reaches the UI supplies both
`_ar` and `_en`. Templates guard on `ui_lang`; the server is the single writer
of the `kinjo_lang` cookie.

**Auditability.** Every state-changing admin operation calls
`log_audit_event()` with an `AuditAction` constant. Every admin endpoint sits
behind `require_admin`.

**Real accounts are real.** This system holds data about named children. Do not
create production accounts for testing, and do not weaken lockout or
authentication thresholds to make verification convenient.

## Design posture

**Operate** for the admin, manager, supervisor and parent surfaces — these are
tools, and the visitor is completing a task. **Persuade** for the public
surfaces (`/`, `/login`, `/services`).

Data density is the norm: rosters, KPI strips, tables, heatmaps. That makes
legibility at small sizes and in Arabic the dominant design constraint, and it
is why the type floor, the tint-foreground tokens and the RTL typography rules
in `DESIGN.md` exist.

---

## [confirm] — assumptions a product owner should correct

1. **Regulatory context.** The admin surface, quality bands and "agency
   reports" imply an external body consuming compliance data. Who is it, what
   do they require, and on what cadence? This shapes whether admin screens are
   *monitoring* or *reporting* surfaces.
2. **Primary audience by volume.** The design currently optimises for the
   admin/manager surfaces. If parents are the largest population by far, the
   parent surfaces deserve proportionally more attention.
3. **Arabic dialect and register.** Copy is Modern Standard Arabic. Whether
   parent-facing copy should sit closer to Jordanian colloquial is a product
   decision, not a design one.
4. **English audience.** Is English for international staff, for regulators, or
   for parents who prefer it? That determines how much the English surface may
   diverge from the Arabic.
5. **Success metric.** What does this product measure itself by — enrolment
   throughput, report compliance, parent engagement, incident reduction? The
   dashboards should lead with that number, and today they lead with
   compliance.
