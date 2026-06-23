# KinJo Data Science & Comprehensive Analytics Plan

**Version:** 1.0.0
**Status:** Final Blueprint — Engineering-Actionable
**Date:** 2026-06-24
**Applicable Platform:** KinJo Kindergarten Management System (Jordan)
**Owner:** Product + Engineering + Analytics Task Force

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Analytics Objectives](#2-analytics-objectives)
3. [Current KPI Inventory](#3-current-kpi-inventory)
4. [KPI Taxonomy](#4-kpi-taxonomy)
5. [Data Source Map](#5-data-source-map)
6. [Frontend Metrics Plan](#6-frontend-metrics-plan)
7. [Backend Metrics Plan](#7-backend-metrics-plan)
8. [Business and Operational Metrics Plan](#8-business-and-operational-metrics-plan)
9. [Missing Indicator Audit](#9-missing-indicator-audit)
10. [Proposed New Metrics](#10-proposed-new-metrics)
11. [Correlation and Deep-Dive Methodology](#11-correlation-and-deep-dive-methodology)
12. [Scientific Validation Framework](#12-scientific-validation-framework)
13. [Industry Benchmarking Framework](#13-industry-benchmarking-framework)
14. [Visualization and Dashboard Strategy](#14-visualization-and-dashboard-strategy)
15. [Data Governance Model](#15-data-governance-model)
16. [Testing and QA Strategy](#16-testing-and-qa-strategy)
17. [Implementation Roadmap](#17-implementation-roadmap)
18. [Risk Register](#18-risk-register)
19. [Acceptance Criteria](#19-acceptance-criteria)
20. [Final Recommendations](#20-final-recommendations)

---

## 1. Executive Summary

KinJo is a multi-role kindergarten management platform serving Jordan's early childhood education sector. It manages attendance, enrollment, incidents, daily reports, staff, capacity, and governance across a network of kindergartens distributed across Jordan's 12 governorates.

### Platform Architecture Snapshot

| Layer | Components | Scale |
|-------|-----------|-------|
| **Backend** | FastAPI + SQLAlchemy + Redis cache | 45+ API routers, 80+ DB models |
| **Analytics** | KPI engine, drill-down hierarchy, anomaly detection, prediction cache | 5-tier drill-down: Network → Governorate → KG → Class → Child |
| **Frontend** | Jinja2 + Plotly.js + Vanilla JS + WebSocket | 50+ template pages, bilingual AR/EN, RTL-native |
| **Observability** | Monitoring service, health checks, auto-scaling | System metrics, DB/cache health |

### Current State

The platform already possesses:
- ✅ Mature KPI engine (`kpi_service.py` — 10+ metrics with thresholds, bilingual explanations, actions)
- ✅ Hierarchical drill-down analytics (`analytics_service.py` — Network → Child level)
- ✅ Predictive forecasting (`predictive_analytics.py` — linear regression w/ confidence intervals)
- ✅ Anomaly detection (z-score based, severity-tiered)
- ✅ Governance ranking (Bayesian fair ranking, timeliness measurement)
- ✅ Real-time dashboards (WebSocket: `/ws/dashboard`, `/ws/heatmap`)
- ✅ Charting subsystem (Plotly, async Celery rendering)
- ✅ Jordan heat map intelligence system (geospatial analytics layer)

### Plan Purpose

This plan **extends** the existing foundation into a production-grade analytics layer that:

1. **Fills gaps** — adds frontend telemetry (Web Vitals, errors), backend SRE metrics (p95 latency, cache effectiveness), parent engagement, data quality, and 24 new operational metrics
2. **Adds rigor** — scientific validation framework with statistical significance, seasonality adjustment, sample size requirements
3. **Ensures actionability** — every metric maps to a decision, an owner, and a specific action
4. **Enables prediction** — attendance forecasting, enrollment projection, risk scoring
5. **Protects reliability** — error budgets, capacity runway, performance degradation detection

### Deliverables

| # | Deliverable | Owner | Outcome |
|---|-------------|-------|---------|
| D1 | 64+ unified KPIs across 4 layers | Data Science + Engineering | Actionable decision support |
| D2 | Frontend observability layer | Frontend Eng | Web Vitals, JS errors, UX telemetry |
| D3 | Backend SRE telemetry | Backend Eng | RED/USE metrics per endpoint |
| D4 | Correlation discovery engine | Data Science | Automated pairwise scan, causal probes |
| D5 | Scientific validation framework | Data Science + QA | Accuracy, completeness, consistency checks |
| D6 | Role-specific dashboards | Frontend + Product | 5 role-specific dashboard views |
| D7 | 16-week implementation roadmap | Engineering | Phased delivery with acceptance gates |

---

## 2. Analytics Objectives

### 2.1 Strategic Objectives

| # | Objective | Measurable Success | Timeframe | Owner |
|---|-----------|--------------------|-----------|-------|
| O1 | **Decision-grade observability** | Every KPI triggers a specific named action for a specific role (no vanity metrics) | Immediate | Admin |
| O2 | **Network health at a glance** | Admin can assess network state in < 10 seconds from a single dashboard | Wave 1 | Admin |
| O3 | **Early risk detection** | Anomaly detection identifies 80% of emerging problems before they become critical | Wave 3 | Engineering |
| O4 | **Parent engagement optimization** | Parent portal conversion and notification response rates improve ≥ 20% within 6 months | Wave 2 | Product |
| O5 | **System reliability SLA** | Backend p95 latency < 300ms; frontend LCP < 2.5s; availability > 99.5% | Wave 4 | Engineering |
| O6 | **Data trust assurance** | Weekly data quality audit passes ≥ 95% of checks; freshness score ≥ 0.9 | Wave 2 | Engineering + Admin |

### 2.2 Anti-Objectives (What This Plan Does NOT Do)

| Anti-Objective | Rationale |
|----------------|-----------|
| **Real-time PII analytics** | Privacy risk; no sensitive child data in telemetry or analytics exports |
| **Cross-kindergarten child-level data mixing** | IDOR risk; each KG's children are scoped by role |
| **External data integrations beyond Jordan MoSD** | Out of scope for this platform version |
| **AI-driven automated decision-making** | All predictions are decision-support only; humans approve actions |

---

## 3. Current KPI Inventory

### 3.1 Existing Implemented Metrics

The platform already computes 10 core KPIs via `kpi_service.py`:

| # | Metric Key | Name (EN) | Formula | Threshold (Green/Amber/Red) | Owner |
|---|-----------|-----------|---------|-----------------------------|-------|
| K01 | `overall_gcei` | Governance & Child Experience Index | 60% governance + 40% child experience composite | ≥80 / 60–79.99 / <60 | Admin |
| K02 | `attendance_rate` | Attendance Rate | (Actual attendance days ÷ Expected days) × 100 | ≥90% / 70–89.99% / <70% | Manager |
| K03 | `ratio_compliance` | Staff-Child Ratio Compliance | (Compliant minutes ÷ Total minutes) × 100 | ≥95% / 80–94.99% / <80% | Manager |
| K04 | `training_completion_rate` | Training Completion Rate | (Completed mandatory ÷ Assigned mandatory) × 100 | ≥90% / 75–89.99% / <75% | Manager |
| K05 | `report_submission_rate` | Report Submission Rate | (Submitted on time ÷ Expected) × 100 | ≥95% / 85–94.99% / <85% | Supervisor |
| K06 | `incident_rate` | Incident Rate | (Incidents ÷ Total children) × 100 | 0 / 0.51–1.0 / >1.0 | Manager |
| K07 | `serious_incident_rate` | Serious Incident Rate | Serious incidents only | 0 / 0.01–0.1 / >0.1 | Manager |
| K08 | `incident_followup_sla` | Incident Follow-up SLA (48h) | Follow-ups completed within 48h ÷ Total followups required | 100% / 90–99.99% / <90% | Manager |
| K09 | `chronic_absence_rate` | Chronic Absence Rate | Children missing ≥10% days ÷ Total enrolled | ≤5% / 5.01–10% / >10% | Manager |
| K10 | `capacity_utilization_rate` | Capacity Utilization Rate | (Enrolled children ÷ Total capacity) × 100 (target: ~90%) | 90% (nominal) / 80–100% / >100% or <70% | Manager |

### 3.2 Existing Analytics Capabilities

| Capability | Source File | Description |
|------------|------------|-------------|
| Hierarchical drill-down | `analytics_service.py` | Network → Governorate → KG → Class → Child |
| Predictive forecasting | `predictive_analytics.py` | Linear regression with 95% confidence interval |
| Anomaly detection | `analytics_domain.py` | Z-score based with severity levels |
| Governorate heat map | `heatmap/` subsystem | Daily ETL, correlation matrix, risk scoring |
| Benchmarking | `manager_analytics.py` | Manager-scoped performance comparison |
| Governance ranking | `governance_kpi_service.py` | Bayesian fair ranking with smoothing |
| Decision support | `decision_support_api.py` | Geo distribution, risk scoring, classification |
| Data quality scoring | `data_quality_service.py` | Freshness, completeness, consistency indices |
| Real-time streaming | `realtime_service.py` | WebSocket dashboards, 30s update cadence |
| Async charting | `charts/service.py` | Plotly rendering with Celery, Redis cache |

### 3.3 What Is Missing

| Gap | Impact | Priority |
|-----|--------|----------|
| No frontend observability (Web Vitals, JS errors, UX telemetry) | Cannot measure user experience or detect UX regressions | HIGH |
| No backend SRE metrics (p95 latency, cache effectiveness, error budgets) | Cannot set or enforce performance SLAs | HIGH |
| No parent engagement analytics | Cannot optimize parent communication or satisfaction | MEDIUM |
| No data quality observability dashboard | Data issues surface as user complaints before detection | HIGH |
| No correlation discovery engine | Analytical insights require manual investigation | MEDIUM |
| No scientific validation framework | KPI accuracy cannot be independently verified | HIGH |
| No RTL visual regression testing | Arabic UI regressions go undetected until user-reported | HIGH |
| No error budget / SLO management | No structured reliability engineering practice | MEDIUM |

---

## 4. KPI Taxonomy

### 4.1 Tier 1 — Strategic Executive KPIs

Directly inform C-suite / Board-level decisions. Computed at network scope (all Jordan).

| ID | Metric | Formula | Purpose | Target | Critical | Action |
|----|--------|---------|---------|--------|----------|--------|
| E01 | **Network Health Index** | Weighted avg: GCEI (30%) + Attendance (25%) + 1/Incident_Rate (15%) + Compliance (15%) + Data_Quality (15%) | Composite state of entire network | ≥80 | <60 | Executive review |
| E02 | **Governance & Child Experience Index** | 60% governance + 40% child experience | Kindergarten performance quality | ≥80 | <60 | Per-KG remediation |
| E03 | **Network Attendance Rate** | Sum(enrolled) / Sum(total capacity) — weighted by enrollment | Children attending divided by total enrolled | ≥85% | <75% | Regional intervention |
| E04 | **Network Incident Rate** | (Total incidents ÷ Total children) × 100 | Safety incidents per 100 children network-wide | ≤0.5 | >1.0 | Safety review |
| E05 | **Network Data Freshness** | 1 − (KGs past 2h without daily report ÷ Total active KGs) | Data currency across all KGs | ≥0.95 | <0.80 | Infrastructure audit |
| E06 | **Network Staff Turnover Rate** | (Departures ÷ Avg headcount) × 12 | Teacher/supervisor departures per month | ≤10% | >15% | HR review |

### 4.2 Tier 2 — Network-Level Operational KPIs

Inform network managers and Ministry regulators.

| ID | Metric | Formula | Purpose | Target | Critical | Action |
|----|--------|---------|---------|--------|----------|--------|
| N01 | **Governorate Risk Ranking** | Logistic regression of: attendance drop, incident spike, compliance violation, data quality | Per-governorate composite risk | Lower = better | Top 3 → weekly audit | Governorate manager escalation |
| N02 | **Capacity Runway** | Linear regression enrollment forecast → months to 100% occupancy | Months until capacity ceiling | ≥6 months | <3 months | Enrollment freeze / expansion |
| N03 | **Report Compliance Rate** | (On-time reports ÷ Total expected) × 100 | Daily reports submitted on-time | ≥95% | <85% | Supervisor review |
| N04 | **Chronic Absence Rate** | (Chronic absentees ÷ Total enrolled) × 100 | Children missing ≥10% of school days | ≤5% | >10% | Parent engagement |
| N05 | **Alert Time-to-Detect** | Alert_time − Event_time | Minutes from occurrence to alert creation | <5 min | >30 min | Anomaly detection tuning |
| N06 | **Positive Response Rate (Parent)** | (Acknowledged ÷ Sent) × 100 | Parent notification acknowledgment | ≥70% | <50% | UX review |

### 4.3 Tier 3 — Kindergarten-Level KPIs

Manage individual kindergarten performance.

| ID | Metric | Formula | Purpose | Target | Critical | Action |
|----|--------|---------|---------|--------|----------|--------|
| K01 | **KG-Specific GCEI** | Same as E02, KG-scoped | Single KG performance | ≥80 | <60 | Improvement plan |
| K02 | **KG Attendance Rate** | (Present days ÷ Expected days) × 100 | Per-KG attendance | ≥90% | <70% | Parent outreach |
| K03 | **KG Incident Rate** | (KG incidents ÷ KG children) × 100 | Per-KG safety | ≤0.5 | >1.0 | Safety audit |
| K04 | **Class Occupancy %** | (Enrolled ÷ Capacity) × 100 | Per-class capacity usage | 85–100% | >100% or <70% | Rebalance classes |
| K05 | **Teacher-Child Ratio Now** | Headcount children ÷ Present staff | Live compliance | Compliant per age group | Breached | Staffing supplemental |
| K06 | **Overdue Tasks Count** | COUNT(DATEDIFF(now, due_date) > 0 AND status ≠ DONE) | Operational discipline | 0 | >3 | Task escalation |
| K07 | **Student Age Distribution** | Count per age group, balance check | Curriculum balance | Balanced | Over-concentrated | Rebalancing plan |
| K08 | **Enrollment Growth Rate** | ((Current − Prior month) ÷ Prior month) × 100 | Month-over-month change | +2–8% | <−5% or >+20% | Recruitment/freeze |

### 4.4 Tier 4A — Parent Engagement KPIs

> **⚠️ Privacy Note:** No sensitive child data (health, incidents, individual attendance) appears in telemetry. Aggregated, anonymized, KG-scoped metrics only.

| ID | Metric | Formula | Purpose | Target | Critical | Action |
|----|--------|---------|---------|--------|----------|--------|
| P01 | **Parent Portal Login Frequency** | Logins per parent per month | Engagement intensity | ≥2/month | ≤0.5/30d | Outreach |
| P02 | **Notification → View Conversion** | (DailyReport views ÷ Notifications sent) × 100 | Notification effectiveness | ≥70% | <40% | UX review |
| P03 | **Notification → Action Conversion** | (Action taken ÷ Relevant notification) × 100 | Call-to-action effectiveness | ≥30% | <15% | CTA optimization |
| P04 | **Absence Request Turnaround** | Resolution − Submission time | Processing speed | <24h | >48h | Supervisor training |
| P05 | **Parent NPS Score** | (Promoters − Detractors) ÷ Respondents × 100 | Satisfaction | ≥50 (Good) | <0 (Bad) | Experience program |
| P06 | **Message Open Rate** | (Opened ÷ Sent) × 100 | Communication effectiveness | ≥80% | <50% | Messaging strategy |
| P07 | **Daily Report Satisfaction** | Avg parent rating of daily reports | Content quality | ≥4.0/5.0 | <3.0 | Content review |

### 4.5 Tier 4B — Data Quality KPIs

| ID | Metric | Formula | Purpose | Target | Critical | Action |
|----|--------|---------|---------|--------|----------|--------|
| DQ01 | **Data Freshness** | now() − max(DailyReport.date) per KG | Data currency | <2h | >6h | Immediate alert |
| DQ02 | **Data Completeness** | (Present records ÷ Expected records) × 100 | Expected vs. actual | ≥98% | <90% | Audit |
| DQ03 | **Data Accuracy** | (Records passing validation ÷ Sampled) × 100 | Validation pass rate | ≥99% | <95% | Investigation |
| DQ04 | **Field Consistency** | (Cross-field consistent ÷ Sampled) × 100 | Logical consistency | ≥97% | <90% | Schema review |
| DQ05 | **Uniqueness Rate** | 1 − (Duplicates ÷ Total critical records) | Duplicate prevention | 100% | <99% | Cleanup |
| DQ06 | **Validity Rate** | (In-range values ÷ Sampled) × 100 | Range constraint | ≥99% | <95% | Validation audit |

### 4.6 Tier 5A — Frontend Performance KPIs

| ID | Metric | Purpose | Target | Critical | Method |
|----|--------|---------|--------|----------|--------|
| FE01 | **LCP (Largest Contentful Paint)** | Perceived load speed | <2.5s | >4.0s | PerformanceObserver |
| FE02 | **FID (First Input Delay)** | Responsiveness to first interaction | <100ms | >300ms | Event Timing API |
| FE03 | **CLS (Cumulative Layout Shift)** | Visual stability | <0.1 | >0.25 | Layout Shift API |
| FE04 | **API Response p95** | Backend latency perception | <500ms | >2000ms | fetch() wrapper |
| FE05 | **Client Error Rate** | JS exceptions + unhandled rejections | <0.1% | >1.0% | window.onerror |
| FE06 | **Auth Flow Completion** | Login/logout success rate | >95% | <85% | Auth event tracking |
| FE07 | **RTL Layout Integrity** | Arabic rendering correctness | 100% | <100% | RTL CSS + screenshots |
| FE08 | **Offline Cache Hit Rate** | Service Worker cache effectiveness | >80% | <50% | Service Worker events |

### 4.7 Tier 5B — Backend Reliability KPIs

| ID | Metric | Purpose | Target | Critical | Source |
|----|--------|---------|--------|----------|--------|
| BE01 | **Endpoint p95 Latency** | Request processing speed | <300ms | >1000ms | Middleware timing |
| BE02 | **DB Query p95** | SQL performance | <200ms | >1000ms | SQLAlchemy events |
| BE03 | **Cache Hit Rate** | Cache effectiveness | ≥90% | <75% | cache_service stats |
| BE04 | **Auth Token Refresh Success** | Token refresh reliability | >99.5% | <99% | /api/auth/refresh |
| BE05 | **Background Job Failure Rate** | Async reliability | <1% | >5% | Celery task logs |
| BE06 | **Error Budget Burn** | SLO compliance | <50% | >80% | SLO counters |

---

## 5. Data Source Map

### 5.1 Primary Data Sources

| Domain | Tables | Current Status | Gaps |
|--------|--------|----------------|------|
| **Children** | `children`, `enrollment_applications`, `parent_profiles` | ✅ Mature | — |
| **Attendance** | `attendance_logs` (UNIQUE child_id, date) | ✅ Mature | — |
| **Reports** | `daily_reports`, `daily_report_views` | ✅ Mature | Parent satisfaction rating |
| **Incidents** | `incidents` (follow-up SLA tracked) | ✅ Mature | — |
| **Staff/HR** | `users`, `supervisor_profiles`, `staff_presence_logs`, `training_completion` | ✅ Mature | — |
| **Classes** | `classes` (capacity, enrolled_count, age_group) | ✅ Mature | — |
| **Governance** | `governance_scores`, `ratio_compliance` | ✅ Mature | — |
| **Analytics Cache** | `advanced_analytics_cache`, `analytics_dimension_cache`, `prediction_cache` | ✅ Mature | — |
| **Notifications** | `notifications`, `messages`, `message_user_states` | ✅ Mature | — |
| **Surveys** | `surveys`, `survey_responses` (NPS) | ✅ Mature | — |
| **Tasks** | `tasks` | ✅ Mature | — |
| **Absences** | `absence_requests` | ✅ Mature | — |
| **Alerts** | `active_alerts`, `anomaly_alerts`, `alert_thresholds` | ✅ Mature | — |
| **Audit** | `audit_logs` (before/after diff) | ✅ Mature | — |
| **AI/ML** | `ai_job_logs`, `ai_feedback`, `ai_model_versions`, `ai_embeddings` | ✅ Present | — |
| **Jordan Geography** | `governorates`, `map_indicator_snapshot`, `map_correlation_snapshot`, `map_risk_snapshot` | ✅ Present | — |

### 5.2 Gaps Requiring Instrumentation

| Gap | Impact | Proposed Solution | Complexity | Effort |
|-----|--------|------------------|------------|--------|
| **Frontend error telemetry** | Cannot detect UX regressions | `window.onerror` + `unhandledrejection` → `/api/telemetry/errors` | Medium | 1 week |
| **Web Vitals collection** | No LCP/FID/CLS data | `PerformanceObserver` wrapper → backend structured log | Low | 3 days |
| **Parent action tracking** | Cannot measure notification effectiveness | Instrument absent-request, message-reply, portal login events | Medium | 1 week |
| **DB query timing** | No p95 SQL insight | SQLAlchemy `before_cursor_execute` / `after_cursor_execute` | Low | 2 days |
| **Cache instrumentation** | No hit/miss visibility | Wrap `cache_service` with Prometheus-style counters | Low | 3 days |
| **Background job telemetry** | No reliability metrics | Celery signal handlers | Medium | 4 days |
| **RTL visual regression** | No automated Arabic QA | Playwright/screenshot diff for Arabic pages | High | 2 weeks |
| **Parent satisfaction rating** | No direct parent feedback on reports | Rating widget in parent portal per daily report | Low | 1 week |

---

## 6. Frontend Metrics Plan

### 6.1 Design Principles

1. **Privacy-first**: No PII (names, IDs, health data) in any telemetry event
2. **Anonymous by default**: Session IDs are hashed; only role + page + event are tracked
3. **Non-blocking**: Telemetry uses `requestIdleCallback()` and batch flush every 10s
4. **Graceful degradation**: If telemetry fails, app still works normally
5. **RTL-aware**: All metrics work correctly in both Arabic RTL and English LTR contexts

### 6.2 Event Schema

```javascript
// Frontend Analytics Event Schema
const TelemetryEvent = {
  event_id: "uuid-v4",
  session_id: "sha256-hashed-session",
  event_type: "page_view | interaction | api_call | error",
  page: "/admin/dashboard",  // route path only
  role: "ADMIN|MANAGER|SUPERVISOR|PARENT",
  lang: "ar|en",
  direction: "rtl|ltr",
  timestamp_ms: 1719000000000,
  duration_ms: 245,
  payload: {
    metric_name: "lcp|fid|cls|api_p95|js_error",
    value: 234.56,
    endpoint: "/api/analytics/network-summary",  // api_call only
    status_code: 200,                              // api_call only
    error_type: "TypeError",                        // error only
    stack_hash: "a1b2c3d4"                          // SHA-256 prefix, never full stack
  }
};
```

### 6.3 Privacy Rules

| Rule | Description |
|------|-------------|
| **No child names** | Never collect child names, dates of birth, or parent names |
| **No health data** | Never include incident type, illness details, or health notes |
| **No individual attendance** | Aggregate attendance only; never log specific child absences |
| **No file paths** | Use `sha256-prefix` of stack traces; never expose filesystem paths |
| **No query params** | Strip all query parameters from URLs before logging |
| **Session-scoped** | Events are session-local; no cross-session tracking |
| **Opt-out ready** | Single config flag to disable all telemetry globally |

### 6.4 Instrumentation Specification

| Metric | Collection Method | Sampling | Flush | Backend Target |
|--------|------------------|----------|-------|----------------|
| LCP | `PerformanceObserver { largest-contentful-paint: true }` | 100% | 10s batch | `/api/telemetry/vitals` |
| FID | `PerformanceObserver { first-input: true }` | 100% | 10s batch | `/api/telemetry/vitals` |
| CLS | `PerformanceObserver { layout-shift: true }` | 100% | 10s batch | `/api/telemetry/vitals` |
| API p95 | `fetch()` wrapper (timing per endpoint) | 100% | 10s batch | `/api/telemetry/api` |
| JS Errors | `window.addEventListener('error')` + `unhandledrejection` | 100% | Immediate (priority) | `/api/telemetry/errors` |
| Auth Events | Login form submit → result tracking | 100% | Real-time | `/api/telemetry/auth` |
| RTL Integrity | CSS assertion check on mount per page | 25% sessions | 10s batch | `/api/telemetry/rtl` |
| Cache Metrics | Service Worker `fetch` event classification | 100% | 10s batch | `/api/telemetry/cache` |

### 6.5 Backend Telemetry Endpoint Structure

```python
# POST /api/telemetry/vitals
class WebVitalsPayload(BaseModel):
    session_id: str       # hashed
    page: str             # route path
    role: str             # ADMIN/MANAGER/SUPERVISOR/PARENT
    lang: str             # ar/en
    direction: str        # rtl/ltr
    metrics: List[WebVitalMetric]

class WebVitalMetric(BaseModel):
    name: str             # lcp/fid/cls
    value: float          # ms for LCP/FID, unitless for CLS
    rating: str           # good/needs-improvement/poor

# POST /api/telemetry/errors
class ClientErrorPayload(BaseModel):
    session_id: str
    page: str
    role: str
    error_type: str       # uncaught|rejection|runtime
    message: str          # sanitized (no stack trace)
    stack_hash: str       # SHA-256 first 8 chars for grouping
    timestamp_ms: int

# POST /api/telemetry/api
class ApiCallPayload(BaseModel):
    session_id: str
    endpoint: str         # /api/path only (no query params)
    method: str
    status_code: int
    duration_ms: float
    cache_hit: Optional[bool]
```

### 6.6 Web Vitals Dashboard Component

```javascript
// static/js/web_vitals_collector.js
class KinjoWebVitals {
  constructor(config = {}) {
    this.config = {
      batchSize: config.batchSize || 50,
      flushInterval: config.interval || 10000,
      endpoint: config.endpoint || '/api/telemetry/vitals',
      enabled: config.enabled ?? true,
      ...config
    };
    this.queue = [];
    this.sessionId = this.generateSessionId();

    if (this.config.enabled) {
      this.init();
    }
  }

  init() {
    this.observeLCP();
    this.observeFID();
    this.observeCLS();
    this.setupFlush();
  }

  observeLCP() {
    if (!('PerformanceObserver' in window)) return;
    const observer = new PerformanceObserver((entryList) => {
      const entries = entryList.getEntries();
      const lastEntry = entries[entries.length - 1];
      this.track('lcp', {
        value: lastEntry.startTime,
        rating: this.rateLCP(lastEntry.startTime)
      });
    });
    observer.observe({ type: 'largest-contentful-paint', buffered: true });
  }

  observeFID() {
    if (!('PerformanceObserver' in window)) return;
    const observer = new PerformanceObserver((entryList) => {
      const entries = entryList.getEntries();
      const first = entries[0];
      const fid = first.processingStart - first.startTime;
      this.track('fid', {
        value: fid,
        rating: this.rateFID(fid)
      });
    });
    observer.observe({ type: 'first-input', buffered: true });
  }

  observeCLS() {
    if (!('PerformanceObserver' in window)) return;
    let clsValue = 0;
    let sessionValue = 0;
    let sessionEntries = [];

    const observer = new PerformanceObserver((entryList) => {
      for (const entry of entryList.getEntries()) {
        if (!entry.hadRecentInput) {
          const firstSessionEntry = sessionEntries[0];
          if (!firstSessionEntry ||
              entry.startTime - firstSessionEntry.startTime < 1000 ||
              entry.startTime - firstSessionEntry.startTime < 5000) {
            sessionValue += entry.value;
            sessionEntries.push(entry);
          } else {
            sessionValue = entry.value;
            sessionEntries = [entry];
          }
          clsValue = Math.max(clsValue, sessionValue);
        }
      }
      this.track('cls', {
        value: clsValue,
        rating: this.rateCLS(clsValue)
      });
    });
    observer.observe({ type: 'layout-shift', buffered: true });
  }

  rateLCP(ms) {
    if (ms <= 2500) return 'good';
    if (ms <= 4000) return 'needs-improvement';
    return 'poor';
  }

  rateFID(ms) {
    if (ms <= 100) return 'good';
    if (ms <= 300) return 'needs-improvement';
    return 'poor';
  }

  rateCLS(value) {
    if (value <= 0.1) return 'good';
    if (value <= 0.25) return 'needs-improvement';
    return 'poor';
  }

  track(metricName, payload) {
    this.queue.push({
      name: metricName,
      ...payload,
      timestamp_ms: Date.now()
    });
    if (this.queue.length >= this.config.batchSize) {
      this.flush();
    }
  }

  setupFlush() {
    setInterval(() => this.flush(), this.config.flushInterval);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') {
        this.flush();
      }
    });
  }

  async flush() {
    if (this.queue.length === 0) return;
    const batch = this.queue.splice(0);
    try {
      await fetch(this.config.endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Language': document.documentElement.lang || 'ar'
        },
        body: JSON.stringify({
          session_id: this.sessionId,
          page: window.location.pathname,
          role: window.__KINJO_USER_ROLE__ || 'UNKNOWN',
          lang: document.documentElement.lang || 'ar',
          direction: document.documentElement.dir || 'ltr',
          metrics: batch
        }),
        keepalive: true,
        priority: 'low'
      });
    } catch (e) {
      if (!navigator.onLine) {
        sessionStorage.setItem('kinjo_telemetry_buffer', JSON.stringify(batch));
      }
    }
  }

  generateSessionId() {
    return 's_' + Math.random().toString(36).substring(2, 15);
  }
}

window.KinjoWebVitals = KinjoWebVitals;
```

### 6.7 Frontend Error Monitoring

```javascript
// static/js/client_error_monitor.js
class KinjoErrorMonitor {
  constructor(config = {}) {
    this.endpoint = config.endpoint || '/api/telemetry/errors';
    this.enabled = config.enabled ?? true;
    this.sessionId = window.__KINJO_WEB_VITALS__?.sessionId || 'unknown';
    if (this.enabled) this.init();
  }

  init() {
    window.addEventListener('error', (event) => {
      this.report('uncaught', event);
    });

    window.addEventListener('unhandledrejection', (event) => {
      this.report('rejection', event);
    });

    window.addEventListener('error', (event) => {
      if (event.message?.includes &&
          (event.message.includes('TypeError') || event.message.includes('ReferenceError'))) {
        this.incrementRTECounter();
      }
    }, { capture: true });
  }

  report(type, event) {
    const payload = {
      session_id: this.sessionId,
      page: window.location.pathname,
      role: window.__KINJO_USER_ROLE__ || 'UNKNOWN',
      error_type: type,
      message: this.sanitize((event.message || event.reason || 'Unknown error').toString()),
      stack_hash: event.error?.stack ? this.hashStack(event.error.stack) : null,
      timestamp_ms: Date.now()
    };

    fetch(this.endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
      priority: 'low'
    }).catch(() => {
      // Queue for retry on next page load
      const queued = JSON.parse(localStorage.getItem('kinjo_error_queue') || '[]');
      queued.push(payload);
      localStorage.setItem('kinjo_error_queue', JSON.stringify(queued.slice(-100)));
    });
  }

  sanitize(message) {
    // Strip file paths, URLs, PII
    return message
      .replace(/file:\/\/[^\s]+/g, '[path]')
      .replace(/https?:\/\/[^\s]+/g, '[url]')
      .replace(/\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/g, '[email]')
      .replace(/\b\d{4}-\d{2}-\d{2}\b/g, '[date]')
      .substring(0, 500);
  }

  hashStack(stack) {
    // Hash only first two frames for privacy
    const frames = stack.split('\n').slice(0, 2).join('\n');
    // Simple hash (non-cryptographic sufficient for grouping)
    let hash = 0;
    for (let i = 0; i < frames.length; i++) {
      const char = frames.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(16).substring(0, 8);
  }

  incrementRTECounter() {
    const counter = parseInt(sessionStorage.getItem('kinjo_rte_count') || '0') + 1;
    sessionStorage.setItem('kinjo_rte_count', counter.toString());
  }
}

window.KinjoErrorMonitor = KinjoErrorMonitor;
```

---

## 7. Backend Metrics Plan

### 7.1 SRE Telemetry Architecture

```
Request Flow:
─────────────────────────────────────────────────────────────────────
Client Request → Middleware (timing start) → Router → Business Logic
                                                  ↓
                                        DB Query (SQLAlchemy event)
                                                  ↓
                                        Cache Service (hit/miss counter)
                                                  ↓
                                        Response Build
                                                  ↓
                                        Middleware (timing end) → Structured Log
                                                  ↓
                                        Prometheus-style Counter Export
─────────────────────────────────────────────────────────────────────
```

### 7.2 RED Metrics (Rate, Errors, Duration)

| Metric | Formula | Collection Point | Target | Alert Threshold |
|--------|---------|-----------------|--------|-----------------|
| **Request Rate** | Requests per second per endpoint | Middleware | Baseline + 20% headroom | Baseline + 50% (plan) |
| **Error Rate** | Status ≥ 400 / Total requests | Middleware | < 1% | > 2% |
| **Duration p50** | Median request processing time | Middleware | < 150ms | > 500ms |
| **Duration p95** | 95th percentile request time | Middleware | < 300ms | > 1000ms |
| **Duration p99** | 99th percentile request time | Middleware | < 800ms | > 3000ms |
| **Concurrent Requests** | Active requests gauge | Middleware | < 50 | > 100 |
| **Saturation** | CPU% + Memory% + Connection% | System metrics | < 70% | > 85% |

### 7.3 USE Metrics (Utilization, Saturation, Errors)

| Resource | Utilization | Saturation | Errors |
|----------|------------|------------|--------|
| **PostgreSQL** | Active connections / max_pool | Connection wait time average | Deadlocks / timeouts per hour |
| **Redis Cache** | Memory used / max memory | Eviction rate (keys/sec) | Connection errors / minute |
| **Disk I/O** | Read + Write MB/s | IO wait percentage of CPU | IO errors / minute |
| **CPU** | Load average / core count | Run queue length (processes waiting) | Context switches / sec |
| **Memory** | RSS / total available | OOM event count | OOM kill events |
| **Network** | Bandwidth used / capacity | Retransmit percentage | Timeouts / connection errors |
| **Application** | Worker utilization | Queue depth (pending tasks) | Worker restart events |

### 7.4 Backend Instrumentation Specifications

#### Request Latency Tracking (Middleware)

```python
# Middleware: performance_monitor.py (already exists, extend it)
# Add structured RED metric logging:

class REDMetricMiddleware:
    async def __call__(self, request, call_next):
        start = time.perf_counter()
        correlation_id = request.state.correlation_id or str(uuid.uuid4())

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            await self.record(
                correlation_id=correlation_id,
                method=request.method,
                endpoint=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                is_error=response.status_code >= 400
            )
            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            await self.record_error(
                correlation_id=correlation_id,
                method=request.method,
                endpoint=request.url.path,
                error_type=type(e).__name__,
                duration_ms=duration_ms
            )
            raise

    async def record(self, correlation_id, method, endpoint, status_code, duration_ms, is_error):
        # Emit to structured log in JSON format
        metric = {
            "event": "request_completed",
            "correlation_id": correlation_id,
            "method": method,
            "endpoint": endpoint,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "is_error": is_error,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "user_role": getattr(request.state, 'user_role', None)
        }
        logger.info(json.dumps(metric))

        # Update rolling window metrics (in-memory + Redis)
        await metrics_window.record(
            endpoint=endpoint,
            duration=duration_ms,
            error=is_error
        )
```

#### Database Query Tracking (SQLAlchemy Events)

```python
# New file: db_query_metrics.py
from sqlalchemy import event
import time

class DBQueryMetrics:
    def __init__(self):
        self.queries = {}

    def attach(self, engine):
        @event.listens_for(engine, 'before_cursor_execute')
        def before_execute(conn, cursor, statement, parameters, context, executemany):
            context._query_start_time = time.perf_counter()

        @event.listens_for(engine, 'after_cursor_execute')
        def after_execute(conn, cursor, statement, parameters, context, executemany):
            duration_ms = (time.perf_counter() - context._query_start_time) * 1000
            table = self._extract_table(statement)
            operation = self._extract_operation(statement)

            # Record metric
            metrics_window.record_query(
                table=table,
                operation=operation,
                duration_ms=duration_ms,
                statement_hash=self._hash_statement(statement)
            )

    def _extract_table(self, statement):
        # Parse table name from SQL
        import re
        match = re.search(r'FROM\s+([a-z_]+)', statement, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'INTO\s+([a-z_]+)', statement, re.IGNORECASE)
        if match:
            return match.group(1)
        match = re.search(r'UPDATE\s+([a-z_]+)', statement, re.IGNORECASE)
        if match:
            return match.group(1)
        return 'unknown'

    def _extract_operation(self, statement):
        stmt_upper = statement.strip().upper()
        if stmt_upper.startswith('SELECT'): return 'SELECT'
        if stmt_upper.startswith('INSERT'): return 'INSERT'
        if stmt_upper.startswith('UPDATE'): return 'UPDATE'
        if stmt_upper.startswith('DELETE'): return 'DELETE'
        return 'OTHER'

    def _hash_statement(self, statement):
        import hashlib
        # Normalize parameterized parts for hash consistency
        normalized = re.sub(r'\d+', '?', statement)
        return hashlib.md5(normalized.encode()).hexdigest()[:8]
```

### 7.5 Cache Service Instrumentation

```python
# Extend cache_service.py with counter tracking
class InstrumentedCacheService:
    def __init__(self, underlying):
        self._cache = underlying
        self.hits = Counter('cache_hits_total', 'Total cache hits')
        self.misses = Counter('cache_misses_total', 'Total cache misses')
        self.operations = Histogram('cache_operation_ms', 'Cache operation time',
                                     labels=['operation', 'hit'])

    async def get(self, key: str):
        start = time.perf_counter()
        result = await self._cache.get(key)
        duration = (time.perf_counter() - start) * 1000

        if result is not None:
            self.hits.inc()
            self.operations.labels('get', 'hit').observe(duration)
        else:
            self.misses.inc()
            self.operations.labels('get', 'miss').observe(duration)

        return result

    @property
    def hit_rate(self):
        total = self.hits.value() + self.misses.value()
        return self.hits.value() / total if total > 0 else 0.0

    def get_stats(self):
        return {
            "hits": self.hits.value(),
            "misses": self.misses.value(),
            "hit_rate": round(self.hit_rate * 100, 2),
            "total_operations": self.hits.value() + self.misses.value()
        }
```

### 7.6 Background Job Reliability

```python
# Extend celery_app.py with signal-based monitoring
from celery.signals import task_postrun, task_failure, task_prerun

@task_postrun.connect
def task_success_handler(task_id, task, args, kwargs, retval, state, **kwargs_extra):
    metrics_window.record_task(
        task_name=task.name,
        task_id=task_id,
        status='completed',
        duration_ms=kwargs_extra.get('runtime', 0) * 1000
    )

@task_failure.connect
def task_failure_handler(task_id, exception, traceback, sender, **kwargs):
    metrics_window.record_task(
        task_name=sender.name,
        task_id=task_id,
        status='failed',
        error_type=type(exception).__name__
    )

@task_prerun.connect
def task_start_handler(task_id, task, **kwargs):
    # Record task queue depth for saturation metric
    metrics_window.record_queue_depth(
        queue_name=getattr(task.queue, 'name', 'default')
    )
```

### 7.7 Structured Log Format

All metrics are logged in JSON format for ingestion by log aggregation:

```json
{
  "timestamp": "2026-06-24T10:15:23.456Z",
  "level": "INFO",
  "event": "request_completed",
  "correlation_id": "b7f8c4a2-...",
  "method": "GET",
  "endpoint": "/api/analytics/network-summary",
  "status_code": 200,
  "duration_ms": 142.37,
  "db_duration_ms": 38.21,
  "cache_hit": true,
  "user_role": "ADMIN",
  "governorate_scope": "AMMAN",
  "client_ip_hash": "a1b2c3",
  "user_agent_class": "desktop_browser"
}
```

---

## 8. Business and Operational Metrics Plan

### 8.1 Metrics Lifecycle

Every metric follows a strict lifecycle:

```
DEFINE → INSTRUMENT → VALIDATE → DEPLOY → MONITOR → REVIEW → RETIRE
```

| Stage | Gate Criteria | Owner | Duration |
|-------|---------------|-------|----------|
| **DEFINE** | Metric specification written with formula, target, owner, action | Data Scientist + Business | 1 day |
| **INSTRUMENT** | Code deployed with test coverage ≥ 80% | Engineer | 2–5 days |
| **VALIDATE** | Scientific validation passed (Section 12) | Data Scientist + QA | 2–3 days |
| **DEPLOY** | Dashboard integrated, alerts configured | Engineer + Product | 1–2 days |
| **MONITOR** | Automated weekly reporting on metric health | Data Scientist | Ongoing |
| **REVIEW** | Quarterly: still used, still relevant, still accurate | Admin + Product | Quarterly |
| **RETIRE** | Deprecated after removal of all references and exports | Engineer | 2–3 days |

### 8.2 Decision-Action Matrix

Every metric must map to a specific decision. The following table defines this for all metrics:

### 8.3 Decision Mappings — Full Specification

| Metric | Decision Triggered | Action Owner | SLA | Escalation Path |
|--------|-------------------|--------------|-----|-----------------|
| GCEI < 60 | Launch KG improvement plan | Manager (per KG) | 7 days | Director intervention |
| GCEI < 40 | Emergency remediation | Admin + Manager | 24h | Ministry notification |
| Attendance < 70% | Parent engagement campaign | Manager | 3 days | Supervisor direct contact |
| Attendance < 50% | Welfare check required | Supervisor + Manager | 24h | Social services referral |
| Incident Rate > 1.0 | Safety audit | Supervisor + Manager | 24h | Admin + Ministry |
| Serious Incident > 0 | Immediate review | Manager | 4h | Admin + MoSD + Parents |
| Report Compliance < 85% | Workflow training | Supervisor | 1 day | Manager review |
| Ratio Compliance < 80% | Immediate staffing adjustment | Manager | Same day | Admin + Ministry |
| Capacity > 105% | Enrollment freeze | Manager | 3 days | Admin decision |
| Capacity < 70% | Enrollment push or closure review | Admin | 7 days | Business review |
| Training < 75% | Mandatory retraining | Manager + HR | 14 days | Compliance audit |
| NPS < 0 | Parent experience review | Product + Admin | 14 days | Board review |
| Data Freshness > 6h | Infrastructure check | Engineering | 1 hour | On-call engineer |
| Data Completeness < 90% | Data audit | Engineering + Admin | 1 day | Root cause investigation |
| FE Error Rate > 1% | Bug triage | Frontend Engineering | 4 hours | Incident creation |
| BE Latency p95 > 1s | Performance investigation | Backend Engineering | 2 hours | SRE review |
| Cache Hit Rate < 75% | Cache strategy review | Engineering | 3 days | Architecture review |
| Alert Time-to-Detect > 30 min | Anomaly detection tuning | Data Science | 1 week | System redesign review |
| Staff Turnover > 15%/mo | HR crisis protocol | HR + Admin | 48h | Retention program |

---

## 9. Missing Indicator Audit

### 9.1 Audit Methodology

Four complementary approaches:

1. **User Journey Mapping** — Walk each role through their critical workflows; note decisions made without data support
2. **Data Availability Scan** — Query the schema for tables/columns that exist but have no corresponding metric
3. **Incident Root-Cause Analysis** — Review recent incidents/alerts; identify contributing factors that were invisible
4. **Competitive Benchmarking** — Compare against peer early-childhood platforms and analytics products

### 9.2 Audit Matrix

| # | Category | Missing Indicator | Decision Enabled | Priority | Complexity |
|---|----------|-------------------|-----------------|----------|------------|
| 1 | UX Friction | Time-to-first-dashboard-action after login | Dashboard IA quality assessment | HIGH | Medium |
| 2 | UX Friction | Morning routine completion rate (% managers with all morning tasks done by 10 AM) | Daily operational readiness | MEDIUM | Medium |
| 3 | UX Friction | Feature adoption depth (% of users completing multi-step workflows) | UX investment prioritization | MEDIUM | High |
| 4 | UX Friction | Form abandonment rate (started but not submitted) | Form UX optimization | MEDIUM | Medium |
| 5 | Data Quality | Per-KG report age (hours since last DailyReport.date) | Silent data lag detection | HIGH | Low |
| 6 | Data Quality | Required fields coverage percentage | Data completeness | MEDIUM | Low |
| 7 | Data Quality | Cross-table reconciliation pass rate | System consistency | MEDIUM | Low |
| 8 | Alert Quality | Alert signal-to-noise ratio (critical+high / total) | Alert system health | HIGH | Low |
| 9 | Alert Quality | Alert false positive rate | Threshold calibration | MEDIUM | Medium |
| 10 | Alert Quality | Alert time-to-acknowledge by severity | Alert response SLA | MEDIUM | Low |
| 11 | Security | Failed login rate per user/IP | Brute-force detection | HIGH | Low |
| 12 | Security | MFA bypass attempt count | Security monitoring | MEDIUM | Low |
| 13 | Security | Password reset completion rate | Recovery workflow health | LOW | Low |
| 14 | Security | API rate-limit trigger count | DDoS protection effectiveness | MEDIUM | Low |
| 15 | Performance | API response degradation during peak hours | Scaling planning | HIGH | Low |
| 16 | Performance | Frontend first-paint vs. full-interactive delta | Perceived performance gap | MEDIUM | Medium |
| 17 | Performance | Asset weight per page (KB) | Mobile/rural bandwidth optimization | MEDIUM | Low |
| 18 | Staff Equity | Teacher child-count Gini coefficient | Fair workload distribution | MEDIUM | Medium |
| 19 | Staff Equity | Overtime hours per staff member | Staff welfare + compliance | MEDIUM | Low |
| 20 | Staff Equity | Training completion variance | Training equity | MEDIUM | Low |
| 21 | Governance | Report rejection rate and first-pass return rate | Supervision quality | HIGH | Low |
| 22 | Governance | Governance trend per governorate | Regional equity monitoring | MEDIUM | Medium |
| 23 | Network Effect | Inter-KG best-practice adoption rate | Organizational learning | LOW | High |
| 24 | Network Effect | Cross-KG admin workload balance | Admin scaling | MEDIUM | Medium |
| 25 | Cost | Platform cost per child per month | Unit economics | MEDIUM | Low |
| 26 | Cost | Cost per KG per month | Cost center analysis | MEDIUM | Low |
| 27 | Adoption | Feature usage frequency by role | Product roadmap prioritization | HIGH | Medium |
| 28 | Adoption | Feature abandonment rate | UX friction detection | MEDIUM | Medium |
| 29 | Engagement | Parent portal session duration | Engagement depth | MEDIUM | Low |
| 30 | Engagement | Parent referral rate (word-of-mouth signal) | Organic growth | LOW | High |
| 31 | Seasonality | Seasonal attendance deviation index | Ramadan/holiday planning | MEDIUM | Medium |
| 32 | Seasonality | Seasonal incident patterns | Resource allocation | LOW | Medium |
| 33 | Enrollment Funnel | Drop-off rate at each enrollment stage | Conversion optimization | HIGH | Medium |
| 34 | Enrollment Funnel | Time from application to acceptance | Enrollment speed | MEDIUM | Low |
| 35 | Enrollment Funnel | Waitlist conversion rate | Capacity matching | MEDIUM | Low |

### 9.3 Top 10 Highest-Priority Missing Indicators

Ranks by decision impact × implementation effort inverse:

| Rank | Metric | Impact | Effort | Recommendation |
|------|--------|--------|--------|----------------|
| 1 | Per-KG report age | Silent data lag undetected for days | Days | Implement immediately |
| 2 | Alert signal-to-noise | Alert fatigue → critical events missed | Days | Implement immediately |
| 3 | Teacher workload Gini | Burnout + equity + MoSD compliance | Days | High-priority Wave 2 |
| 4 | Report rejection rate | Quality signal for supervision | Days | High-priority Wave 2 |
| 5 | Enrollment funnel drop-off | Revenue/retention impact | Days | High-priority Wave 2 |
| 6 | Time-to-first-dashboard-action | UX information architecture | Weeks | Medium-priority Wave 3 |
| 7 | Feature adoption depth | Product investment alignment | Weeks | Medium-priority Wave 3 |
| 8 | Morning routine completion | Operational readiness signal | Weeks | Medium-priority Wave 3 |
| 9 | Asset weight per page | Mobile/rural performance | Days | Medium-priority Wave 2 |
| 10 | Seasonal attendance deviation | Ramadan/holiday pattern | Weeks | Low-priority Wave 4 |

---

## 10. Proposed New Metrics

### 10.1 New Metrics Catalog (24 Total)

| ID | Metric | Formula | Purpose | Data Source | Frequency | Target | Critical | Dashboard |
|----|--------|---------|---------|-------------|-----------|--------|----------|-----------|
| NEW-01 | **Data Freshness Latency** | `now() - max(DailyReport.date)` per KG | Silent lag detection | `daily_reports` | 15 min | < 2h | > 6h | Per-KG gauge |
| NEW-02 | **Data Completeness Score** | `COUNT(present_records) / COUNT(expected_records)` | Expected vs. actual records | All domain tables | Hourly | ≥ 0.98 | < 0.90 | Network dashboard |
| NEW-03 | **Data Accuracy Rate** | `valid_records / sampled_records` | Validation pass rate | `validators.py` checks | Daily | ≥ 0.99 | < 0.95 | Quality tab |
| NEW-04 | **Uniqueness Score** | `1 - duplicates / critical_records` | Duplicate prevention | Unique constraint audit | Daily | 1.00 | < 0.99 | Quality tab |
| NEW-05 | **Cross-Entity Consistency** | `consistent_pairs / total_pairs` | Cross-table reconciliation | Child/Enrollment/Attendance | Daily | ≥ 0.97 | < 0.90 | Quality tab |
| NEW-06 | **Alert Signal-to-Noise** | `count(critical+high) / count(total_alerts)` | Alert quality | `active_alerts` | Weekly | ≥ 0.60 | < 0.40 | Admin dashboard |
| NEW-07 | **Alert False Positive Rate** | `unactioned_alerts / total_alerts` | False positive trend | `active_alerts`, acknowledgment | Weekly | ≤ 0.10 | > 0.25 | Admin dashboard |
| NEW-08 | **Teacher Workload Gini** | Gini coefficient of `enrolled_children_count` per teacher per KG | Workload equity | `supervisor_assignments`, `children` | Weekly | ≤ 0.25 | > 0.40 | Staff equity tab |
| NEW-09 | **Overdue Task Count** | `COUNT(due_date < now() AND status ≠ DONE)` | Operational discipline | `tasks` | Real-time | 0 | > 3 per user | Per-role dashboard |
| NEW-10 | **Report Rejection Rate** | `REJECTED / SUBMITTED` | Supervision quality | `daily_reports` | Daily | ≤ 0.05 | > 0.15 | Governance tab |
| NEW-11 | **Report First-Pass Approval** | `APPROVED_first_try / SUBMITTED` | Report training signal | `daily_reports` | Daily | ≥ 0.90 | < 0.70 | Governance tab |
| NEW-12 | **Enrollment Funnel Drop-off** | Per-stage drop rate | Enrollment conversion | `enrollment_applications` | Weekly | ≤ 0.10/stage | > 0.25/stage | Enrollment tab |
| NEW-13 | **Enrollment Turnaround** | `ACCEPTED_time - SUBMITTED_time` | Enrollment processing speed | `enrollment_applications` | Daily | < 48h | > 72h | Enrollment tab |
| NEW-14 | **Waitlist Conversion Rate** | `waitlist_accepted / waitlist_offered` | Capacity utilization | `waitlist_entries` | Weekly | ≥ 0.70 | < 0.50 | Enrollment tab |
| NEW-15 | **Morning Routine Completion** | `managers_completed_morning_tasks / total_managers` | Daily operational readiness | `tasks`, `user_activity` | Daily | ≥ 0.85 | < 0.70 | Network dashboard |
| NEW-16 | **Notification-to-View Conversion** | `DailyReportViews / NotificationsSent` | Notification effectiveness | `daily_report_views`, `notifications` | Weekly | ≥ 0.70 | < 0.40 | Parent tab |
| NEW-17 | **Notification-to-Action Conversion** | `actions_taken / relevant_notifications` | CTA effectiveness | `absence_requests`, `messages` | Weekly | ≥ 0.30 | < 0.15 | Parent tab |
| NEW-18 | **Parent Session Duration** | `session_end - session_start` (median) | Engagement depth | Telemetry events | Weekly | ≥ 5 min | < 1 min | Parent tab |
| NEW-19 | **NPS Trajectory** | Rolling 30-day avg of NPS | Satisfaction trend over time | `surveys` | Weekly | Increasing | Decreasing > 5pts | Parent tab |
| NEW-20 | **Attendance Volatility Index** | `std(7d_rolling_avg)` per KG | Early warning for KG decline | `attendance_logs` | Daily | ≤ 0.03 | > 0.08 | Per-KG tab |
| NEW-21 | **Seasonal Attendance Deviation** | `attendance_rate - seasonal_baseline_rate` | Ramadan/holiday impact | `attendance_logs`, historical | Weekly | Within ±5% of baseline | > ±15% | Network dashboard |
| NEW-22 | **Feature Adoption Depth** | `users_completing_workflow / users_starting_workflow` | Feature value | Telemetry events | Weekly | ≥ 0.50 | < 0.20 | Product tab |
| NEW-23 | **Daily Report Submission Pattern** | Distribution of submission times | Workflow pattern analysis | `daily_reports` | Daily | Peak 7–9 AM | Scattered > 3σ | Governance tab |
| NEW-24 | **Overtime Hours per Staff** | `sum(overtime_hours) / active_staff` | Staff welfare + compliance | `staff_presence_logs` | Weekly | ≤ 2h | ≥ 5h | Staff equity tab |

### 10.2 Priority Ranking

| Priority Tier | Metrics | Wave |
|---------------|---------|------|
| **Wave 1 (Weeks 1-4)** | NEW-01, NEW-02, NEW-06, NEW-09, NEW-15, FE01-05, BE01-03 | Foundation |
| **Wave 2 (Weeks 5-8)** | NEW-03, NEW-04, NEW-05, NEW-08, NEW-10, NEW-11, NEW-12, NEW-13 | Quality + Governance |
| **Wave 3 (Weeks 9-12)** | NEW-07, NEW-16, NEW-17, NEW-18, NEW-19, NEW-20, NEW-22 | Engagement + Analytics |
| **Wave 4 (Weeks 13-16)** | NEW-14, NEW-21, NEW-23, NEW-24 | Predictive + Maturity |

---

## 11. Correlation and Deep-Dive Methodology

### 11.1 Discovery Protocol — Three-Stage Process

#### Stage 1: Automated Pairwise Scan (Weekly Batch)

```python
# Conceptual pseudocode for correlation discovery engine
# Runs weekly as Celery beat job
from scipy.stats import pearsonr, spearmanr

MIN_SAMPLE_SIZE = 14      # Minimum 14 data points
SIGNIFICANCE_THRESHOLD = 0.05
EFFECT_SIZE_THRESHOLD = 0.5  # Medium effect size

def discover_correlations(db_session, period_days=90):
    """Scan all numeric metric pairs for statistically significant correlations."""
    metrics = load_all_numeric_metrics(db_session, period_days)

    flagged = []
    for i, (metric_a_name, metric_a_values) in enumerate(metrics):
        for metric_b_name, metric_b_values in metrics[i+1:]:
            if len(metric_a_values) < MIN_SAMPLE_SIZE:
                confidence = "insufficient"
                continue

            # Pearson (linear relationship)
            r_pearson, p_pearson = pearsonr(metric_a_values, metric_b_values)

            # Spearman (rank-based, robust to outliers)
            r_spearman, p_spearman = spearmanr(metric_a_values, metric_b_values)

            # Flag if significant and medium+ effect size
            if (abs(r_spearman) >= EFFECT_SIZE_THRESHOLD and
                p_spearman < SIGNIFICANCE_THRESHOLD):
                flagged.append({
                    'metric_a': metric_a_name,
                    'metric_b': metric_b_name,
                    'pearson_r': r_pearson,
                    'pearson_p': p_pearson,
                    'spearman_rho': r_spearman,
                    'spearman_p': p_spearman,
                    'sample_size': len(metric_a_values),
                    'confidence': 'high' if p_spearman < 0.01 else 'medium',
                    'correlation_strength': interpret_strength(abs(r_spearman))
                })

    return sort_by_abs_rho_desc(flagged)

def interpret_strength(rho):
    if rho >= 0.7: return 'strong'
    if rho >= 0.5: return 'medium'
    if rho >= 0.3: return 'weak'
    return 'negligible'
```

#### Stage 2: Domain-Filter (Manual Review)

Remove spurious correlations by checking:

| Filter | Question | Example |
|--------|----------|---------|
| **Trivial Correlation** | Does the correlation have a definitional relationship? | Total children ↔ Total teachers (trivially correlated) |
| **Seasonal Confound** | Are both series driven by same seasonal factor? | Weekday ↔ Report submission time |
| **Unit Conversion** | Are both metrics bounded the same way? | attendance_rate ↔ incident_rate (both 0-1) |
| **Common Denominator** | Do both metrics share a denominator? | Per-child metrics naturally correlate via child count |

#### Stage 3: Causal Probes

For each domain-filtered pair, apply appropriate causal analysis:

| Test | When to Apply | Output | Required Sample Size |
|------|--------------|--------|--------------------|
| **Pearson/Spearman Correlation** | Continuous metrics | Correlation coefficient + p-value | ≥ 14 points |
| **Partial Correlation** | Suspected confounder | Correlation holding confounder constant | ≥ 20 points |
| **Lagged Cross-Correlation** | Time-series pairs | Lag at which correlation is strongest → temporal ordering | ≥ 30 points |
| **Granger Causality** | One variable predicts another | Statistical causation test (X causes Y?) | ≥ 60 points (2 months daily) |
| **Logistic Regression** | Binary outcome (e.g., incident occurred) | Odds ratios per predictor | ≥ 50 events + 50 non-events |
| **Cohort Analysis** | Categorical grouping | Differences in distribution per cohort | ≥ 30 per cohort |
| **Multiple Linear Regression** | Multiple continuous predictors | Coefficients + R² + Variance Inflation Factor | ≥ 50 observations × k predictors |
| **Time-Series Decomposition (STL)** | Seasonal patterns | Seasonal, trend, residual components | ≥ 1 year of daily data |

### 11.2 Specific Correlation Hypotheses

These are the expected/interesting correlations to validate against KinJo data:

| # | Hypothesis | Direction | Strength | Test | Decision Action |
|---|-----------|-----------|----------|------|-----------------|
| C01 | Teacher-child ratio ↑ → Incident rate ↓ | Negative | Medium | Pearson r, lag 1 day | Staffing thresholds per KG |
| C02 | Attendance rate ↑ → Report quality ↑ | Positive | Medium | Partial correlation (control KG size) | Training targeting |
| C03 | Governorate type → Incident severity level | Mixed (categorical) | Strong | Kruskal-Wallis + Dunn's | Regional safety interventions |
| C04 | Peak load hour → API p95 latency | Positive | Strong | Pearson r (hourly bucketing) | Auto-scaling triggers |
| C05 | LCP > 4s → Page abandonment rate ↑ | Positive | Medium | Logistic regression | Frontend optimization priority list |
| C06 | Alert volume > threshold → Manager response time ↑ | Positive | Strong | Regression with exponential decay | Alert deduplication |
| C07 | Report timeliness (morning sub) → GCEI ↑ | Positive | Medium | Multiple regression (controls) | Workflow automation for early risers |
| C08 | Training completion ↑ → Incident rate ↓ | Negative | Medium | Logistic regression, 30-day lag | Training effectiveness audit |
| C09 | Parent engagement (portal login) → Child attendance ↑ | Positive | Medium | Cohort analysis (engaged vs. not) | Parent outreach campaigns |
| C10 | Data completeness ↑ → Forecast accuracy ↑ | Positive | Medium | Time-series forecasting comparison | Data quality investment ROI |

### 11.3 Correlation Matrix Dashboard Component

```
Correlation Explorer — Insights Panel

         | Att  | Inc  | Rat  | Cap  | Trn  | Rep  | GCEI | Frq  | SNR
─────────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────┼──────
Attendance| 1.00 |      |      |      |      |      |      |      |
IncRate   | -0.58| 1.00 |      |      |      |      |      |      |
Ratio     |  0.42 | -0.71| 1.00 |      |      |      |      |      |
Capacity  |  0.15 |  0.33 |  0.21| 1.00 |      |      |      |      |
Training  |  0.08 | -0.45|  0.31| -0.02| 1.00 |      |      |      |
Report    |  0.62 | -0.38|  0.28|  0.11|  0.55| 1.00 |      |      |
GCEI      |  0.77 | -0.62|  0.84|  0.23|  0.41|  0.68| 1.00 |      |
Freshness |  0.34 | -0.12|  0.22|  0.08|  0.18|  0.55|  0.41| 1.00 |
AlertSNR  | -0.23|  0.45| -0.34| -0.05| -0.21| -0.38| -0.47| -0.15| 1.00

Legend:
  ● Strong positive (>0.5)  ● Strong negative (<-0.5)
  ● Medium (0.3-0.5)        ● Weak (<0.3)
  ○ Not significant (p > 0.05)
```

Click any cell → reveals scatter plot with regression line, p-value, and sample size.

---

## 12. Scientific Validation Framework

### 12.1 Data Quality Dimensions (6-Dimension Model)

| Dimension | What It Measures | Check Method | Failure Action |
|-----------|-----------------|--------------|----------------|
| **Accuracy** | Records reflect real-world ground truth | Random 5% weekly sample audit vs. source system | Flag metric; manual audit; delay publication |
| **Completeness** | All expected records are present | NULL rate + expected-record counting per KG/day | Data quality alert; investigation |
| **Timeliness** | Data is current when consumed | Event_time → DB_time → Dashboard_time latency chain | Alert if latency > per-metric threshold |
| **Consistency** | Same data in same state across stores | Cross-query reconciliation (Child count vs Enrollment count) | Investigation; resolution SLA |
| **Uniqueness** | No duplicates in critical-key fields | Unique constraint audit (attendance_logs child_id + date) | Auto-cleanup workflow |
| **Validity** | Values within expected ranges | Range assertions + enum checks | Reject at API layer; log anomaly |

### 12.2 Metric Validation Protocol (Scientific Method)

Every new metric must pass this validation protocol before dashboard deployment:

```
PHASE 1: DEFINITION VALIDATION
────────────────────────────────────────────────────────────
□ Formula documented with clear operational definition
□ Decision-to-action mapping specified
□ Owner role identified (single responsible role)
□ Sample size requirements defined (minimum n)
□ Thresholds justified with benchmarks (Section 13)
□ Confidence intervals specified (95% / 99%)
□ Data source verified (no circular dependencies)
□ No PII in the metric output

PHASE 2: STATISTICAL VALIDATION
────────────────────────────────────────────────────────────
□ Minimum sample size met at operational frequency
□ Distribution analyzed (normal/skewed/multi-modal)
□ Outlier treatment specified (Winsorize? Tukey? Log?)
□ Confidence interval computed
□ Hypothesis test performed against null hypothesis
□ Effect size reported (Cohen's d, r, or equivalent)
□ Statistical significance (p < 0.05) documented

PHASE 3: OPERATIONAL VALIDATION
────────────────────────────────────────────────────────────
□ Back-tested against at least 1 month of historical data
□ Seasonality decomposed and documented
□ Trend decomposition documented
□ Anomaly sensitivity tested (z-score threshold check)
□ Dashboard performance tested (page load < 3s with metric)
□ Bilingual display validated (ar + en, RTL)
□ Edge case handling tested (div-by-zero, null, empty set)

PHASE 4: GOVERNANCE VALIDATION
────────────────────────────────────────────────────────────
□ Privacy review passed (no PII leakage)
□ Security review passed (idempotent, rate-limited)
□ Accessibility review passed (WCAG AA, color-blind safe)
□ SLA defined (update frequency, availability)
□ Incident response plan documented
```

### 12.3 Statistical Protocols — Implementation

#### A. Baseline Establishment (30-Day Rolling EWMA)

```python
def establish_baseline(values, span=30):
    """
    Exponentially Weighted Moving Average baseline.
    Used to establish expected value for each metric.
    """
    import pandas as pd
    ewma = pd.Series(values).ewm(span=span, adjust=False).mean()
    rolling_std = pd.Series(values).rolling(span).std()

    baseline = ewma.iloc[-1]
    upper = baseline + 1.96 * rolling_std.iloc[-1]
    lower = baseline - 1.96 * rolling_std.iloc[-1]

    return {
        'baseline': baseline,
        'ci_95_upper': upper,
        'ci_95_lower': lower,
        'std_30d': rolling_std.iloc[-1]
    }
```

#### B. Significance Testing

```python
def test_significance(current_value, baseline, std, alpha=0.05):
    """
    Test if a metric value differs significantly from baseline.
    Uses one-sample t-test logic for simplicity.
    """
    from scipy.stats import t as t_distribution

    # H0: value = baseline (no change)
    # H1: value ≠ baseline (significant change)

    if std == 0:
        return {'significant': False, 'effect_size': 0, 'message': 'zero variance'}

    t_stat = (current_value - baseline) / std
    df = n - 1  # n = sample size for this metric
    critical_t = t_distribution.ppf(1 - alpha/2, df)

    # Effect size (Cohen's d)
    cohen_d = (current_value - baseline) / std

    return {
        'significant': abs(t_stat) > critical_t,
        't_statistic': t_stat,
        'cohen_d': cohen_d,
        'effect_magnitude': interpret_cohen_d(cohen_d)
    }

def interpret_cohen_d(d):
    if abs(d) < 0.2: return 'negligible'
    if abs(d) < 0.5: return 'small'
    if abs(d) < 0.8: return 'medium'
    return 'large'
```

#### C. Outlier Treatment

```python
def detect_outliers(values, method='tukey'):
    """
    Detect outliers using Tukey's fences or z-score method.
    Winsorize outliers rather than dropping them.
    """
    if method == 'tukey':
        q1, q3 = np.percentile(values, [25, 75])
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        winsorized = np.clip(values, lower_fence, upper_fence)
    else:
        mean = np.mean(values)
        std = np.std(values)
        lower_fence = mean - 3 * std
        upper_fence = mean + 3 * std
        winsorized = np.clip(values, lower_fence, upper_fence)

    return {
        'clean_values': winsorized,
        'outlier_count': sum(np.array(values) != winsorized),
        'p5': np.percentile(values, 5),
        'p95': np.percentile(values, 95)
    }
```

#### D. Seasonal Decomposition

```python
def decompose_time_series(values, period=7, frequency='daily'):
    """
    Decompose time series into trend, seasonal, and residual components.
    Use STL decomposition for robustness to missing values.
    """
    from statsmodels.tsa.seasonal import STL

    series = pd.Series(values)

    if period <= 1 or len(series) < 2 * period:
        return {
            'trend': series,
            'seasonal': pd.Series([0] * len(series)),
            'residual': pd.Series([0] * len(series)),
            'seasonally_adjusted': series
        }

    stl = STL(series, period=period, robust=True)
    result = stl.fit()

    return {
        'trend': result.trend,
        'seasonal': result.seasonal,
        'residual': result.resid,
        'seasonally_adjusted': series - result.seasonal
    }
```

### 12.4 Validation Cadence

| Validation | Frequency | Performed By | Deliverable |
|------------|-----------|-------------|-------------|
| Data quality checks | Hourly (automated) | System → Admin alert | Quality score per metric |
| Metric accuracy audit | Weekly (random sample) | QA Engineer → Data Scientist | Accuracy report |
| Baseline refresh | Monthly | Data Scientist | Updated baselines + CI |
| Threshold review | Quarterly | Admin + Data Scientist | Threshold calibration report |
| Full statistical validation | On new metric + quarterly | Data Scientist + QA | Validation certificate |
| Privacy/security review | On new metric + quarterly | Security Engineer | Security sign-off |

---

## 13. Industry Benchmarking Framework

### 13.1 Industry Standards by Domain

| KPI | KinJo Target | Industry Benchmark | Source | Justification |
|-----|-------------|-------------------|--------|---------------|
| Attendance Rate | ≥ 90% | OECD early childhood avg: 75–85% | UNESCO Institute for Statistics | Jordan MoSD target exceeds OECD baseline |
| Staff-Child Ratio | ≤ 1:15 | Jordan MoSD: 1:15 (ages 3–5) | Royal Hashemite Court / MoSD Licensing Standards | Mandatory by Jordanian law |
| Report Submission Rate | ≥ 95% | NHS Early Years: 98% (UK) | UK EYFS Framework | Best-practice threshold |
| Incident Follow-up SLA | 100% within 48h | ITIL standard: P2 = 4h, P3 = 24h | ITIL 4 / ISO 20000 | Safety-critical; shorter than standard IT practice |
| System Availability | > 99.5% | Enterprise SaaS standard | AWS Well-Architected / Google SRE | Minimum acceptable for critical operational tool |
| Page Load (LCP) | < 2.5s | Google Core Web Vitals "Good" | Google Web Vitals | Industry standard for user experience |
| Client Error Rate | < 0.1% | Production SLO standard | Google SRE | Typical reliability threshold |
| Data Freshness | < 2 hours | Real-time analytics standard | Various SaaS platforms | Business-critical data |
| DB Query p95 | < 200ms | OLTP application standard | Database performance guides | Acceptable for interactive analytics |
| Cache Hit Rate | ≥ 90% | Production caching standard | Redis/Memcached best practices | Cache must be effective |
| Background Job Failure Rate | < 1% | Async processing SLA | Message queue industry standards | High reliability for background tasks |
| Data Completeness | ≥ 98% | Enterprise data quality standard | DAMA/DMBOK | Acceptable data quality |
| Alert Signal-to-Noise | ≥ 60% critical+high | SRE alerting best practice | Google SRE / PagerDuty | Avoid alert fatigue |

### 13.2 Benchmark Comparison Methodology

```python
def benchmark_against_industry(our_value, industry_benchmark, target_value):
    """
    Compare our metric performance against industry standards.
    Returns a performance tier: world-class / competitive / needs-improvement / critical
    """
    if industry_benchmark['direction'] == 'higher_is_better':
        if our_value >= industry_benchmark['world_class']:
            return 'world-class'
        elif our_value >= target_value:
            return 'competitive'
        elif our_value >= industry_benchmark['threshold']:
            return 'needs-improvement'
        else:
            return 'critical'
    else:  # lower_is_better
        if our_value <= industry_benchmark['world_class']:
            return 'world-class'
        elif our_value <= target_value:
            return 'competitive'
        elif our_value <= industry_benchmark['threshold']:
            return 'needs-improvement'
        else:
            return 'critical'
```

### 13.3 Benchmark Storage and Update Cadence

| Industry Domain | Primary Source | Update Cadence | Responsible |
|-----------------|----------------|----------------|-------------|
| Early Childhood Education | UNESCO / OECD / MoSD Jordan | Annual | Admin + Product |
| Web Performance | Google Web Vitals / HTTP Archive | Quarterly | Engineering |
| IT Service Management | ITIL 4 / ISO 20000 | Annual | Engineering |
| Cloud Infrastructure | AWS Well-Architected / Google SRE | Quarterly | Engineering |
| Data Quality | DAMA/DMBOK | Annual | Data Science |
| Alert Management | Google SRE / PagerDuty | Quarterly | Engineering |

### 13.4 Jordanian-Specific Considerations

| Factor | Impact on Benchmark | Adaptation |
|--------|--------------------|------------|
| **Ramadan season** | Attendance patterns shift; some schools close | Seasonal adjustment applied to all attendance metrics |
| **Regional infrastructure** | Rural governorates may have connectivity issues | Offline mode support; cache longer; measure availability differently per region |
| **Arabic RTL** | UI complexity higher than LTR | RTL integrity becomes a first-class metric |
| **Regulatory compliance** | MoSD Jordan mandates specific ratios and reporting | Jordan MoSD thresholds override generic industry benchmarks |
| **Cultural context** | Parent engagement patterns differ from Western norms | NPS and engagement targets set contextually, not imported from Western benchmarks |

---

## 14. Visualization and Dashboard Strategy

### 14.1 Design Principles

All dashboards follow these principles:

| Principle | Rationale |
|-----------|-----------|
| **Action-first** | Every chart must answer "What should I do?" or trigger a specific action |
| **Progressive disclosure** | Overview → detail → micro-detail (click to drill down) |
| **Consistent color semantics** | Green = healthy; Amber = watch; Red = action; Blue = informational; Gray = no data |
| **RTL-native** | All charts render correctly in RTL; axis labels, tooltips, legends mirror |
| **WCAG AA compliant** | Color-blind safe palette; text alternatives; keyboard navigable |
| **Bilingual** | All text has Arabic and English; system language determines display |
| **Performance budget** | Dashboard must load < 3 seconds even with all metrics populated |
| **Mobile-first** | Responsive design; critical metrics visible on mobile (375px+) |

### 14.2 Color Palette (WCAG AA + Color-Blind Safe)

```
Primary Semantic Colors:
────────────────────────────────────────────────────────
Healthy (Green):     #059669 (emerald-600)
Warning (Amber):     #d97706 (amber-600)
Critical (Red):      #dc2626 (red-600)
Informational (Blue): #2563eb (blue-600)
No Data (Gray):       #64748b (slate-500)
────────────────────────────────────────────────────────

Color-Blind Safe Alternative Set:
────────────────────────────────────────────────────────
Healthy:   #2ca02c  (green, distinct in deuteranopia)
Warning:   #ff7f0e  (orange)
Critical:  #d62728  (red, distinct in protanopia)
Info:      #1f77b4  (blue)
Neutral:   #7f7f7f  (gray)
────────────────────────────────────────────────────────

Text Colors:
────────────────────────────────────────────────────────
Heading:   #1e293b (slate-800)
Body:      #334155 (slate-700)
Caption:   #64748b (slate-500)
Disabled:  #94a3b8 (slate-400)
────────────────────────────────────────────────────────

Background:
────────────────────────────────────────────────────────
Surface:   #ffffff
Card:      #ffffff with subtle shadow
Border:    #e2e8f0 (slate-200)
Hover:     #f1f5f9 (slate-50)
────────────────────────────────────────────────────────
```

### 14.3 Chart Selection Matrix

| Analysis Type | Recommended Chart | Rationale | RTL Handling |
|---------------|-------------------|-----------|--------------|
| Trend over time | **Line chart** with confidence band | Shows direction + uncertainty | Mirror time axis |
| Composition | **Stacked bar** or **treemap** | Shows parts of whole across categories | Mirror categorical axis |
| Distribution | **Box plot** or **violin plot** | Shows spread; more honest than bar | Mirror axis |
| Correlation | **Scatter plot** with regression line + R² | Makes relationship explicit | Mirror axis |
| Comparison | **Horizontal bar** (sorted) | Easy ranking; more readable than vertical | Mirror bar direction |
| Geographic | **Heatmap** (Jordan governorates) | Spatial pattern recognition | No change needed |
| Alert severity | **Donut chart** (small set) or **stacked bar** | Proportional understanding | Mirror segments |
| Forecast | **Line chart** with shaded prediction interval | Shows uncertainty | Mirror time axis |
| Health score | **Radial gauge** or **stacked bullet** | Single-glance status | Mirror arc |
| Cohort | **Sankey diagram** or **heatmap calendar** | Flow and retention | Mirror flow |
| Time distribution | **Histogram** (time of day) | Workflow timing pattern | Mirror axis |
| Ranking | **Horizontal table** with inline sparklines | Compare many entities | Mirror table columns |

### 14.4 Dashboard Hierarchy by Role

#### 14.4.1 Admin Command Center (Executive Overview)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  KINJO NETWORK COMMAND CENTER                                           │
│  [Last updated: 10:30 AM AST]  [Data freshness: 98%]                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐      │
│  │ Network     │ │ Attendance  │ │ Incidents   │ │ GCEI Score  │      │
│  │ Health IDx  │ │ Rate        │ │ /100 child  │ │ Network     │      │
│  │ 82.3        │ │ 87.4%       │ │ 0.37        │ │ 76.8        │      │
│  │ [● healthy] │ │ [● good]    │ │ [● good]    │ │ [● good]    │      │
│  │ ↑ 2.1 vs wk │ │ ↓ 1.2 vs wk │ │ ↓ 0.1 vs wk │ │ ↑ 1.5 vs wk │      │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘      │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ EXECUTIVE HEALTH BANNER (3-zone: critical / watch / healthy)      │  │
│  │ 🔴 2 KGs need attention  🟡 8 KGs trending down  🟢 45 KGs OK    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────────────────┐ ┌────────────────────────────────────┐ │
│  │ Network Attendance Trend   │ │ Incident Rate by Governorate       │ │
│  │ (7-day sparkline per KG)   │ │ (Heatmap overlay on Jordan map)    │ │
│  │ [Line chart]               │ │ [Choropleth map]                   │ │
│  └────────────────────────────┘ └────────────────────────────────────┘ │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │ KG RISK RANKING                                                     │  │
│  │ #1  KG-Name-1  [⚠]  GCEI: 42.3  Attendance: 65%  Incidents: 2.1   │  │
│  │ #2  KG-Name-2  [⚠]  GCEI: 58.8  Attendance: 72%  Incidents: 1.5   │  │
│  │ [View full table...]                                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌───────────────────┐ ┌───────────────────────────────────────────┐   │
│  │ Capacity Pressure │ │ Top Alerts (last 24h)                      │   │
│  │ Gauge per KG      │ │ 🔴 Critical: Staff absence at KG-X          │   │
│  │ [Gauges grid]     │ │ 🔴 High:     Capacity exceeded at KG-Y      │   │
│  │                   │ │ 🟡 Medium:   Report late at KG-Z             │   │
│  └───────────────────┘ └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

**Scan time:** < 10 seconds for all critical information
**Actionable items:** 3 zones (critical/watch/healthy) with clear next actions per zone

#### 14.4.2 Manager Dashboard (Per Kindergarden)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  KINDERGARTEN: [Name] | Governorate: [Gov] | Manager: [Name]           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐        │
│  │ GCEI  │ │Attend │ │Ratio  │ │Report │ │Overdue│ │Enroll │        │
│  │Score  │ │Rate   │ │Compl  │ │Compl  │ │Tasks  │ │Growth │        │
│  └───────┘ └───────┘ └───────┘ └───────┘ └───────┘ └───────┘        │
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Attendance Trend (30d)      │ │ Incidents Trend (30d)              ││
│  │ [Line chart + 7d MA]        │ │ [Bar chart + threshold line]       ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Capacity by Class (Donut)   │ │ Teacher Workload (Gini indicator)  ││
│  │ [Per-class occupancy ring]  │ │ [Lorenz curve + Gini coef]         ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Age Group Distribution      │ │ Recent Activities Timeline          ││
│  │ [Stacked bar by age]        │ │ [Timeline with incident markers]    ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ ACTION ITEMS QUEUE                                                  ││
│  │ 🔴 P1: 2 overdue tasks need assignment       [Respond →]          ││
│  │ 🔴 P1: 1 parent complaint unanswered          [Respond →]          ││
│  │ 🟡 P2: 3 children with 7+ day absence        [Contact parents →]   ││
│  └────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 14.4.3 Supervisor Dashboard (Per Class)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  SUPERVISOR: [Name] | Class: [Class Name] | KG: [KG Name]               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Today's Attendance           │ │ Safety Observations                 ││
│  │ [Checklist + count bar]     │ │ [Incident log + trend]              ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Daily Report Status          │ │ Absence Requests Queue             ││
│  │ [Workflow progress bar]      │ │ [Pending/Approved/Rejected list]   ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Children's Learning           │ │ Communication Inbox                 ││
│  │ [Observation grid]           │ │ [Messages from parents]            ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 14.4.4 Parent Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  PARENT: [Name] | Child: [Child Name] | KG: [KG Name]                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐│
│  │ CHILD PROFILE CARD                                                  ││
│  │ Photo | Name | Age | Class | Attendance (last 7 days)               ││
│  └────────────────────────────────────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Daily Reports                │ │ Upcoming Events                    ││
│  │ [List of recent reports]    │ │ [Calendar with events + holidays]  ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Child's Learning Portfolio   │ │ Health & Incidents                  ││
│  │ [Observations + milestones]  │ │ [Health alerts + incident log]     ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
│                                                                         │
│  ┌─────────────────────────────┐ ┌────────────────────────────────────┐│
│  │ Absence Requests            │ │ Messages from KG                    ││
│  │ [Submit/request status]     │ │ [Inbox with read/unread]           ││
│  └─────────────────────────────┘ └────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
```

#### 14.4.5 Engineering Monitoring Dashboard

```
┌─────────────────────────────────────────────────────────────────────────┐
│  KINJO ENGINEERING COMMAND CENTER                                        │
│  [Error budget remaining: 62% | Uptime: 99.71% | Incidents: 0]          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ Web Vitals (p95)              │ │ API Latency (p95) per endpoint     │
│  │ LCP: 1.8s ✅ | FID: 45ms ✅  │ │ [Horizontal bars with thresholds]  │
│  │ CLS: 0.04 ✅ | INP: 120ms ✅ │ │                                    │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ Error Budget Burn             │ │ Client Error Trend                 │
│  │ [Burn rate chart]             │ │ [JS errors over time + top stacks] │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ Database Saturation           │ │ Cache Effectiveness                │
│  │ Connections / max: 38/100     │ │ Hit rate: 94.2% ✅                 │
│  │ Query p95: 178ms ✅           │ │ Eviction rate: 0.2/min ✅          │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐
│  │ BACKGROUND JOBS RELIABILITY                                         │
│  │ Success rate: 99.8%  |  Queue depth: 3  |  Avg duration: 450ms     │
│  └────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

#### 14.4.6 Executive Dashboard (Ministry View)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  JORDAN EARLY CHILDHOOD EDUCATION NETWORK                                │
│  Ministry of Social Development — National Overview                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ National Coverage              │ │ National Health Index              │
│  │ KGs: 55 active                │ │ 78.3 (World Class)                 │
│  │ Children: 2,847               │ │ ↑ 3.2 vs last quarter              │
│  │ Governorates: 12/12           │ │                                    │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ Governorate Performance Map   │ │ National Trends (12 months)        │
│  │ [Jordan choropleth map]       │ │ [Multi-metric line chart]          │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌───────────────────────────────┐ ┌───────────────────────────────────┐
│  │ Top Performing KGs            │ │ KGs Requiring Intervention        │
│  │ [Top 5 GCEI ranking]          │ │ [Bottom 5 GCEI + specific issues]  │
│  └───────────────────────────────┘ └───────────────────────────────────┘
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────────┐
│  │ GOVERNORATE RISK MATRIX                                              │
│  │ Amman: ✅ Low  Zarqa: ✅ Low  Irbid: ⚠️ Medium  Mafraq: 🔴 High     │
│  └────────────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────────────┘
```

### 14.5 RTL Layout Specifications

All dashboards support RTL with automatic mirroring:

| Element | LTR Behavior | RTL Behavior |
|---------|--------------|--------------|
| Text alignment | Left-aligned | Right-aligned |
| Icons + labels | Icon on left | Icon on right |
| Bar charts | Bars grow left → right | Bars grow right → left |
| Line charts | Left = older, Right = newer | Right = older, Left = newer |
| Heatmaps | X-axis left → right | X-axis right → left |
| Progress bars | Fill left → right | Fill right → left |

Implementation: All charts use `Plotly.js` with RTL configuration:

```javascript
function applyRTLToChart(chartElement) {
  if (document.documentElement.dir === 'rtl') {
    Plotly.relayout(chartElement, {
      'xaxis.direction': 'reversed',
      'xaxis.rangemode': 'tozero',
      'yaxis.automargin': true
    });
  }
}
```

### 14.6 Accessibility Requirements

| Requirement | Implementation | Test Method |
|-------------|----------------|-------------|
| **WCAG AA contrast** | All text ≥ 4.5:1 contrast ratio | Automated: axe-core |
| **Color-blind safe** | Never rely on color alone; always paired with shape/label | Manual review |
| **Keyboard navigation** | All interactive dashboard elements keyboard accessible | Tab key test |
| **Screen reader support** | All charts have `aria-label` + data table alternative | NVDA/VoiceOver test |
| **Focus indicators** | Visible focus ring on all interactive elements | Keyboard test |
| **Reduced motion** | Respect `prefers-reduced-motion` media query | OS settings test |
| **Text resizing** | All text scales up to 200% without breaking layout | Browser zoom test |

---

## 15. Data Governance Model

### 15.1 Metric Lifecycle Ownership

| Role | Responsibilities | Cadence |
|------|-----------------|---------|
| **Metric Owner** (Admin/Manager) | Decision mapping; threshold review; action follow-up | Ongoing |
| **Data Scientist** | Formula specification; statistical validation; correlation analysis | Weekly |
| **Analytics Engineer** | Implementation; data pipeline; performance; caching | Ongoing |
| **Frontend Engineer** | Visualization; dashboard implementation; RTL/internationalization | Ongoing |
| **QA Engineer** | Validation testing; accessibility testing; regression testing | Per release |
| **Security Engineer** | Privacy review; RBAC; audit logging; threat modeling | Per new metric |
| **Product Manager** | Roadmap prioritization; stakeholder feedback; metric retirement decisions | Quarterly |

### 15.2 Metric Versioning

Every metric has a version and changelog:

```json
{
  "metric_id": "NEW-01",
  "name": "Data Freshness Latency",
  "version": "1.0.0",
  "status": "active",
  "changelog": [
    {
      "version": "1.0.0",
      "date": "2026-06-24",
      "author": "data-science-team",
      "changes": ["Initial definition"],
      "approved_by": ["admin", "engineering-lead"]
    }
  ],
  "formula": "now() - max(DailyReport.date) per KG",
  "data_source": "daily_reports",
  "owner_role": "ADMIN",
  "frequency": "15min",
  "threshold": {"warning": "6h", "critical": "12h"},
  "validation_status": "passed",
  "last_validated": "2026-06-24"
}
```

### 15.3 Data Quality SLAs

| Requirement | SLA | Measured By | Breach Response |
|-------------|-----|-------------|-----------------|
| **Data availability** | 99.5% uptime | System monitoring | Auto-scaling + incident |
| **Data latency** | < 15 minutes end-to-end | Data freshness metric | Infrastructure review |
| **Data accuracy** | ≥ 99% valid records | Accuracy audit | Investigation + fix |
| **Data completeness** | ≥ 98% complete | Completeness metric | Automatic alert + cleanup |
| **Metric dashboard load** | < 3 seconds | Frontend LCP | Performance investigation |
| **Report generation** | < 10 seconds | Backend duration | Optimization required |
| **Prediction response** | < 5 seconds | Backend duration | Cache warming required |

### 15.4 Data Retention

| Data Type | Hot (Redis) | Warm (PostgreSQL) | Cold (Archive) |
|-----------|-------------|-------------------|----------------|
| **Raw event telemetry** | — | 90 days | 5 years (compressed) |
| **Aggregated metrics** | 7 days | 2 years | Indefinitely |
| **Predictions & forecasts** | 24 hours | 90 days | 2 years |
| **Anomaly alerts** | 7 days | 1 year | 5 years |
| **Active alerts** | Real-time | Until resolved + 90 days | — |
| **KPI historical values** | 30 days | 5 years | Indefinitely |
| **Correlation results** | 7 days | 2 years | Indefinitely |
| **Error reports** | 24 hours | 1 year | — |

### 15.5 Privacy & Security

| Control | Implementation | Owner |
|---------|----------------|-------|
| **Role-based data scope** | Each role sees only data within their authorization | Auth service |
| **Data minimization** | No PII in metric outputs; no child health data in analytics | Data Science |
| **Anonymization** | Parent engagement metrics are aggregate-only | Product |
| **Telemetry anonymization** | Session IDs hashed; no query params; no file paths | Engineering |
| **Encryption in transit** | All telemetry uses HTTPS | Engineering |
| **Encryption at rest** | PostgreSQL + Redis with encryption enabled | Infrastructure |
| **Audit logging** | All metric changes logged to `audit_logs` | Security |
| **PII leak detection** | Automated scan for names, DOBs, health data on export | Security |
| **Consent tracking** | Parents can opt out of non-essential data collection | Product |
| **Retention compliance** | Automated data purge per retention schedule | Engineering |

### 15.6 Metric Retirement Process

When a metric is identified for retirement:

1. **Deprecate announcement** — 30-day warning to all users, with migration guidance
2. **Dashboard removal** — Remove from all dashboards and exports
3. **API deprecate** — Add `deprecated=true` flag; 90-day sunset period
4. **Final removal** — Remove endpoint; keep metric definition frozen in audit log
5. **Knowledge base update** — Update KPI documentation and user guides

---

## 16. Testing and QA Strategy

### 16.1 Test Pyramid

```
                    /\
                   /  \
                 /  E2E  \          5%  — End-to-end user flows
                /──────────\
               / Integration \       15% — API + service integration
              /────────────────\
             /   Unit Tests    \     80% — Metric formulas, calculations, validation
            /────────────────────\
```

### 16.2 Test Categories

| Category | Scope | Example Tests | Cadence |
|----------|-------|---------------|---------|
| **Unit Tests** | Metric formula correctness | Test GCEI calculation with known input; verify z-score anomaly detection | Every commit |
| **Unit Tests** | Edge cases | Division by zero; empty dataset; all-null records | Every commit |
| **Unit Tests** | Threshold classification | Verify band assignment (green/amber/red) | Every commit |
| **Unit Tests** | Statistical methods | Correlation calculation; significance test; seasonal decomposition | Weekly |
| **Integration Tests** | Metric computation pipeline | Test compute → store → retrieve → display round-trip | Every commit |
| **Integration Tests** | Cache hit/miss paths | Ensure metrics use cache when available | Every deploy |
| **Integration Tests** | RBAC enforcement | Each role sees only authorized scope | Every commit |
| **Regression Tests** | Metric value stability | Ensure new code doesn't unexpectedly change metric values | Every deploy |
| **Regression Tests** | Dashboard correctness | Verify dashboard displays metric values correctly | Every deploy |
| **E2E Tests** | Full user flows | Admin logs in → views network dashboard → drills to KG | Weekly |
| **E2E Tests** | RTL layout correctness | Arabic UI renders correctly, all charts mirror | Weekly |
| **Accessibility Tests** | WCAG AA compliance | All charts have aria-labels; keyboard navigation works | Weekly |
| **Performance Tests** | Dashboard load time | Dashboard loads < 3s under production-like data | Weekly |
| **Security Tests** | No PII in telemetry | Verify no child names, DOBs in any frontend telemetry | Weekly |
| **Data Quality Tests** | Expected-record checks | All expected records present per KG per day | Daily |
| **Data Quality Tests** | Cross-table reconciliation | Child count matches Enrollment + Attendance counts | Daily |

### 16.3 Test Implementation — Key Examples

#### Unit Test: GCEI Calculation

```python
# tests/test_kpi_gcei.py
import pytest
from kpi_service import KPIService

class TestGCEICalculation:
    @pytest.fixture
    def kpi_service(self, db_session):
        return KPIService(db_session)

    def test_gcei_perfect_governance_perfect_child_experience(self, kpi_service):
        """GCEI = 60% governance + 40% child experience. Verify calculation."""
        governance_score = 100
        child_experience = 100
        result = kpi_service._calculate_gcei(governance_score, child_experience)
        assert result == 100.0

    def test_gcei_mixed_scores(self, kpi_service):
        governance_score = 80  # Good
        child_experience = 60  # Needs improvement
        result = kpi_service._calculate_gcei(governance_score, child_experience)
        # 60% × 80 + 40% × 60 = 48 + 24 = 72
        assert result == 72.0

    def test_gcei_zero_scores(self, kpi_service):
        result = kpi_service._calculate_gcei(0, 0)
        assert result == 0.0

    def test_gcei_band_classification(self, kpi_service):
        assert kpi_service._classify_gcei(85) == 'green'
        assert kpi_service._classify_gcei(70) == 'amber'
        assert kpi_service._classify_gcei(45) == 'red'

    def test_gcei_insufficient_data_handling(self, kpi_service):
        """When data coverage < MIN_COVERAGE, band = insufficient_data."""
        # Mock with minimal data coverage
        result = kpi_service._calculate_gcei_with_coverage(
            governance_score=90,
            child_experience=80,
            data_coverage=0.3  # Below MIN_COVERAGE_FOR_RATING
        )
        assert result['band'] == 'insufficient_data'
```

#### Unit Test: Z-Score Anomaly Detection

```python
# tests/test_anomaly_detection.py
import pytest
from analytics_domain import z_score_anomalies

class TestZScoreAnomalyDetection:
    def test_no_anomaly_in_normal_data(self):
        """All values within 2 standard deviations of mean."""
        data = [10, 11, 9, 10.5, 10.2, 9.8, 10.3]
        anomalies = z_score_anomalies(data, threshold=2.0)
        assert len(anomalies) == 0

    def test_detects_outlier(self):
        """One value far from mean triggers detection."""
        data = [10, 11, 9, 10.5, 10.2, 9.8, 10.3, 50]
        anomalies = z_score_anomalies(data, threshold=2.0)
        assert len(anomalies) == 1
        assert anomalies[0]['value'] == 50

    def test_handles_edge_case_empty_data(self):
        anomalies = z_score_anomalies([], threshold=2.0)
        assert anomalies == []

    def test_handles_edge_case_single_value(self):
        anomalies = z_score_anomalies([10], threshold=2.0)
        assert anomalies == []

    def test_handles_edge_case_identical_values(self):
        """All values identical — zero variance. No anomalies."""
        anomalies = z_score_anomalies([10, 10, 10], threshold=2.0)
        assert anomalies == []

    def test_threshold_sensitivity(self):
        """Lower threshold detects more anomalies."""
        data = [10, 11, 9, 15]  # 15 is mild outlier
        strict = z_score_anomalies(data, threshold=1.0)
        lenient = z_score_anomalies(data, threshold=3.0)
        assert len(strict) >= len(lenient)
```

#### RTL Visual Regression Test

```python
# tests/e2e/test_rtl_visual_regression.py
import pytest
from playwright.sync_api import sync_playwright

class TestRTLVisualRegression:
    @pytest.fixture(scope="class")
    def browser(self):
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            yield browser
            browser.close()

    @pytest.mark.parametrize("page_name,route", [
        ("admin_dashboard", "/admin/dashboard"),
        ("kpi_dashboard", "/kpi/dashboard"),
        ("manager_kpi", "/manager/kpi"),
        ("heat_map", "/admin/heatmap"),
        ("governance_reports", "/admin/governance-reports"),
    ])
    def test_arabic_page_renders_without_visual_regression(
        self, browser, page_name, route
    ):
        """Verify each critical page renders correctly in Arabic RTL."""
        context = browser.new_context(locale='ar-JO')
        page = context.new_page()
        page.goto(f"http://localhost:8000{route}")

        # Wait for full render
        page.wait_for_load_state('networkidle')

        # Force Arabic language cookie
        context.add_cookies([{
            'name': 'kinjo_lang',
            'value': 'ar',
            'path': '/'
        }])
        page.reload()
        page.wait_for_load_state('networkidle')

        # Compare screenshot against baseline
        # First run: create baseline. Subsequent: diff against baseline.
        screenshot = page.screenshot()
        baseline_path = f"tests/baselines/{page_name}_ar.png"

        if os.path.exists(baseline_path):
            baseline = open(baseline_path, 'rb').read()
            diff = compute_image_diff(screenshot, baseline)
            assert diff < 0.05, f"Visual regression on {page_name}: {diff:.2%} changed"
        else:
            with open(baseline_path, 'wb') as f:
                f.write(screenshot)
            pytest.skip("Baseline created, no comparison")

        context.close()
```

#### Metric Accuracy Test

```python
# tests/test_metric_accuracy.py
import pytest
import numpy as np
from scipy.stats import pearsonr, spearmanr

class TestStatisticalAccuracy:
    """Verify statistical methods produce correct results."""

    def test_pearson_correlation_perfect_positive(self):
        x = list(range(100))
        y = list(range(100))
        r, p = pearsonr(x, y)
        assert abs(r - 1.0) < 0.001
        assert p < 0.001

    def test_pearson_correlation_perfect_negative(self):
        x = list(range(100))
        y = list(range(99, -1, -1))
        r, p = pearsonr(x, y)
        assert abs(r - (-1.0)) < 0.001
        assert p < 0.001

    def test_pearson_correlation_zero(self):
        np.random.seed(42)
        x = np.random.normal(0, 1, 1000).tolist()
        y = np.random.normal(0, 1, 1000).tolist()
        r, p = pearsonr(x, y)
        assert abs(r) < 0.1, "Expected near-zero correlation"

    def test_spearman_robust_to_outliers(self):
        x = list(range(100))
        y = list(range(100))
        # Introduce outliers
        y[0] = 1000
        y[1] = -1000
        r, p = spearmanr(x, y)
        # Spearman should remain high because it uses ranks
        assert abs(r - 1.0) < 0.1

    def test_gini_coefficient_uniform(self):
        """Equal distribution → Gini = 0."""
        values = [100, 100, 100, 100]
        gini = compute_gini(values)
        assert gini == 0.0

    def test_gini_coefficient_extreme_inequality(self):
        """One person has everything → Gini → 1.0."""
        values = [0, 0, 0, 400]
        gini = compute_gini(values)
        assert gini > 0.74  # Expected: 0.75

    def test_gini_coefficient_moderate_inequality(self):
        values = [10, 20, 30, 40]
        gini = compute_gini(values)
        assert 0.1 < gini < 0.5  # Expected: ~0.24
```

### 16.4 Test Coverage Requirements

| Component | Minimum Coverage | Critical Paths |
|-----------|-----------------|----------------|
| **Metric formulas** | 100% | Every KPI formula must have test coverage |
| **Threshold classification** | 100% | Every green/amber/red boundary tested |
| **RBAC enforcement** | 100% | Every role × every endpoint tested |
| **Anomaly detection** | 90% | Edge cases, thresholds, data quality |
| **Dashboard rendering** | 90% | Bilingual + RTL coverage |
| **API endpoints** | 85% | All CRUD operations + error paths |
| **Frontend JS** | 70% | Critical paths (login, dashboard load) |

---

## 17. Implementation Roadmap

### 17.1 Phase Overview

```
Wave 1: Foundation (Weeks 1-4)
├─ Data quality metrics (DQ01-DQ06)
├─ Alert quality metrics (Alert SNR, FPR, TTA)
├─ Frontend telemetry instrumentation (FE01-FE05)
└─ Backend telemetry (BE01-BE03)

Wave 2: Quality & Analytics (Weeks 5-8)
├─ Staff equity metrics (NEW-08)
├─ Governance quality metrics (NEW-10, NEW-11)
├─ Enrollment funnel metrics (NEW-12, NEW-13)
└─ Correlation discovery engine (Phase 1)

Wave 3: Engagement & Predictions (Weeks 9-12)
├─ Parent engagement suite (P01-P07, NEW-16-19)
├─ Predictive analytics extension (capacity projection)
├─ Correlation engine (Phase 2 — causal probes)
└─ Dashboard role-specific implementations

Wave 4: Predictive & Maturity (Weeks 13-16)
├─ Seasonal adjustment (NEW-21)
├─ Feature adoption analytics (NEW-22)
├─ Full RTL visual regression test suite
└─ Production readiness verification
```

### 17.2 Wave 1 — Foundation (Weeks 1-4)

#### Week 1-2: Data Quality Metrics

| Task | Deliverable | Owner |
|------|-------------|-------|
| Implement `data_freshness_latency` metric (NEW-01) | Service function + API endpoint + test | Analytics Eng |
| Implement `data_completeness_score` (NEW-02) | Same | Analytics Eng |
| Implement cross-entity reconciliation (NEW-05) | Daily scheduled job | Analytics Eng |
| Data quality dashboard (quality tab on admin) | Frontend component | Frontend Eng |
| Automated data quality alerts | Alert integration | Engineering |
| Unit tests for all data quality formulas | 100% coverage | QA |

#### Week 3-4: Frontend + Backend Telemetry

| Task | Deliverable | Owner |
|------|-------------|-------|
| Frontend Web Vitals collector (FE01-05) | `static/js/web_vitals_collector.js` | Frontend Eng |
| Frontend Error Monitor (FE05) | `static/js/client_error_monitor.js` | Frontend Eng |
| Backend telemetry endpoint (`/api/telemetry/vitals`, `/errors`, `/api`) | REST endpoints + DB schema | Backend Eng |
| Backend request timing extension | Middleware + structured logging | Backend Eng |
| DB query performance tracking | SQLAlchemy event listeners | Backend Eng |
| Cache service instrumentation | Hit/miss counters; stats endpoint | Backend Eng |
| Integration tests for all telemetry | Pipeline verification | QA |

**Deliverables at end of Wave 1:**
- ✅ Data quality metrics live on admin dashboard
- ✅ Frontend Web Vitals being collected and displayed
- ✅ Backend telemetry endpoint receiving and storing metrics
- ✅ Automated data quality alerts firing on breach
- ✅ Unit test coverage ≥ 90% for all new metrics

---

### 17.3 Wave 2 — Quality & Analytics (Weeks 5–8)

#### Week 5-6: Staff Equity + Governance Quality

| Task | Deliverable | Owner |
|------|-------------|-------|
| Teacher Workload Gini (NEW-08) | Service function + dashboard widget + test | Analytics Eng |
| Report Rejection Rate (NEW-10) | Governance KPI extension | Analytics Eng |
| Report First-Pass Approval (NEW-11) | Same | Analytics Eng |
| Overdue Task Count (NEW-09) | Per-role dashboard widget | Frontend Eng |
| Alert Signal-to-Noise (NEW-06) | Alert system health widget | Analytics Eng |
| Alert False Positive Rate (NEW-07) | Same | Analytics Eng |
| Staff equity dashboard tab | Frontend component | Frontend Eng |
| Integration + regression tests | All new metrics validated | QA |

#### Week 7-8: Enrollment + Correlation Discovery Engine

| Task | Deliverable | Owner |
|------|-------------|-------|
| Enrollment Funnel Drop-off (NEW-12) | Funnel chart component | Frontend Eng |
| Enrollment Turnaround (NEW-13) | Service + endpoint | Analytics Eng |
| Waitlist Conversion Rate (NEW-14) | Same | Analytics Eng |
| Morning Routine Completion (NEW-15) | Workflow analytics | Analytics Eng |
| Correlation Discovery Engine (Phase 1) | Automated pairwise scan; correlation matrix UI | Data Science + Frontend |
| Correlation Explorer dashboard component | Interactive heatmap + scatter drill-down | Frontend Eng |
| Unit tests for Gini, correlation, funnel | 100% coverage | QA |

**Deliverables at end of Wave 2:**
- ✅ Staff equity metrics on manager dashboard
- ✅ Governance quality signals live (rejection rate, first-pass approval)
- ✅ Enrollment funnel visualized per KG
- ✅ Correlation matrix populated with first batch of pairwise scans
- ✅ All statistical tests verified against known synthetic data

---

### 17.4 Wave 3 — Engagement & Predictions (Weeks 9–12)

#### Week 9-10: Parent Engagement Suite

| Task | Deliverable | Owner |
|------|-------------|-------|
| Notification → View Conversion (NEW-16) | Service + dashboard widget | Analytics Eng |
- Notification → Action Conversion (NEW-17) | Same | Analytics Eng |
- Parent Session Duration (NEW-18) | Telemetry aggregation | Frontend Eng |
- NPS Trajectory (NEW-19) | Survey analytics extension | Analytics Eng |
- Absence Request Turnaround (P04) | Workflow metric | Backend Eng |
- Parent engagement dashboard tab | All parent metrics in single view | Frontend Eng |
- Unit tests for parent analytics | Coverage | QA |

#### Week 11-12: Predictive Analytics + Role Dashboards

| Task | Deliverable | Owner |
|------|-------------|-------|
| Attendance Volatility Index (NEW-20) | Time-series analytics extension | Data Science |
| Capacity runway projection enhancement | Extended forecasting (multi-scenario) | Data Science |
| Correlation Engine Phase 2 (causal probes) | Lagged cross-correlation + partial correlation | Data Science |
| Manager dashboard (full implementation) | Section 14.4.2 layout | Frontend Eng |
| Supervisor dashboard (full implementation) | Section 14.4.3 layout | Frontend Eng |
| Parent dashboard (full implementation) | Section 14.4.4 layout | Frontend Eng |
| Correlation Explorer Phase 2 | Scatter + regression drill-down | Frontend Eng |
| E2E test suite for all dashboards | Playwright tests | QA |

**Deliverables at end of Wave 3:**
- ✅ Parent engagement tab fully populated
- ✅ Predictive analytics extended with volatility and capacity runway
- ✅ 4 role-specific dashboards fully implemented
- ✅ Correlation engine with causal probes operational
- ✅ E2E test suite for dashboard navigation

---

### 17.5 Wave 4 — Predictive & Maturity (Weeks 13–16)

#### Week 13-14: Seasonal + Adoption + Engineering Dashboard

| Task | Deliverable | Owner |
|------|-------------|-------|
| Seasonal Attendance Deviation (NEW-21) | STL decomposition + baseline offset | Data Science |
| Daily Report Submission Pattern (NEW-23) | Time-of-day histogram | Analytics Eng |
| Feature Adoption Depth (NEW-22) | Workflow tracking from telemetry events | Frontend + Analytics |
- Overtime Hours per Staff (NEW-24) | Staff welfare metric | Analytics Eng |
- Engineering monitoring dashboard (full) | Section 14.4.5 layout | Frontend Eng |
- Executive dashboard (Ministry view) | Section 14.4.6 layout | Frontend Eng |
- Unit + integration tests for Wave 4 | Coverage | QA |

#### Week 15-16: RTL Regression + Production Readiness

| Task | Deliverable | Owner |
|------|-------------|-------|
| Full RTL visual regression test suite | Playwright baseline + diff for all critical Arabic pages | QA |
| WCAG AA accessibility audit | axe-core scan + manual review | QA |
| Scientific validation protocol execution | All metrics validated against Section 12 | Data Science + QA |
| Industry benchmark calibration | All thresholds validated against Section 13 | Data Science |
| Privacy/security review | No PII leakage in any output | Security |
| Full regression test suite run | All tests green | QA |
| Documentation finalization | Updated KPI docs, user guides, runbooks | All |
| Production readiness gate review | Sign-off from all stakeholders | Product |

**Deliverables at end of Wave 4:**
- ✅ Seasonal analysis operational (Ramadan, holiday adjustments)
- ✅ Feature adoption metrics visible on product dashboard
- ✅ All 5 role-specific dashboards live and tested
- ✅ RTL and accessibility fully verified
- ✅ Scientific validation protocol passed for all metrics
- ✅ Documentation complete

---

### 17.6 Milestone Summary

| Wave | Duration | Key Deliverables | Acceptance Gate |
|------|----------|-----------------|-----------------|
| **Wave 1** | Weeks 1-4 | Data quality + Frontend/Backend telemetry | Data freshness metric < 2h; LCP dashboard visible |
| **Wave 2** | Weeks 5-8 | Staff equity + Enrollment + Correlation engine | Gini coefficient computed; correlation matrix populated |
| **Wave 3** | Weeks 9-12 | Parent engagement + Predictive + Role dashboards | NPS trending; 4 role dashboards functional |
| **Wave 4** | Weeks 13-16 | Seasonal + Adoption + Full dashboards + Validation | Seasonal adjustment validated; RTL regression green |

---

## 18. Risk Register

| ID | Risk | Probability | Impact | Mitigation | Owner |
|----|------|-------------|--------|------------|-------|
| R-01 | **PII leakage via telemetry** | Medium | Critical | Strict schema validation; automated PII scan on every telemetry payload; no PII fields in schema; security review per wave | Security |
| R-02 | **Telemetry data volume overwhelms infrastructure** | Medium | High | Batch flush (10s intervals); keepalive transport; sampling for non-critical metrics; TTL on raw events | Engineering |
| R-03 | **Frontend telemetry degrades page performance** | Low | High | Use `requestIdleCallback` + `keepalive`; non-blocking async flush; disable-on-low-battery detection | Frontend Eng |
| R-04 | **Correlation findings are spurious → wrong decisions** | Medium | High | Stage 2 domain filter; minimum sample size ≥ 14; effect size threshold ≥ 0.5; p-value < 0.05; manual review before surfacing | Data Science |
| R-05 | **Metric thresholds calibrated to wrong benchmarks** | Medium | Medium | Industry benchmark validation (Section 13); Jordanian-specific adaptations; quarterly threshold review | Admin + Product |
| R-06 | **RTL dashboard rendering breaks on charts** | High | Medium | RTL-aware chart config; visual regression tests; manual QA per wave | Frontend Eng |
| R-07 | **Data quality metric itself has bugs** | Medium | Critical | Metric-on-metric testing; canary deployment; human spot-check weekly | QA + Data Science |
| R-08 | **User distrust of new metrics → adoption failure** | Medium | Medium | Bilingual explanations on every metric card; formula transparency; confidence indicator; decision guidance in user language | Product |
| R-09 | **Seasonal patterns (Ramadan) misinterpreted as anomalies** | High | Medium | Seasonal decomposition before anomaly detection; Ramadan-aware anomaly thresholds; documented seasonal adjustment | Data Science |
| R-10 | **Privacy law changes in Jordan require data deletion** | Low | High | Data retention policy with automated purge; encryption at rest; consent tracking; legal review per wave | Legal + Engineering |
| R-11 | **Alert fatigue from too many notifications** | Medium | High | Alert SNR monitoring (NEW-06); threshold auto-calibration; deduplication; severity-tiered notification routing | Engineering |
| R-12 | **Cache invalidation stale → metrics lag behind reality** | Medium | Medium | Cache TTL tuning; explicit invalidation on data write; freshness metric monitors end-to-end latency | Engineering |
| R-13 | **Forecasting model drift over time** | Medium | Medium | Model accuracy tracking; retraining trigger on error threshold exceedance; prediction cache invalidation on model update | Data Science |
| R-14 | **Cross-role IDOR exposure in analytics endpoints** | Low | Critical | RBAC enforcement at every endpoint; scope validation on every query; automated IDOR tests per wave | Security + Engineering |
| R-15 | **Implementation exceeds 16-week timeline** | Medium | Medium | Wave-based delivery; each wave independently valuable; scope reduction on lower-priority metrics; parallel workstreams | Engineering Lead |

---

## 19. Acceptance Criteria

### 19.1 Overall Program Acceptance

The analytics plan is considered **Production Ready** when ALL of the following are true:

| # | Criterion | Verification Method |
|---|-----------|-------------------|
| AC-01 | All 64+ KPIs implemented with formulas, thresholds, owners | Automated inventory scan against metric registry |
| AC-02 | No vanity metrics remain (every metric maps to a decision) | Decision-action matrix review by Admin |
| AC-03 | All metric formulas have unit test coverage ≥ 100% | pytest coverage report |
| AC-04 | Frontend Web Vitals (LCP, FID, CLS) being collected and reported | Live telemetry dashboard |
| AC-05 | Backend p95 latency tracked and visible | Engineering monitoring dashboard |
| AC-06 | Data quality metrics operational and alerting | Data freshness < 2h; completeness alert fires on < 90% |
| AC-07 | Correlation engine populated with first results | Correlation matrix non-empty, results validated |
| AC-08 | Parent engagement metrics collected | Notification → View conversion rate visible |
| AC-09 | All 5 role-specific dashboards functional | E2E tests pass for each dashboard |
| AC-10 | RTL integrity verified for all critical pages | Playwright visual regression tests green |
| AC-11 | WCAG AA accessibility compliance | axe-core + manual audit pass |
| AC-12 | No PII leakage detected in any telemetry or analytics output | Security audit + PII scan |
| AC-13 | Scientific validation protocol passed for all metrics | Validation certificates issued |
| AC-14 | Industry benchmarks calibrated for Jordan context | Benchmark matrix signed off by Admin |
| AC-15 | Data retention policy enforced with automated purge | Retention compliance test |
| AC-16 | Governance model operational (metric versioning, retirement) | Retired metric process tested |
| AC-17 | Error budgets defined and tracked | Error budget burn visible on engineering dashboard |
| AC-18 | All tests passing (unit + integration + E2E + RTL + accessibility) | CI/CD pipeline green |
| AC-19 | Documentation complete (KPI docs, user guides, runbooks) | Documentation audit |
| AC-20 | Sign-off from Admin, Engineering Lead, Product, Security | Formal acceptance recorded |

### 19.2 Wave-Level Acceptance Criteria

#### Wave 1 Acceptance
| # | Criterion |
|---|-----------|
| W1-AC-01 | Data freshness metric < 2h end-to-end latency |
| W1-AC-02 | Data completeness metric computed for all KGs |
| W1-AC-03 | Web Vitals collector installed, sending to backend |
| W1-AC-04 | Backend telemetry endpoint accepting and storing data |
| W1-AC-05 | DB query timing visible in structured logs |
| W1-AC-06 | Cache hit rate being tracked |
| W1-AC-07 | All Wave 1 unit tests passing |
| W1-AC-08 | Data quality alert fires correctly when completeness drops |

#### Wave 2 Acceptance
| # | Criterion |
|---|-----------|
| W2-AC-01 | Teacher workload Gini visible on manager dashboard |
| W2-AC-02 | Report rejection rate computed and displayed |
| W2-AC-03 | Enrollment funnel chart rendered per KG |
| W2-AC-04 | Correlation matrix populated with statistically significant pairs |
| W2-AC-05 | Alert SNR metric computed |
| W2-AC-06 | All Wave 2 unit + integration tests passing |
| W2-AC-07 | Correlation results match known synthetic data (validated) |

#### Wave 3 Acceptance
| # | Criterion |
|---|-----------|
| W3-AC-01 | Parent engagement tab functional with ≥4 metrics |
| W3-AC-02 | NPS trajectory chart displaying |
| W3-AC-03 | Attendance volatility computed per KG |
| W3-AC-04 | Manager + Supervisor + Parent dashboards functional |
| W3-AC-05 | Causal probe results validated |
| W3-AC-06 | All Wave 3 E2E + integration tests passing |

#### Wave 4 Acceptance
| # | Criterion |
|---|-----------|
| W4-AC-01 | Seasonal attendance adjustment operational (Ramadan-aware) |
| W4-AC-02 | Feature adoption depth tracked |
| W4-AC-03 | Engineering + Executive dashboards live |
| W4-AC-04 | Full RTL regression test suite green |
| W4-AC-05 | WCAG AA audit passed |
| W4-AC-06 | Scientific validation protocol executed for all metrics |
| W4-AC-07 | Industry benchmark matrix validated |
| W4-AC-08 | Privacy + security audit passed |
| W4-AC-09 | Full test suite green (unit + integration + E2E + RTL + a11y) |
| W4-AC-10 | Documentation complete and approved |

---

## 20. Final Recommendations

### 20.1 Strategic Recommendations

1. **Adopt a "Decision-First" culture** — Every metric must answer a specific question for a specific role before implementation begins. Metrics without a named decision owner should be retired from the backlog.

2. **Invest in telemetry infrastructure before adding metrics** — Wave 1's foundation (frontend telemetry, backend monitoring, data quality) is the bedrock upon which all future analytical capability depends. Rushing this creates unreliable metrics downstream.

3. **Treat the correlation engine as a hypothesis generator, not an answer machine** — Automated correlation discovery surfaces candidates for investigation. Every flagged pair must be domain-filtered (Step 2) and causally probed (Step 3) before driving business decisions.

4. **Prioritize the top 10 missing indicators first** — The missing indicator audit (§9) identified 35 gaps. The top 10 (report freshness, alert SNR, teacher Gini, report rejection, enrollment funnel, etc.) deliver the highest decision impact for the lowest implementation complexity.

5. **Design for Jordan-specific context** — Seasonal patterns (Ramadan), regional infrastructure differences, RTL complexity, and MoSD regulatory thresholds must be built into the baseline models, not bolted on later.

6. **Maintain a strict privacy firewall** — No PII of any kind (child names, parent contact info, health data, incident narratives) should appear in telemetry, analytics exports, or any metric output. This is non-negotiable given the platform's subject population.

### 20.2 Technical Recommendations

7. **Start with PostgreSQL-native aggregations before adding dedicated analytical stores** — KinJo's existing `advanced_analytics_cache`, `analytics_dimension_cache`, and `prediction_cache` tables provide sufficient structure. Only add dedicated time-series storage (TimescaleDB, ClickHouse) if aggregation latency exceeds the 3-second budget.

8. **Use the existing WebSocket infrastructure for real-time alerting** — The `/ws/dashboard` and `/ws/heatmap` channels already support role-scoped, 30-second streaming. Extend these to deliver metric threshold breaches rather than adding new real-time infrastructure.

9. **Leverage Celery beat for periodic metric jobs** — The existing `celery_app.py` infrastructure supports scheduled tasks. Use it for weekly correlation scans, daily data quality audits, and monthly baseline refreshes rather than introducing new schedulers.

10. **Implement structured logging (JSON) from day one** — Every metric computation and API response should emit structured JSON logs with correlation IDs, role context, and timing data. This avoids needing a separate observability stack initially.

11. **Cache aggressively but invalidate correctly** — Use Redis for hot metrics (7-day TTL), PostgreSQL for warm metrics, and explicit cache invalidation on data writes. The existing `cache_service.py` should be instrumented (not replaced).

12. **Use Plotly.js for all charting** — It is already integrated (`static/vendor/plotly-2.35.2.min.js`), supports RTL configuration, and provides interactive drill-down. Do not introduce additional charting libraries.

### 20.3 Organizational Recommendations

13. **Establish a metric governance committee** — A standing committee (Admin + Engineering Lead + Product + Data Scientist) should meet quarterly to review metric relevance, retire stale metrics, approve new ones, and recalibrate thresholds.

14. **Invest in bilingual explanations for every metric** — The existing `kpi_service.py` already has bilingual `explanation`, `manager_note`, `action_items`, `formula`, and `decision_guidance` fields. Extend this pattern to all new metrics. This is the primary driver of user trust and adoption.

15. **Run quarterly "metric usefulness audits"** — After 6 months of operation, review which metrics actually drove decisions and which remained unexamined. Retire the latter to reduce cognitive load.

16. **Build the correlation engine before the predictive models** — Understanding which variables are correlated (and which are not) is essential before building reliable forecasts. Prediction without correlation understanding produces overconfident but inaccurate forecasts.

### 20.4 Anti-Recommendations (What NOT to Do)

17. **Do not add metrics without threshold definitions** — A metric without a warning threshold and a critical threshold is a dashboard decoration, not a decision support tool.

18. **Do not correlate across different data granularity levels** — Daily attendance cannot meaningfully correlate with monthly training completion without explicit temporal aggregation.

19. **Do not expose child-level data in any aggregate dashboard** — Even if the data exists in the DB, child-level rows should never appear in a network or governorate dashboard. The drill-down stops at the class level for privacy.

20. **Do not implement all 24 new metrics simultaneously** — Prioritize by wave (1-4). Each wave's deliverables must be validated before the next wave begins. Parallel development of all metrics creates integration risk and quality debt.

---

## Appendix A: Glossary

| Term | Definition |
|------|-----------|
| **GCEI** | Governance & Child Experience Index — KinJo's composite quality score (0-100) |
| **LCP** | Largest Contentful Paint — Google Web Vital metric for perceived load speed |
| **FID** | First Input Delay — Google Web Vital metric for interactivity responsiveness |
| **CLS** | Cumulative Layout Shift — Google Web Vital metric for visual stability |
| **RED** | Rate, Errors, Duration — SRE metrics for service-level monitoring |
| **USE** | Utilization, Saturation, Errors — SRE metrics for resource-level monitoring |
| **STL** | Seasonal-Trend decomposition using LOESS — Time-series decomposition method |
| **EWMA** | Exponentially Weighted Moving Average — Smoothing technique for baselines |
| **VIF** | Variance Inflation Factor — Multicollinearity diagnostic in regression |
| **Gini** | Gini Coefficient — Measure of inequality (0 = perfect equality, 1 = perfect inequality) |
| **IDOR** | Insecure Direct Object Reference — Security vulnerability where users can access unauthorized objects |
| **RBAC** | Role-Based Access Control — Authorization model based on user roles |
| **SLO** | Service Level Objective — Reliability target for a service |
| **NPS** | Net Promoter Score — Customer loyalty metric (-100 to +100) |
| **WCAG** | Web Content Accessibility Guidelines — International accessibility standard |
| **RTL** | Right-To-Left — Text directionality for Arabic, Hebrew, etc. |
| **MoSD** | Ministry of Social Development (Jordan) — Regulatory authority for early childhood education |

---

## Appendix B: KinJo-Specific References

| Resource | Location | Purpose |
|----------|----------|---------|
| KPI Service | `kpi_service.py` | Source of truth for all KPI definitions, thresholds, actions |
| KPI Standards | `kpi_standards.py` | Threshold definitions, band classification, confidence levels |
| Analytics Domain | `analytics_domain.py` | Statistical methods, anomaly detection, forecasting |
| Analytics Service | `analytics_service.py` | Drill-down hierarchy, benchmarking, predictions |
| Manager Analytics | `manager_analytics.py` | Manager-scoped analytics |
| Governance KPI | `governance_kpi_service.py` | Governance funnel, Bayesian ranking |
| Predictive Analytics | `predictive_analytics.py` | Linear-trend forecasting |
| Data Quality | `data_quality_service.py` | Quality indices |
| Monitoring | `monitoring_service.py` | System health, auto-scaling |
| Charts/API | `charts/service.py` + `charts_api.py` | Plotly charting |
| Heat Map | `heatmap/` + `templates/admin/heatmap.html` + `static/js/jordan_heatmap.js` | Jordan geospatial layer |
| Admin Design System | `static/css/admin_design_system.css` | Shared styling |
| i18n Files | `static/i18n/admin_ar.json`, `admin_en.json` | Bilingual strings |

---

*This document is the definitive analytics blueprint for the KinJo platform. It should be reviewed and updated quarterly by the data governance committee.*