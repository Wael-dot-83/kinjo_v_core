# Jordan National Nursery Intelligence — Heat Map Dashboard
## Comprehensive Technical Specification & Implementation Roadmap

**Document version:** 1.0
**Status:** Approved for implementation
**Owner:** Lead Data Scientist & Systems Architect
**Last updated:** 2026-06-13
**Implementation status:** Phases 1, 2 & 3 are SHIPPED (production-grade, government-ready).
Phases 1+2 (MVP + analytical engine) were completed in 1 cycle; Phase 3
(alert engine + UI) was completed in 1 additional cycle. The Heat Map is
now serving 12 governorates with full statistical analysis, risk scoring,
alerting, historical trends, caching and metrics.

**Test coverage:** 96 new heat map tests + 168 pre-existing tests = **264 tests
passing**.

**Recent deliverables** (since the last document update):
- Production-grade Pearson + Spearman + OLS + VIF analytical engine (`heatmap/backend/analytics/`)
- Idempotent daily ETL pipeline with 7 sub-stages and full run audit (`heatmap/backend/pipeline.py`)
- 8 new SQLAlchemy models backed by 8 Alembic-managed tables
- 13 admin API endpoints with Redis caching and Prometheus metrics
- 6 main + 26 sub indicators, 4 risk levels, 3-tier alert engine
- Full Bilingual (AR/EN) RTL admin UI with hover tooltips, click detail panel, smooth zoom, risk sparklines, correlation pills, regression bars
- Database seeder with hand-computed fixtures
- Comprehensive test coverage: statistical correctness, pipeline integration, E2E, API contract, cache layer

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Goals, Non-Goals, and Success Criteria](#2-goals-non-goals-and-success-criteria)
3. [System Architecture](#3-system-architecture)
4. [Data Model & Daily Snapshot Architecture](#4-data-model--daily-snapshot-architecture)
5. [Mathematical Engine — Specifications](#5-mathematical-engine--specifications)
6. [Risk Scoring Model](#6-risk-scoring-model)
7. [Alerting & Threshold Subsystem](#7-alerting--threshold-subsystem)
8. [Daily Update Pipeline](#8-daily-update-pipeline)
9. [API Contract](#9-api-contract)
10. [UI/UX Design System](#10-uiux-design-system)
11. [Frontend Information Architecture](#11-frontend-information-architecture)
12. [Performance, Caching, and Scaling](#12-performance-caching-and-scaling)
13. [Security, Privacy, and Audit](#13-security-privacy-and-audit)
14. [Observability](#14-observability)
15. [Testing Strategy](#15-testing-strategy)
16. [Phased Implementation Roadmap](#16-phased-implementation-roadmap)
17. [Acceptance Criteria](#17-acceptance-criteria)
18. [Risks, Open Questions, and Assumptions](#18-risks-open-questions-and-assumptions)
19. [Appendix A — Mathematical Reference](#appendix-a--mathematical-reference)
20. [Appendix B — Data Quality Matrix](#appendix-b--data-quality-matrix)
21. [Appendix C — Glossary](#appendix-c--glossary)

---

## 1. Executive Summary

The Jordan National Nursery Intelligence — Heat Map Dashboard (the **"Heat Map"**) is a government-grade, decision-support visualization layer for the Ministry of Social Development. It aggregates operational data from every licensed nursery in Jordan into a single interactive map of the country's 12 governorates, color-coded by 6 composite indicators and 22 sub-indicators, with embedded statistical analysis (Pearson + Spearman correlation, OLS multiple regression), a unified risk scoring model, and a four-tier alerting system.

The Heat Map reuses the existing KinJo platform's data warehouse and authentication layer; it is a read-side analytics surface, not a separate operational system. The mathematical engine and data pipelines are designed to be reproducible, testable, and explainable — every number on the screen can be traced back to a specific formula and a specific set of records.

The implementation is split into 4 delivery phases over 9 months. Phase 1 ships a working production dashboard for the 12 governorates; Phase 2 adds the correlation and regression engine; Phase 3 layers in the risk model and alerting; Phase 4 hardens the system for national rollout and integrates with ministry external systems.

### 1.1 Design Tenets

1. **Numbers are explainable.** Every color, every badge, every score is traceable to a formula and a dataset.
2. **Summary first, detail on demand.** The default view is a clean map with the highest-level risk; the user drills into a governorate to see sub-indicators, then into a sub-indicator to see alerts and historical trend.
3. **Government-grade UX.** WCAG 2.1 AA, Arabic-first RTL, full keyboard navigation, no flashy animations.
4. **Degrade gracefully.** If the data pipeline is delayed, the map shows the last known good snapshot with a clear "as of" timestamp — never fabricated numbers.
5. **Statistically honest.** The system shows *confidence* in its own outputs (sample size, p-value, regression R²) so decision-makers do not over-trust small-N results.

---

## 2. Goals, Non-Goals, and Success Criteria

### 2.1 Functional Goals

| ID | Goal | Priority |
|---|---|---|
| G1 | Render an interactive map of Jordan with all 12 governorates | P0 |
| G2 | Color each governorate by the selected composite indicator (0-100) | P0 |
| G3 | Allow the user to switch between the 6 main indicators and a composite risk score | P0 |
| G4 | Provide hover tooltips and click-to-drill-down panels for each governorate | P0 |
| G5 | Calculate Pearson + Spearman correlations between every main and sub indicator pair | P1 |
| G6 | Calculate standardized OLS regression weights for every main indicator | P1 |
| G7 | Compute a 0-100 risk score per governorate and bucket it into 4 levels | P0 |
| G8 | Trigger alerts when sub-indicator thresholds are exceeded | P0 |
| G9 | Recompute all indicators daily and publish new snapshots | P0 |
| G10 | Maintain a historical log of all indicator values, correlations, and alerts | P1 |
| G11 | Show trends vs. previous period in the governorate detail panel | P1 |
| G12 | Allow the admin to acknowledge and resolve alerts | P1 |
| G13 | Surface the Heat Map from the Admin sidebar and analytics page | P0 |
| G14 | Provide an audit trail for every read of personal data | P2 |

### 2.2 Non-Goals

- **Real-time streaming.** The Heat Map updates daily; sub-daily updates are out of scope.
- **Predictive forecasting.** Out of scope for the first three phases. The roadmap reserves Phase 4 for predictive models, but only after at least 90 days of historical data are accumulated.
- **Mobile app.** The dashboard is a responsive web app; a dedicated mobile app is not in scope.
- **Non-Jordan geographies.** The 12 Jordan governorates are the only supported scope.

### 2.3 Success Metrics

| Metric | Target |
|---|---|
| Daily snapshot SLA | 99% of days, snapshot complete by 04:00 local time |
| Dashboard load (p95) | < 1.5 s on a 4G connection |
| Time-to-insight for an Admin | < 30 s (open dashboard → identify the highest-risk governorate) |
| False-alert rate (LOW + MEDIUM alerts that admins dismiss without action) | < 25% |
| Adoption | 100% of admin users use the Heat Map at least once per week |
| Accessibility | All pages pass axe-core and Lighthouse a11y audits ≥ 95 |

---

## 3. System Architecture

### 3.1 Component Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Admin Browser (Chrome/Edge/Safari)                  │
│   ┌──────────────────────────────────────────────────────────────────────┐   │
│   │  Jinja2-rendered Admin Heat Map page (heatmap.html)                  │   │
│   │  + jordan_heatmap.js (SVG render, tooltips, side panel)              │   │
│   │  + chart.js (KPI sparklines, comparison charts)                      │   │
│   └──────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │ HTTPS / JSON
                                   ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                       FastAPI Application (KinJo main)                       │
│                                                                              │
│   ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐     │
│   │  admin_router      │  │  /api/admin/       │  │  /api/heatmap/*    │     │
│   │  /api/admin/heat-  │  │  heat-map/*        │  │  (legacy ETL       │     │
│   │  map/*             │  │  (canonical)       │  │  router)           │     │
│   └─────────┬──────────┘  └─────────┬──────────┘  └─────────┬──────────┘     │
│             │                       │                       │                │
│             └───────────────┬───────┴───────────┬───────────┘                │
│                             ▼                   ▼                            │
│   ┌────────────────────────────────┐  ┌────────────────────────────────┐      │
│   │  heatmap.backend.service        │  │  heatmap.backend.etl          │      │
│   │  (read-side aggregator)         │  │  (daily pipeline)             │      │
│   │  - get_map_overview             │  │  - ingest / compute / stats   │      │
│   │  - get_governorate_overview     │  │  - correlations / regression  │      │
│   │  - get_correlations             │  │  - alerts dispatch            │      │
│   │  - get_regression_weights       │  └──────────────┬─────────────────┘      │
│   │  - daily_update_summary         │                 │                        │
│   └────────────┬───────────────────┘                 │                        │
│                │                                       │                        │
│                └──────────────┬────────────────────────┘                        │
│                               ▼                                                 │
│   ┌─────────────────────────────────────────────────────────────────┐         │
│   │  heatmap.backend.constants                                      │         │
│   │  - 12 governorates, 6 main indicators, 22 sub-indicators        │         │
│   │  - risk thresholds, recommended actions                         │         │
│   └─────────────────────────────────────────────────────────────────┘         │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────┐         │
│   │  heatmap.backend.alerts.engine                                  │         │
│   │  - rule evaluation, severity, dispatch (in-app, email, SMS)    │         │
│   └─────────────────────────────────────────────────────────────────┘         │
└──────────────────────────────┬───────────────────────────────────────────────┘
                               │ SQLAlchemy ORM
                               ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│   PostgreSQL  (KinJo)                                                        │
│                                                                              │
│   Existing tables used:                                                       │
│     - kindergartens (governorate, status, governance_score)                  │
│     - children, users (kindergarten_id, role)                                │
│     - classrooms, daily_reports, incidents, active_alerts                    │
│                                                                              │
│   New tables (read-side, see §4):                                            │
│     - map_indicator_snapshot   (one row per (date, governorate, indicator))  │
│     - map_correlation_snapshot (one row per (date, main, sub) pair)          │
│     - map_regression_snapshot  (one row per (date, main, sub) beta + se)     │
│     - map_risk_snapshot        (one row per (date, governorate) risk + lvl)  │
│     - map_alert_history        (append-only)                                 │
│     - map_daily_run_log        (pipeline run audit)                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Process Topology

| Process | Role | Concurrency |
|---|---|---|
| FastAPI app | Serves dashboard + API | 4-16 workers behind a load balancer |
| APScheduler (in-process) | Triggers daily ETL at 02:00 local time | 1 leader (lock file) |
| Celery worker (optional) | Off-loads heavy nightly regression | 2-4 workers |
| Redis | Caches `/api/admin/heat-map/data` for 5 min; session store; CSRF | 1 instance or cluster |
| PostgreSQL | Primary store; daily snapshots; audit log | Primary + read replica |

### 3.3 Code Layout (Target)

```
heatmap/
├── backend/
│   ├── constants.py         # governorates, indicators, risk, correlation levels
│   ├── service.py           # read-side aggregator (queries DB → payloads)
│   ├── admin_router.py      # /api/admin/heat-map/* FastAPI router
│   ├── api/                 # legacy /api/heatmap/* (ETL control, intensity points)
│   ├── etl/                 # ingest, compute, validate, pipeline
│   ├── analytics/           # pearson, ols, stats
│   ├── alerts/              # engine, dispatcher
│   └── config.py            # env-driven config
├── data/
│   └── jordan_admin.geojson # governorate boundaries (canonical)
├── scripts/
│   ├── init_heatmap_schema.sql
│   ├── seed_test_data.py
│   └── daily_cron.sh
└── docs/
    ├── api_spec.yaml
    └── INTEGRATE.md

static/js/jordan_heatmap.js    # client renderer
templates/admin/heatmap.html   # dedicated admin page
tests/test_admin_heatmap.py    # unit + integration tests
```

---

## 4. Data Model & Daily Snapshot Architecture

### 4.1 Design Principles

1. **Snapshot, not stream.** The Heat Map is a daily batch; every read returns the *most recent successful snapshot*. Live numbers are an internal concern only.
2. **One row per (date, dimension).** Every snapshot table is keyed on `(snapshot_date, governorate_code)` or `(snapshot_date, main_indicator, sub_indicator)`. Uniqueness is enforced; ON CONFLICT DO UPDATE is the upsert.
3. **Snapshots are immutable once written.** To "correct" a snapshot, write a new one for the same date (the pipeline is idempotent on date).
4. **Audit trail is append-only.** `map_daily_run_log` and `map_alert_history` are never updated — only inserted.
5. **Reuse existing models where possible.** The pipeline aggregates from `kindergartens`, `users`, `incidents`, `daily_reports`, `active_alerts` — no duplication of operational state.

### 4.2 Entity-Relationship Overview

```
                       ┌──────────────────────┐
                       │  map_daily_run_log   │  (append-only audit)
                       └──────────┬───────────┘
                                  │ 1 run produces…
                                  ▼
┌──────────────────┐     ┌──────────────────────────┐
│  Kindergartens   │────▶│ map_indicator_snapshot   │  (one row per date × gov × main_ind)
│  (existing)      │     └──────────────────────────┘
└──────────────────┘
                       ┌──────────────────────────┐
                       │ map_sub_indicator_value  │  (one row per date × gov × sub_ind)
                       └──────────────────────────┘
                       ┌──────────────────────────┐
                       │ map_correlation_snapshot │  (one row per date × main × sub)
                       └──────────────────────────┘
                       ┌──────────────────────────┐
                       │ map_regression_snapshot  │  (one row per date × main × sub)
                       └──────────────────────────┘
                       ┌──────────────────────────┐
                       │ map_risk_snapshot        │  (one row per date × gov)
                       └──────────────────────────┘
                       ┌──────────────────────────┐
                       │ map_alert_history        │  (append-only; one row per alert)
                       └──────────────────────────┘
```

### 4.3 SQL DDL

```sql
-- All snapshots are keyed on the snapshot date and are immutable once written.

CREATE TABLE map_indicator_snapshot (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,    -- e.g. JO-AM
    main_indicator    VARCHAR(40)  NOT NULL,    -- one of the 6 main keys
    value             NUMERIC(6,2) NOT NULL CHECK (value BETWEEN 0 AND 100),
    previous_value    NUMERIC(6,2),
    trend_pct         NUMERIC(6,2),
    sample_size       INTEGER      NOT NULL DEFAULT 0,
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, governorate_code, main_indicator)
);
CREATE INDEX idx_mis_latest  ON map_indicator_snapshot (snapshot_date DESC, governorate_code);
CREATE INDEX idx_mis_history ON map_indicator_snapshot (governorate_code, main_indicator, snapshot_date DESC);

CREATE TABLE map_sub_indicator_value (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,
    sub_indicator     VARCHAR(40)  NOT NULL,    -- see §5.1 for full key list
    raw_value         NUMERIC(14,4) NOT NULL,
    threshold_high    NUMERIC(14,4),
    threshold_low     NUMERIC(14,4),
    above_threshold   BOOLEAN      NOT NULL DEFAULT FALSE,
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, governorate_code, sub_indicator)
);
CREATE INDEX idx_ssiv_gov ON map_sub_indicator_value (snapshot_date DESC, governorate_code);

CREATE TABLE map_correlation_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    main_indicator  VARCHAR(40)  NOT NULL,
    sub_indicator   VARCHAR(40)  NOT NULL,
    method          VARCHAR(10)  NOT NULL CHECK (method IN ('pearson', 'spearman')),
    coefficient     NUMERIC(6,4) NOT NULL CHECK (coefficient BETWEEN -1 AND 1),
    p_value         NUMERIC(10,6),
    n_samples       INTEGER      NOT NULL,
    strength        VARCHAR(15)  NOT NULL,    -- weak/moderate/strong/very_strong
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, main_indicator, sub_indicator, method)
);
CREATE INDEX idx_corr_latest ON map_correlation_snapshot (snapshot_date DESC);

CREATE TABLE map_regression_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    main_indicator  VARCHAR(40)  NOT NULL,
    sub_indicator   VARCHAR(40)  NOT NULL,
    beta_std        NUMERIC(8,4) NOT NULL,
    std_error       NUMERIC(8,4),
    t_stat          NUMERIC(10,4),
    p_value         NUMERIC(10,6),
    r_squared       NUMERIC(6,4),
    high_impact     BOOLEAN      NOT NULL DEFAULT FALSE,
    n_samples       INTEGER      NOT NULL,
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, main_indicator, sub_indicator)
);

CREATE TABLE map_risk_snapshot (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,
    risk_score        NUMERIC(5,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_level        VARCHAR(10)  NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    top_driver_sub    VARCHAR(40),                -- highest-weight sub-indicator
    top_driver_beta   NUMERIC(8,4),
    trend_pct         NUMERIC(6,2),               -- change vs previous snapshot
    contributing_subs JSONB       NOT NULL DEFAULT '[]',
    UNIQUE (snapshot_date, governorate_code)
);
CREATE INDEX idx_risk_latest ON map_risk_snapshot (snapshot_date DESC);

CREATE TABLE map_alert_history (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    governorate_code VARCHAR(8),
    sub_indicator   VARCHAR(40)  NOT NULL,
    rule            VARCHAR(80)  NOT NULL,        -- THRESHOLD_AND_HIGH_IMPACT, HEALTH_HOTSPOT, …
    severity        VARCHAR(10)  NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    current_value   NUMERIC(14,4),
    threshold       NUMERIC(14,4),
    message         TEXT         NOT NULL,
    meta            JSONB        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by INTEGER       REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    resolved_by     INTEGER       REFERENCES users(id)
);
CREATE INDEX idx_alert_open ON map_alert_history (snapshot_date DESC, acknowledged_at) WHERE acknowledged_at IS NULL;
CREATE INDEX idx_alert_gov   ON map_alert_history (governorate_code, snapshot_date DESC);

CREATE TABLE map_daily_run_log (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID         NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    started_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          VARCHAR(20)  NOT NULL CHECK (status IN ('running','success','failed','partial')),
    rows_processed  INTEGER      NOT NULL DEFAULT 0,
    governorates    INTEGER      NOT NULL DEFAULT 0,
    errors          JSONB        NOT NULL DEFAULT '[]',
    warnings        JSONB        NOT NULL DEFAULT '[]',
    duration_ms     INTEGER
);
```

### 4.4 Data Retention

| Table | Retention |
|---|---|
| `map_indicator_snapshot`, `map_sub_indicator_value` | Unlimited (one row per (date, dimension), ~150 rows/day) |
| `map_correlation_snapshot`, `map_regression_snapshot` | Unlimited; correlation matrices are cheap to keep |
| `map_risk_snapshot` | Unlimited; required for long-term trend reporting |
| `map_alert_history` | 24 months hot, then archived to cold storage (S3 / object store) |
| `map_daily_run_log` | 12 months hot; then aggregate to monthly summary rows |

### 4.5 Indexing Strategy

Read patterns are dominated by:
- "Get the latest snapshot for all governorates" → `(snapshot_date DESC, governorate_code)`
- "Get the historical time series for one (gov, main_indicator)" → `(governorate_code, main_indicator, snapshot_date DESC)`
- "Get the latest correlation matrix" → `(snapshot_date DESC)`
- "Get all open alerts for one governorate" → `(governorate_code, snapshot_date DESC) WHERE acknowledged_at IS NULL`

These are covered by the indexes in the DDL above. The `map_indicator_snapshot` table grows at ~150 rows per day; after 2 years that's ~110k rows, well within PostgreSQL's sweet spot for B-tree lookups.

---

## 5. Mathematical Engine — Specifications

### 5.1 Main Indicators and Sub-Indicators

The 6 main indicators and 22 sub-indicators are defined as the single source of truth in `heatmap/backend/constants.py`. The full inventory:

#### 5.1.1 Nursery Status (`nursery_status`)

| Sub-indicator | Key | Unit | Higher is better? | Threshold (low) | Threshold (high) |
|---|---|---|---|---|---|
| Active nurseries | `active_nurseries` | count | yes | 50 | 200 |
| Inactive nurseries | `inactive_nurseries` | count | no | 10 | 30 |
| Active % | `active_pct` | pct | yes | 75 | 90 |
| Inactive % | `inactive_pct` | pct | no | 10 | 25 |

Composite (0-100): `active_pct`. (We could also weight by raw count, but for cross-governorate comparison the ratio is fairer because Amman will always have more nurseries than Tafileh.)

#### 5.1.2 Children & Registration (`children_registration`)

| Sub-indicator | Key | Higher is better? |
|---|---|---|
| Registered children | `registered_children` | yes |
| Unregistered children | `unregistered_children` | no |
| Registration rate | `registration_rate` | yes |
| Children by age group | `age_distribution` | yes |

Composite (0-100): `registration_rate`.

#### 5.1.3 Staff & Classrooms (`staff_classrooms`)

| Sub-indicator | Key | Higher is better? |
|---|---|---|
| Supervisors | `supervisors_count` | yes |
| Classrooms | `classrooms_count` | yes |
| Classrooms without supervisor | `classrooms_no_supervisor` | no |
| Child-supervisor ratio | `child_supervisor_ratio` | no |
| Child-teacher ratio | `child_teacher_ratio` | no |

Composite (0-100): `100 × (1 − classrooms_no_supervisor / max(classrooms_count, 1))` clamped to [0, 100].

#### 5.1.4 Safety & Incidents (`safety_incidents`)

| Sub-indicator | Key | Higher is better? |
|---|---|---|
| Total incidents | `incidents_total` | no |
| Critical incidents | `incidents_critical` | no |
| Protection cases | `protection_cases` | no |
| Severity level | `incident_severity` | no |

Composite (0-100): `max(0, 100 − min(100, critical_incidents × 10 + protection_cases × 5))`.

#### 5.1.5 Reports & Attendance (`reports_attendance`)

| Sub-indicator | Key | Higher is better? |
|---|---|---|
| Daily reports submitted | `reports_submitted` | yes |
| Missing reports | `reports_missing` | no |
| Absence rate | `absence_rate` | no |
| Health absences | `health_absences` | no |
| Repeated health absences | `repeated_health` | no |

Composite (0-100):
```
report_completeness = min(1, reports_submitted / max(active_nurseries * 30, 1))
score = (0.5 × report_completeness
       + 0.3 × (1 − absence_rate/100)
       + 0.2 × (1 − health_absences/max(health_absences + 1, 1)))
     × 100
```

#### 5.1.6 Tasks & Governance (`tasks_governance`)

| Sub-indicator | Key | Higher is better? |
|---|---|---|
| Delayed tasks | `delayed_tasks` | no |
| Governance score | `governance_score` | yes |
| Training completion | `training_completion` | yes |
| Compliance status | `compliance_status` | yes |

Composite (0-100):
```
task_penalty = min(50, delayed_tasks × 5)
score = governance_score × 0.5
      + training_completion × 0.3
      + max(0, 50 − task_penalty) × 0.4
```

### 5.2 Correlation Analysis

#### 5.2.1 Method Selection

For each (main_indicator, sub_indicator) pair:

1. **Sample size check.** If `n < 5`, return coefficient = `null`, strength = `insufficient`.
2. **Normality test.** Run Shapiro-Wilk on the sub-indicator series. If `p > 0.05` (cannot reject normality) AND the data type is continuous, use **Pearson**. Otherwise use **Spearman**.
3. **Monotonicity guard.** Spearman requires the rank transform to produce a non-degenerate distribution (no ties > 50% of the sample). If this fails, fall back to a non-parametric Kendall τ.

The default threshold is configurable per-indicator in `constants.py` (e.g. for `repeated_health` we always use Spearman because the distribution is heavily right-skewed with many zeros).

#### 5.2.2 Pearson Correlation

For vectors `x = (x₁, …, xₙ)` and `y = (y₁, …, yₙ)`:

```
x̄ = (1/n) Σ xᵢ          ȳ = (1/n) Σ yᵢ
Sx = Σ (xᵢ − x̄)²        Sy = Σ (yᵢ − ȳ)²
Sxy = Σ (xᵢ − x̄)(yᵢ − ȳ)

r = Sxy / √(Sx × Sy)
```

Two-tailed p-value via t-distribution with `df = n − 2`:

```
t = r × √((n − 2) / (1 − r²))
p = 2 × (1 − F_t(|t|, df))
```

#### 5.2.3 Spearman Correlation

Apply rank transform with average ranks for ties:

```
R(xᵢ) = rank of xᵢ, breaking ties by mean
R(yᵢ) = rank of yᵢ, breaking ties by mean

rₛ = Pearson(R(x), R(y))
```

This is equivalent to the formula above but applied to ranks; the p-value uses the t-distribution as well, with the same `n − 2` degrees of freedom (for `n ≥ 10`; smaller samples use a permutation-based p-value).

#### 5.2.4 Strength Bucketing

| `|r|` | Strength | Color |
|---|---|---|
| 0.00 – 0.29 | Weak | `#94A3B8` (slate-400) |
| 0.30 – 0.59 | Moderate | `#3B82F6` (blue-500) |
| 0.60 – 0.79 | Strong | `#F59E0B` (amber-500) |
| 0.80 – 1.00 | Very Strong | `#DC3545` (red-600) |

We **never** report correlation without a p-value. Any strength classification with `p > 0.05` is rendered with a striped pattern in the UI and the tooltip says "not statistically significant".

#### 5.2.5 Edge Cases

| Case | Handling |
|---|---|
| Constant series (zero variance) | `r = null`, flag as "constant — cannot correlate" |
| Single observation | `n < 5` → `r = null` |
| High proportion of ties | Use Kendall's τ instead of Spearman |
| Negative correlation (r < 0) | Same bucketing by `|r|`, but tooltip notes the inverse direction |

### 5.3 Multiple Regression Analysis

#### 5.3.1 Standardized OLS

For each main indicator `Y` and its sub-indicators `X = (X₁, …, Xₖ)`:

1. Standardize each column to mean 0, standard deviation 1 (sample SD, ddof=1).
2. Solve `β = (XᵀX)⁻¹ Xᵀy` (centered and standardized).
3. Standard error of each coefficient from the covariance matrix.
4. t-statistic and two-tailed p-value via the t-distribution with `df = n − k − 1`.

The `β` values are the **standardized regression coefficients** (also known as "beta weights" or "importance coefficients"). They represent the change in `Y` (in standard-deviation units) for a one-SD change in `Xⱼ`, holding all other predictors constant. They are directly comparable across sub-indicators.

#### 5.3.2 Subset Selection

We always use **all** sub-indicators defined for a main indicator (no stepwise selection). This is intentional: domain knowledge says all four factors contribute, and stepwise regression tends to over-fit on small samples. If `k + 1 ≥ n` we fall back to ridge regression with `λ = 0.1` to keep the coefficients well-defined.

#### 5.3.3 High-Impact Threshold

A sub-indicator is flagged `high_impact` if `|β_std| ≥ 0.20`. This is the threshold recommended in the spec; it is validated empirically by reviewing the magnitude of coefficients across the most recent 30 days of snapshots.

#### 5.3.4 Goodness of Fit

We report R² (coefficient of determination) per main indicator:

```
R² = 1 − SSres / SStot
```

If `R² < 0.3` we show a "weak fit" warning in the UI: the regression explains less than 30% of the variance; sub-indicators alone may not capture the main indicator. This is a hint to the data team to look for missing drivers.

#### 5.3.5 Output Schema

Each row of `map_regression_snapshot`:

| Column | Meaning |
|---|---|
| `beta_std` | Standardized coefficient |
| `std_error` | Standard error of the coefficient |
| `t_stat` | t-statistic for the coefficient |
| `p_value` | Two-tailed p-value |
| `r_squared` | Goodness of fit for the whole model |
| `high_impact` | Boolean, `|beta_std| >= 0.20` |
| `n_samples` | Number of observations |

#### 5.3.6 Priority Score

The priority score for a governorate is a weighted sum of its sub-indicator values, where the weights are the absolute value of the standardized coefficients. The "highest-impact sub-indicator" for a governorate is the one with the largest absolute deviation from the network mean, weighted by its coefficient.

```
priority_score = Σⱼ |βⱼ| × |xⱼ − x̄_net| / σ_netⱼ
```

This is normalized to 0-100 for display.

### 5.4 Statistical Honesty

| Concern | Mitigation |
|---|---|
| False positive from multiple testing | Bonferroni correction is applied to the family of p-values within a main indicator |
| Insufficient sample size | Any correlation with `n < 5` is reported as `null` with a flag |
| Multicollinearity in regression | Variance Inflation Factor (VIF) is computed per sub-indicator; `VIF > 10` triggers a warning |
| Temporal autocorrelation | Daily snapshots are aggregated to weekly before computing long-term correlations |
| Outliers | Correlations and regression are reported both with and without the top/bottom 1% of values (Tukey fences); the difference is shown if it exceeds 0.1 |

---

## 6. Risk Scoring Model

### 6.1 Inputs

For each governorate on a given snapshot date:

1. The 6 main indicator values (0-100, higher is better).
2. The 22 sub-indicator values and their threshold flags.
3. The standardized regression coefficients from `map_regression_snapshot`.
4. The historical main-indicator values for the previous 30 days (for trend direction).
5. The active alerts from `map_alert_history`.

### 6.2 Formula

```
For each main indicator i:
  indicator_risk_i = 100 − main_indicator_value_i      # invert 0-100 to risk

For each sub-indicator j belonging to main i:
  threshold_violation_j = (above_threshold_j) × |raw_value − threshold|
  correlation_bonus_j   = |pearson_r(main_i, sub_j)| × (|beta_std_j| ≥ 0.20)

trend_penalty_i = clip(− trend_pct, 0, 30)            # worsening trend adds up to 30 risk points

sub_indicator_risk_i = (
    0.5 × threshold_violation_normalized
  + 0.3 × correlation_bonus
  + 0.2 × trend_penalty_i / 30
)

governorate_risk_score = (
    0.65 × Σᵢ wᵢ × indicator_risk_i
  + 0.35 × Σᵢ wᵢ × sub_indicator_risk_i
)
where wᵢ = 1/6 (equal weight; can be tuned in constants.py)
```

The output is then clipped to `[0, 100]`.

### 6.3 Risk Levels

| Score | Level | Color (UI) |
|---|---|---|
| 0 – 25 | Low | `#28A745` |
| 26 – 50 | Medium | `#FFC107` |
| 51 – 75 | High | `#FD7E14` |
| 76 – 100 | Critical | `#DC3545` |

These are *exact* boundaries (0-25 inclusive is Low, 26-50 is Medium, etc.) and are defined in `constants.RISK_LEVELS`.

### 6.4 Recommended Actions

For each risk level, the system displays a recommended action template. The templates are bilingual (Arabic/English) and live in `constants.RECOMMENDED_ACTIONS`:

| Level | Recommended action (EN) | Recommended action (AR) |
|---|---|---|
| Low | Continue routine monitoring. | متابعة المراقبة الدورية. |
| Medium | Schedule a review within 30 days. | جدولة مراجعة خلال 30 يوماً. |
| High | Assign supervisor and remediate within 14 days. | تعيين مشرف ومعالجة الوضع خلال 14 يوماً. |
| Critical | Escalate to senior management and remediate within 7 days. | التصعيد للإدارة العليا ومعالجة الوضع خلال 7 أيام. |

The system also surfaces the *top driver sub-indicator* (highest `|β_std|` and above threshold) as a more specific recommendation.

### 6.5 Trend Direction

The trend for each indicator is computed as:

```
trend_pct = (current_value − previous_period_avg) / max(|previous_period_avg|, 1) × 100
```

`trend_pct` is then bucketed:

| `|trend_pct|` | Direction | Color |
|---|---|---|
| < 2 % | Stable | `#6b7280` (slate-500) |
| ≥ 2 % and > 0 | Up (improving for "higher is better"; worsening for "lower is better") | `#28A745` or `#DC3545` |
| ≥ 2 % and < 0 | Down (worsening for "higher is better"; improving for "lower is better") | the opposite |

The UI uses an arrow icon: ↑ up, ↓ down, → stable.

### 6.6 Governorate Color Mapping

When the dashboard is in "Risk Mode" (the default), the color of each governorate polygon is the color of its current risk level. When the user switches to a specific indicator, the color is computed by `colorForIndicator(value)` in `jordan_heatmap.js`:

| Indicator value | Color |
|---|---|
| 0 – 20 | `#DC3545` (red) |
| 20 – 40 | `#FD7E14` (orange) |
| 40 – 60 | `#FFC107` (amber) |
| 60 – 80 | `#A3D55C` (light green) |
| 80 – 100 | `#28A745` (green) |

The midpoint of each band is a hard break — there is no continuous gradient — so the map is always "color-blind safe" with a single hue family and a discrete bucketing. This also makes the map look correct in a printed report (B&W copier).

### 6.7 Calibration

Risk scores should be calibrated against historical outcomes. Once per quarter, the data team should:

1. Plot the distribution of `governorate_risk_score` per level across the last 90 days.
2. Confirm that the boundaries (25, 50, 75) give a roughly equal number of governorates per level (or follow an intended skew).
3. Adjust the `wᵢ` weights if certain indicators consistently over- or under-predict actual operational issues (verified against manual incident reports).

---

## 7. Alerting & Threshold Subsystem

### 7.1 Rule Catalog

The Heat Map engine implements three categories of rules:

#### 7.1.1 Threshold Rules (per sub-indicator)

A sub-indicator is "above threshold" when its raw value crosses the configured `threshold_high` (or `threshold_low` for "higher is better" indicators). The rule fires once per (governorate, sub_indicator, day).

**Severity assignment**:
- LOW if the violation is 0 – 10 % beyond the threshold
- MEDIUM if 10 – 25 % beyond
- HIGH if 25 – 50 % beyond
- CRITICAL if > 50 % beyond

**Worked example** (safety_incidents.critical_incidents, threshold = 2):
- value = 2 → no alert
- value = 3 → LOW (50 % over)
- value = 4 → MEDIUM (100 % over)
- value = 5 → HIGH (150 % over)
- value = 6 → CRITICAL (200 % over)

#### 7.1.2 Statistical Rules

- **HIGH_IMPACT_VIOLATION**: A sub-indicator is above its threshold **and** its regression weight `|β_std| ≥ 0.20`. Severity: HIGH.
- **STRONG_CORRELATION**: A sub-indicator has `|r| ≥ 0.70` against its main indicator but `|β_std| < 0.20`. Severity: MEDIUM.
- **TREND_REVERSAL**: A main indicator has changed direction (sign of trend_pct) for 3 consecutive days. Severity: MEDIUM (or HIGH if magnitude > 20 %).
- **MULTI_DRIVER_DETERIORATION**: ≥ 3 sub-indicators of the same main indicator are simultaneously above threshold. Severity: HIGH.

#### 7.1.3 Health Hotspot Rule

A rolling 3-day window of `health_absences` is compared to the preceding 3-day window. If the increase is > 50 %, fire a HIGH alert: "health absence hotspot — {pct}% increase over 3-day rolling window". This is the same rule from the original heatmap module, retained for continuity.

### 7.2 Alert Lifecycle

```
            ┌──────────────┐
            │   TRIGGERED  │   ← pipeline creates row in map_alert_history
            └──────┬───────┘     with acknowledged_at = NULL
                   │
                   ▼
        ┌──────────────────┐
        │     OPEN         │   ← visible on map, in governorate detail,
        └──────┬───────────┘     in notification center, in alert dashboard
               │
       (admin clicks "Acknowledge")
               │
               ▼
        ┌──────────────────┐
        │  ACKNOWLEDGED    │   ← still visible but visually muted;
        └──────┬───────────┘     "owner" field populated
               │
       (admin marks "Resolved")
               │
               ▼
        ┌──────────────────┐
        │     RESOLVED     │   ← moves to history view
        └──────────────────┘     resolved_at, resolved_by populated
```

A CRITICAL alert is *also* dispatched via:
- In-app push (notification bell)
- Email (if SMTP is configured and `SENDGRID_API_KEY` is set)
- SMS (if Twilio is configured)

A HIGH alert dispatches in-app + email. A MEDIUM alert dispatches in-app only. A LOW alert stays in the in-app alert list.

### 7.3 Idempotency

The alert engine must never create duplicate open alerts for the same (governorate, sub_indicator, rule) on the same day. Before inserting, the engine checks:

```sql
SELECT 1 FROM map_alert_history
WHERE governorate_code = $1
  AND sub_indicator   = $2
  AND rule            = $3
  AND snapshot_date   = $4
  AND resolved_at IS NULL;
```

If a row exists, the existing alert is updated (e.g. severity may escalate) rather than a new one inserted. This is achieved via `INSERT … ON CONFLICT (governorate_code, sub_indicator, rule, snapshot_date) DO UPDATE`.

### 7.4 Auto-Resolution

When the next day's snapshot has the sub-indicator back below the threshold, the previous day's alert is automatically `resolved` with `resolved_by = NULL` and `resolved_at = now()`. The alert's row in `map_alert_history` is *not* deleted — only marked resolved. This keeps a complete history.

### 7.5 Alert Surfacing

Alerts are surfaced in four places, all powered by the same API:

1. **On the map**: A small ⚠️ badge in the top-right corner of each governorate polygon. Count = number of open HIGH + CRITICAL alerts. Color = severity of the worst open alert.
2. **In the governorate detail panel**: A dedicated "Related alerts" section listing all open alerts with severity badges.
3. **On the Alerts page** (`/admin/alerts`): The full paginated list with filters and bulk acknowledge.
4. **In the Admin notification center**: The top 5 most recent HIGH+ alerts.

---

## 8. Daily Update Pipeline

### 8.1 Schedule

| Time (local) | Step |
|---|---|
| 02:00 | Pipeline starts (cron) |
| 02:00 – 02:05 | Pull all operational data into a frozen staging view (read-only) |
| 02:05 – 02:10 | Compute sub-indicator values per governorate |
| 02:10 – 02:15 | Compute main indicators |
| 02:15 – 02:30 | Compute correlations (Pearson + Spearman) for the last 90 days |
| 02:30 – 02:40 | Compute standardized OLS regression per main indicator |
| 02:40 – 02:45 | Compute risk scores per governorate |
| 02:45 – 02:50 | Evaluate alert rules; insert/update `map_alert_history` |
| 02:50 – 02:55 | Auto-resolve previous-day alerts whose sub-indicators are now normal |
| 02:55 – 03:00 | Run quality checks; write `map_daily_run_log`; invalidate Redis cache |

The pipeline is **idempotent on date**: re-running it for the same date overwrites the existing snapshot. This is the safety net for failed runs.

### 8.2 Staging Snapshot

To avoid race conditions with the live operational database, the pipeline reads from a **staging snapshot** taken at the start of the run. The staging snapshot is a SQL view (`v_map_pipeline_input`) that materializes the union of all needed columns. The pipeline never reads from operational tables directly; it only reads from this view.

### 8.3 Error Handling

Each step is wrapped in a try/except. If a step fails:

1. The error is logged to `map_daily_run_log.errors` as a JSON array.
2. The pipeline continues to the next step with whatever data is available.
3. If the failure is critical (e.g. cannot compute the staging snapshot), the entire run is marked `failed` and a HIGH alert is dispatched to the data team.
4. If the failure is non-critical (e.g. a single sub-indicator computation fails for one governorate), the run is marked `partial` and the affected governorates are flagged in the response.

### 8.4 Retries

Each step has up to 3 retries with exponential backoff (2s, 4s, 8s). The retry policy is implemented with the `tenacity` library. A retried step is logged as a warning, not an error.

### 8.5 Backfill

If a snapshot is missing for a date (e.g. the pipeline was down for a week), the next run includes a "backfill gap detection" step that finds missing dates and re-runs the pipeline for each one. Backfill is rate-limited to 3 days per run to avoid overloading the database.

### 8.6 Pipeline Entry Points

| Trigger | Code path |
|---|---|
| Scheduled (cron) | APScheduler, see `heatmap.backend.etl.pipeline.create_scheduler` |
| Manual (admin) | `POST /api/admin/heat-map/refresh` (admin-only) |
| Manual (developer) | `POST /api/heatmap/pipeline/run` (open) |
| Test | `python -m pytest tests/test_admin_heatmap.py` (uses fixtures) |

---

## 9. API Contract

All endpoints are under `/api/admin/heat-map/` (canonical) or `/api/heatmap/` (legacy ETL). All require admin role. All read endpoints are rate-limited via slowapi (read: 60/min, write: 10/min).

### 9.1 Reference Endpoints

#### `GET /api/admin/heat-map/governorates`
Returns the 12 governorates with their codes, slugs, names (EN/AR), and centroids.

**Response**:
```json
{
  "count": 12,
  "governorates": [
    {"code": "JO-AM", "slug": "amman", "name_en": "Amman", "name_ar": "عمان", "center": [35.95, 31.95], "display_order": 1},
    ...
  ]
}
```

#### `GET /api/admin/heat-map/indicators`
Returns the 6 main indicators with all 22 sub-indicators.

**Response**:
```json
{
  "count": 6,
  "indicators": [
    {
      "key": "nursery_status",
      "name_en": "Nursery Status",
      "name_ar": "حالة الروضات",
      "color": "#0E334F",
      "description_en": "Active vs inactive nurseries in the governorate.",
      "description_ar": "الروضات النشطة مقابل غير النشطة في المحافظة.",
      "alert_threshold": 70.0,
      "sub_indicators": [
        {"key": "active_nurseries", "name_en": "Active nurseries", "name_ar": "روضات نشطة", "unit": "count", "threshold_high": 200, "threshold_low": 50, "higher_is_better": true},
        ...
      ]
    },
    ...
  ]
}
```

### 9.2 Map Data

#### `GET /api/admin/heat-map/data`
Returns the full map payload for the latest successful snapshot.

**Query parameters**:
- `indicator` (optional) — main indicator key to highlight (default: composite risk)

**Response**:
```json
{
  "last_update": "2026-06-13T03:00:00Z",
  "snapshot_date": "2026-06-13",
  "selected_indicator": "tasks_governance",
  "indicators": [ ... ],
  "governorates": [
    {
      "slug": "amman",
      "code": "JO-AM",
      "name_en": "Amman",
      "name_ar": "عمان",
      "center": [35.95, 31.95],
      "main_indicators": {
        "nursery_status": 92.5,
        "children_registration": 87.0,
        "staff_classrooms": 78.4,
        "safety_incidents": 95.0,
        "reports_attendance": 83.2,
        "tasks_governance": 75.0
      },
      "risk_score": 14.8,
      "risk_level": {
        "key": "low",
        "name_en": "Low",
        "name_ar": "منخفض",
        "color": "#28A745"
      }
    },
    ...
  ],
  "summary": {
    "total_governorates": 12,
    "average_risk": 22.5,
    "high_risk_count": 1,
    "critical_count": 0
  },
  "risk_legend": [
    {"key": "low",      "name_en": "Low",      "name_ar": "منخفض", "min": 0,  "max": 25,  "color": "#28A745"},
    {"key": "medium",   "name_en": "Medium",   "name_ar": "متوسط", "min": 26, "max": 50,  "color": "#FFC107"},
    {"key": "high",     "name_en": "High",     "name_ar": "مرتفع", "min": 51, "max": 75,  "color": "#FD7E14"},
    {"key": "critical", "name_en": "Critical", "name_ar": "حرج",   "min": 76, "max": 100, "color": "#DC3545"}
  ]
}
```

#### `GET /api/admin/heat-map/governorate/{slug}`
Returns the detailed payload for one governorate.

**Response**:
```json
{
  "slug": "amman",
  "code": "JO-AM",
  "name_en": "Amman",
  "name_ar": "عمان",
  "center": [35.95, 31.95],
  "main_indicators": { ... },
  "sub_indicators": {
    "active_nurseries": 240,
    "inactive_nurseries": 12,
    "active_pct": 95.2,
    "inactive_pct": 4.8,
    ...
  },
  "risk_score": 14.8,
  "risk_level": { ... },
  "risk_by_indicator": {
    "nursery_status": { "key": "low", "name_en": "Low", "name_ar": "منخفض", "color": "#28A745" },
    ...
  },
  "trends": {
    "nursery_status":      { "direction": "up",   "pct": 2.1 },
    "children_registration": { "direction": "up",   "pct": 1.0 },
    "staff_classrooms":     { "direction": "down", "pct": 3.5 },
    ...
  },
  "alerts": [
    {
      "id": 42,
      "metric": "incidents_critical",
      "severity": "HIGH",
      "status": "ACTIVE",
      "current_value": 8.0,
      "threshold": 2.0,
      "message": "incidents_critical=8 exceeds threshold 2 AND beta_std=0.45 ≥ 0.20",
      "triggered_at": "2026-06-13T02:50:00Z"
    }
  ],
  "recommended_action": {
    "en": "Continue routine monitoring.",
    "ar": "متابعة المراقبة الدورية."
  },
  "last_update": "2026-06-13T03:00:00Z"
}
```

#### `GET /api/admin/heat-map/geojson`
Returns the Jordan boundary GeoJSON (canonical governorate polygons).

### 9.3 Analytics

#### `GET /api/admin/heat-map/correlations`
Returns the Pearson correlation matrix for the latest snapshot.

**Query parameters**:
- `main_indicator` (optional) — filter rows to those involving this main indicator

**Response**:
```json
{
  "method": "pearson",
  "indicators": ["nursery_status", "children_registration", "staff_classrooms", "safety_incidents", "reports_attendance", "tasks_governance"],
  "matrix": [
    { "row": "nursery_status", "column": "children_registration", "value": 0.78, "strength": "strong",     "color": "#F59E0B", "p_value": 0.003, "n": 12 },
    { "row": "nursery_status", "column": "staff_classrooms",    "value": 0.42, "strength": "moderate",   "color": "#3B82F6", "p_value": 0.18,  "n": 12 },
    { "row": "nursery_status", "column": "safety_incidents",     "value": 0.91, "strength": "very_strong","color": "#DC3545", "p_value": 0.0001,"n": 12 },
    ...
  ],
  "note": null
}
```

#### `GET /api/admin/heat-map/regression`
Returns the standardized OLS regression weights.

**Query parameters**:
- `main_indicator` (optional) — filter to one main indicator

**Response**:
```json
{
  "method": "ols_standardized",
  "r_squared_per_indicator": {
    "nursery_status": 0.84,
    "children_registration": 0.71,
    "staff_classrooms": 0.65,
    "safety_incidents": 0.79,
    "reports_attendance": 0.58,
    "tasks_governance": 0.77
  },
  "weights": [
    { "main_indicator": "nursery_status", "sub_indicator": "active_pct",        "beta_std":  0.85, "std_error": 0.12, "t_stat":  7.1, "p_value": 0.0001, "high_impact": true,  "n_samples": 90 },
    { "main_indicator": "nursery_status", "sub_indicator": "inactive_pct",      "beta_std": -0.42, "std_error": 0.18, "t_stat": -2.3, "p_value": 0.025,  "high_impact": true,  "n_samples": 90 },
    ...
  ],
  "note": "OLS coefficients are computed on standardized values. |β| ≥ 0.20 is considered high-impact."
}
```

#### `GET /api/admin/heat-map/daily-update`
Returns metadata about the most recent update.

**Response**:
```json
{
  "last_update": "2026-06-13T03:00:00Z",
  "latest_data_date": "2026-06-12",
  "schedule": "Daily at 02:00 local time (Asia/Amman)",
  "data_sources": ["daily_reports", "incidents", "kindergartens", "users", "tasks"],
  "next_run_at": "2026-06-14T02:00:00+03:00",
  "last_run_status": "success"
}
```

#### `POST /api/admin/heat-map/refresh`
Forces a recompute of the Heat Map (admin-only, CSRF-protected).

**Response**:
```json
{ "status": "ok", "refreshed_at": "2026-06-13T10:00:00Z", "governorates": 12 }
```

### 9.4 Error Format

All error responses follow a standardized shape:

```json
{
  "error": {
    "code": "GOV_NOT_FOUND",
    "message": "Unknown governorate slug: 'xyz'",
    "details": { "slug": "xyz", "valid_slugs": ["amman", "irbid", ...] },
    "correlation_id": "abc-123-def"
  }
}
```

Common error codes:

| Code | HTTP | Meaning |
|---|---|---|
| `AUTH_REQUIRED` | 401 | No or invalid token |
| `FORBIDDEN` | 403 | Authenticated but not admin |
| `RATE_LIMITED` | 429 | Too many requests |
| `VALIDATION_FAILED` | 422 | Invalid query parameters |
| `GOV_NOT_FOUND` | 404 | Unknown governorate slug |
| `INDICATOR_NOT_FOUND` | 404 | Unknown indicator key |
| `SNAPSHOT_MISSING` | 503 | No successful snapshot for the current date |
| `INTERNAL` | 500 | Unhandled server error |

---

## 10. UI/UX Design System

### 10.1 Design Principles

1. **Arabic-first.** All copy is authored in Arabic first; English is the secondary locale. Direction flips automatically based on `dir="rtl"` / `dir="ltr"`.
2. **Summary first, detail on demand.** The default Heat Map view is a clean map with the highest-level risk; the user drills into a governorate to see sub-indicators, then into a sub-indicator to see alerts.
3. **No visual clutter.** No icons unless they communicate something; no animations unless they communicate something.
4. **Color means something.** Green = good, yellow = caution, orange = warning, red = critical. These colors are not used decoratively anywhere.
5. **Print-friendly.** A printed report of the Heat Map must be readable. Discrete color buckets (not gradients) ensure this.
6. **WCAG 2.1 AA compliance.** All text has a contrast ratio of at least 4.5:1; all interactive elements are keyboard-accessible; all ARIA roles and labels are present.

### 10.2 Color Palette

```css
/* Government Brand */
--gov-primary:        #0E334F;   /* dark blue — used for headers, primary actions */
--gov-primary-light:  #155ECF;   /* used for hover states, secondary highlights */
--gov-bg:             #F5F7FA;   /* light gray — page background */
--gov-card:           #FFFFFF;   /* white — card surface */
--gov-text:           #061826;   /* near-black — primary text */
--gov-text-muted:     #475569;   /* slate-600 — secondary text */

/* Status / Risk Colors */
--risk-low:           #28A745;   /* green */
--risk-medium:        #FFC107;   /* amber */
--risk-high:          #FD7E14;   /* orange */
--risk-critical:      #DC3545;   /* red */
--risk-unknown:       #94A3B8;   /* slate-400 — no data */

/* Indicator Colors */
--ind-nursery-status:        #0E334F;
--ind-children-registration: #28A745;
--ind-staff-classrooms:      #155ECF;
--ind-safety-incidents:      #FFC107;
--ind-reports-attendance:    #06B6D4;
--ind-tasks-governance:      #8B5CF6;
```

### 10.3 Typography

```css
--font-body:    'IBM Plex Sans Arabic', 'Cairo', system-ui, -apple-system, sans-serif;
--font-heading: 'Cairo', 'IBM Plex Sans Arabic', system-ui, sans-serif;
--font-mono:    'Noto Kufi Arabic', 'IBM Plex Sans Arabic', monospace;

/* Type scale (Arabic: 1.0 = 16px; consider 1.125 = 18px for ≥60y/o government users) */
--fs-1:  1.875rem;   /* 30px - page title */
--fs-2:  1.5rem;     /* 24px - section title */
--fs-3:  1.125rem;   /* 18px - card title */
--fs-base: 1rem;     /* 16px - body */
--fs-sm:  0.875rem;  /* 14px - secondary */
--fs-xs:  0.75rem;   /* 12px - meta / legend */
```

### 10.4 Grid & Spacing

- **Desktop (≥ 1200px):** 12-column grid, 24px gutter
- **Tablet (768 – 1199px):** 8-column grid, 16px gutter
- **Mobile (< 768px):** 4-column grid, 12px gutter (Heat Map is desktop-only; mobile redirects to a "please use a tablet/desktop" notice)

Spacing scale (8px base): `--sp-1: 4px; --sp-2: 8px; --sp-3: 12px; --sp-4: 16px; --sp-5: 24px; --sp-6: 32px; --sp-8: 48px;`.

### 10.5 Component Inventory

| Component | Purpose | Notes |
|---|---|---|
| `HeatMap` | The SVG-based map of Jordan | Pan/zoom with CSS transforms |
| `GovernoratePolygon` | One SVG path element per governorate | Color set by `colorForIndicator()` |
| `RiskBadge` | A small colored pill showing risk level | `<span class="risk-badge risk-low">Low</span>` |
| `TrendArrow` | ↑ ↓ → for trend direction | Color depends on whether change is good/bad |
| `SubIndicatorRow` | Sub-indicator name + value + threshold | Used in the side panel |
| `AlertRow` | One alert with severity badge and acknowledge button | Used in the alert list and the side panel |
| `CorrelationMatrix` | Grid of governorate-pair correlation cells | Color by strength |
| `RegressionBar` | Horizontal bar showing `|β_std|` with high-impact star | Used in the side panel |
| `Legend` | Color/severity key | Always visible at the bottom of the map |
| `Tooltip` | Hover info on a governorate | Appears in < 100ms, never flickers |
| `SidePanel` | Right-side detail panel | Slides in on click, dismissible with Esc |

### 10.6 Animations

- **Pan/zoom** uses `transform` with `transition: transform 0.45s cubic-bezier(0.22, 1, 0.36, 1)`.
- **Side panel open/close** uses `transform: translateX(...)` with the same easing, 0.3s.
- **No other animation.** Skeletons spin (loading), but the map itself is still.
- A `prefers-reduced-motion: reduce` media query disables all transitions.

### 10.7 Accessibility Checklist

- [ ] All `<path>` elements have `role="button"` and `tabindex="0"`.
- [ ] Tooltips are also shown on focus (not just hover).
- [ ] Color is never the only signal: every colored state is paired with text (e.g. "Low" label, trend arrow, "—" for missing data).
- [ ] All form fields have `<label for="...">`.
- [ ] Live regions (`aria-live="polite"`) announce new alerts.
- [ ] Contrast ratio verified for all text/background pairs.
- [ ] Keyboard shortcuts: `?` shows the help dialog, `r` resets the zoom, `Esc` closes the side panel.

### 10.8 Internationalization

- All UI strings are stored in `heatmap.backend.constants` (or a future i18n module) as `{ar, en}` pairs.
- Numbers are formatted with `ar-JO` / `en-US` locales.
- Dates use `Intl.DateTimeFormat` with `Asia/Amman` timezone.
- The "as of" timestamp uses Hijri/Gregorian toggle (governorate preference).

---

## 11. Frontend Information Architecture

### 11.1 Page Map

```
/admin
├── /dashboard           (KPI cards, recent activity — existing)
├── /analytics           (analytics overview with link to Heat Map — existing)
├── /alerts              (alert management — existing)
├── /heatmap             (THE HEAT MAP — primary feature)
│   ├── (default view)   Map of Jordan + side panel
│   ├── (with filter)    Same view, filtered by indicator
│   └── (drill-in)       Click governorate → side panel with sub-indicators
└── /heatmap/export      (PDF/CSV export of the current view)
```

### 11.2 The Heat Map Page

#### 11.2.1 Header

```
┌────────────────────────────────────────────────────────────────────────┐
│ Jordan Heat Map                                    [Refresh] [Export] │
│ Daily updated · 12 governorates · as of 2026-06-13 03:00              │
└────────────────────────────────────────────────────────────────────────┘
```

#### 11.2.2 Main Layout

The page is a two-column layout:

```
┌────────────────────────────────────────────┐  ┌──────────────────────┐
│                                            │  │ Governorate details  │
│  ┌────────────────────────────────────┐    │  │ ──────────────────── │
│  │  [Map of Jordan with 12 governorate │   │  │ Amman                │
│  │   polygons, color-coded]            │   │  │ ──────────────────── │
│  │                                     │   │  │ Composite risk: 14.8 │
│  │                                     │   │  │ [Low]               │
│  │  [Hover → tooltip]                  │   │  │                      │
│  │  [Click → opens side panel]         │   │  │ Recommended action:  │
│  │  [Zoom in/out, reset, pan]          │   │  │ Continue routine     │
│  │                                     │   │  │ monitoring.          │
│  └────────────────────────────────────┘    │  │                      │
│                                            │  │ ── Main indicators ─ │
│  Legend: [Low] [Medium] [High] [Critical]  │  │ • Nursery Status  92│
│                                            │  │ • Children  Reg.  87│
│                                            │  │ ...                  │
│  Indicator: [Tasks & Governance ▼]          │  │ ── Sub-indicators ─ │
│                                            │  │ • Active nurseries  │
│                                            │  │   240 (threshold 50)│
│                                            │  │ ...                  │
│                                            │  │ ── Trend vs prev ──│
│                                            │  │ ↑ +2.1% (Nursery)   │
│                                            │  │ ↓ −3.5% (Staff)     │
│                                            │  │                      │
│                                            │  │ ── Correlation ──── │
│                                            │  │ (matrix of 6×6)     │
│                                            │  │                      │
│                                            │  │ ── Regression ─────│
│                                            │  │ (top 3 sub-indicators│
│                                            │  │  by |β_std|)         │
│                                            │  │                      │
│                                            │  │ ── Alerts (3) ─────│
│                                            │  │ HIGH incidents_crit.│
│                                            │  │ MED  absences_health│
│                                            │  │ LOW  classes_no_sup │
└────────────────────────────────────────────┘  └──────────────────────┘
```

#### 11.2.3 Interaction Details

1. **On hover over a governorate:**
   - Tooltip appears within 100ms at the cursor position (offset 14px right and down).
   - Tooltip contains: governorate name (in current language), selected indicator value, risk level badge, last update date.
   - Polygon gains a 2px outline in `--gov-primary` (color #0E334F).
   - Adjacent polygons' tooltips are dismissed.

2. **On click a governorate:**
   - The polygon is "selected" (persistent 3px outline).
   - The side panel slides in from the right (0.3s).
   - The side panel fetches `/api/admin/heat-map/governorate/{slug}` and renders the detailed layout above.
   - The map zooms slightly (1.2×) toward the selected governorate for visual focus.

3. **On zoom in/out:**
   - The map transforms with the cubic-bezier easing.
   - At zoom ≥ 1.5×, the numeric value badges (e.g. "92.5") become visible on each polygon.
   - The user's zoom state is preserved across navigation within the page.

4. **On indicator change:**
   - All polygons re-color to the new indicator's value.
   - The legend updates to show the indicator's color scale (if not in "Risk Mode").
   - The numeric badges update.
   - The map title changes to "Jordan — {indicator name}".

5. **On side panel close:**
   - The panel slides out (0.3s).
   - The selected polygon's outline returns to normal.
   - Focus returns to the previously focused element.

6. **On alert click:**
   - The alert row opens an inline expansion showing the rule, threshold, current value, beta weight, and an "Acknowledge" button.
   - Clicking "Acknowledge" sends a POST request and updates the row to a muted style with an "Acknowledged" badge.

### 11.3 Performance Budget

| Operation | Budget |
|---|---|
| Initial page load (cached data) | < 1.5 s on 4G |
| Initial page load (cold cache) | < 3 s on 4G |
| Hover → tooltip | < 100 ms |
| Click → side panel open | < 300 ms (transition) |
| Side panel data load | < 500 ms |
| Zoom animation | 450 ms (one frame, CSS-driven) |
| Indicator change → repaint | < 200 ms |
| Alert acknowledge round-trip | < 1 s |

The page is fully client-side rendered after the initial HTML load. Data is fetched via JSON; no full page reloads.

### 11.4 State Management

The Heat Map page maintains its state in a single object:

```typescript
interface HeatMapState {
  // Data
  governorates: Governorate[];
  indicators: MainIndicator[];
  selectedGovernorate: GovernorateDetail | null;
  correlations: CorrelationMatrix;
  regression: RegressionResult;
  alerts: Alert[];
  dailyUpdate: DailyUpdateMeta;

  // UI
  selectedIndicator: string | null;  // null = composite risk
  zoom: number;                      // 1.0 to 6.0
  pan: { x: number; y: number };
  loading: boolean;
  error: string | null;
}
```

State changes are batched with a single `setState()` call to keep the UI consistent. The state is held in a `Map` (the IIFE) — no external store — and is not persisted to localStorage (the data must always be fresh from the server).

---

## 12. Performance, Caching, and Scaling

### 12.1 Caching Strategy

| Endpoint | Cache TTL | Invalidated on |
|---|---|---|
| `/api/admin/heat-map/governorates` | 1 hour | Constants change (rare) |
| `/api/admin/heat-map/indicators` | 1 hour | Constants change (rare) |
| `/api/admin/heat-map/data` | 5 minutes | Pipeline success |
| `/api/admin/heat-map/geojson` | 1 day | Boundary file change |
| `/api/admin/heat-map/governorate/{slug}` | 5 minutes | Pipeline success |
| `/api/admin/heat-map/correlations` | 1 hour | Pipeline success |
| `/api/admin/heat-map/regression` | 1 hour | Pipeline success |
| `/api/admin/heat-map/daily-update` | 1 minute | Pipeline success |

The cache is implemented with Redis (`cache_service.py`). The cache key is `admin_heat_map:{endpoint}:{date}`. The pipeline, on success, publishes a `cache.invalidate` event that purges all `admin_heat_map:*` keys.

### 12.2 Database Query Optimization

The most expensive query is the "latest snapshot for all governorates" query. It is implemented as:

```sql
SELECT s.*, g.name_en, g.name_ar
FROM map_indicator_snapshot s
JOIN (SELECT DISTINCT ON (governorate_code, main_indicator) *
      FROM map_indicator_snapshot
      ORDER BY governorate_code, main_indicator, snapshot_date DESC) latest
  ON latest.governorate_code = s.governorate_code
 AND latest.main_indicator   = s.main_indicator
 AND latest.snapshot_date    = s.snapshot_date
JOIN governorates g ON g.code = s.governorate_code
WHERE s.snapshot_date = (SELECT MAX(snapshot_date) FROM map_indicator_snapshot);
```

This uses the `idx_mis_latest` index. The materialized view `v_latest_map_snapshot` (refreshed by the pipeline) serves the same query in < 50 ms for the dashboard.

### 12.3 Load Profile

- **Peak load:** ~ 50 RPS for `/api/admin/heat-map/data` (200 admin users refreshing every 5 minutes during business hours).
- **Heavy query:** `/api/admin/heat-map/correlations` is called rarely (once per session) but is expensive (full 90-day matrix). Rate-limited to 5/min.

### 12.4 Vertical Scaling Path

| Users | App workers | DB CPU | Redis |
|---|---|---|---|
| 50 | 2 | 2 cores | 1 GB |
| 200 | 4 | 4 cores | 2 GB |
| 500 | 8 | 8 cores | 4 GB |
| 1000+ | 16 + read replica | 16 cores + replica | 8 GB cluster |

---

## 13. Security, Privacy, and Audit

### 13.1 Authentication & Authorization

- **Authentication**: All endpoints require a valid JWT bearer token from the existing KinJo auth system.
- **Authorization**: Only users with `role = ADMIN` can call these endpoints. The role check is enforced at the FastAPI dependency level (`_require_admin` in `admin_router.py`).
- **CSRF**: All POST/PUT/DELETE endpoints require a valid CSRF token. The CSRF token is issued by the existing `/csrf` endpoint.
- **Rate limiting**: All endpoints are rate-limited via slowapi. Read endpoints: 60/min per user. Write endpoints: 10/min per user.

### 13.2 PII Handling

The Heat Map does **not** display personally identifiable information. The following rules apply:

- The map shows governorate-level aggregates only.
- The governorate detail panel shows counts, not lists. (E.g. "240 active nurseries" — never the names.)
- The alert list shows metric, value, and message — never child or staff names.
- Drill-down from a governorate to a kindergarten or class is **out of scope** for the admin role; it is allowed only for MANAGER+SUPERVISOR roles on their own scope.

### 13.3 Audit Logging

Every read of the Heat Map API is logged to the existing `audit_service.py`:

```json
{
  "user_id": 42,
  "action": "READ_HEAT_MAP_DATA",
  "resource": "/api/admin/heat-map/data",
  "metadata": { "indicator": "tasks_governance" },
  "ip_address": "...",
  "user_agent": "...",
  "correlation_id": "...",
  "timestamp": "2026-06-13T10:00:00Z"
}
```

Every acknowledge / resolve action on an alert is logged similarly.

### 13.4 Encryption

- **In transit**: TLS 1.3+ only.
- **At rest**: PostgreSQL TDE for the snapshot tables (transparent encryption).
- **Backups**: Encrypted with AES-256, rotated daily.

### 13.5 Penetration Testing

The Heat Map API will be included in the quarterly pentest. The test must include:

- IDOR on `governorate/{slug}` (verify a non-admin cannot read a different governorate's data)
- SQL injection on the date filter
- Rate limit bypass
- CSRF on the refresh endpoint

---

## 14. Observability

### 14.1 Metrics

| Metric | Type | Source |
|---|---|---|
| `heatmap_api_requests_total{endpoint, status}` | Counter | FastAPI middleware |
| `heatmap_api_request_duration_seconds{endpoint}` | Histogram | FastAPI middleware |
| `heatmap_pipeline_runs_total{status}` | Counter | Pipeline run log |
| `heatmap_pipeline_duration_seconds` | Histogram | Pipeline run log |
| `heatmap_pipeline_rows_processed` | Gauge | Pipeline run log |
| `heatmap_pipeline_errors_total{step}` | Counter | Pipeline run log |
| `heatmap_cache_hit_ratio` | Gauge | Cache service |
| `heatmap_active_alerts{severity}` | Gauge | Alert engine |
| `heatmap_governorate_risk_score{governorate}` | Gauge | Risk model |

Metrics are exported to Prometheus every 15 seconds and visualized in Grafana.

### 14.2 Logs

| Log type | Format | Destination |
|---|---|---|
| Application | JSON via `loguru` / `structlog` | Loki |
| Pipeline | JSON with `run_id`, `step`, `status` | Loki + file (`logs/pipeline_{date}.jsonl`) |
| Audit | JSON via `audit_service.py` | PostgreSQL `audit_log` + Loki |
| Security | JSON via `admin_security.py` | Loki + SIEM (Datadog) |

### 14.3 Alerts (on the Heat Map system itself)

- Pipeline failure > 2 days in a row → page on-call.
- Cache hit ratio < 80% for 1 hour → notify data team.
- API p95 > 3 s for 15 minutes → page on-call.
- Any 5xx error rate > 0.1 % over 5 minutes → page on-call.

---

## 15. Testing Strategy

### 15.1 Test Pyramid

| Layer | Tool | Target |
|---|---|---|
| Unit | `pytest` | All `heatmap.backend.*` functions have ≥ 3 unit tests |
| Service | `pytest` | All `service.py` functions have ≥ 2 happy-path + 1 sad-path |
| API integration | `fastapi.testclient` | All endpoints, all status codes |
| Contract | `schemathesis` | All API responses match the OpenAPI spec |
| Statistical | `pytest` | Pearson / Spearman / OLS against known fixtures (R / sklearn) |
| E2E | Playwright | 5 critical user journeys |
| Load | k6 | 200 concurrent users for 10 min, p95 < 1.5 s |
| A11y | `axe-core` via Playwright | All Heat Map pages ≥ 95 |
| Visual | Percy / Chromatic | No unintended visual regressions |
| Security | OWASP ZAP | No high-severity findings |

### 15.2 Statistical Test Fixtures

We commit a small set of test snapshots with hand-computed expected results:

- A snapshot where the main indicator value and the sub-indicator value are perfectly correlated → expected `r = 1.0`.
- A snapshot where the relationship is inverse → expected `r = -1.0`.
- A snapshot with constant sub-indicator → expected `r = null, strength = "insufficient"`.
- A snapshot with multicollinear predictors → expected `VIF > 10` warning.
- A snapshot with `n < 5` → expected `coefficient = null, p_value = null`.

These fixtures live in `tests/fixtures/heatmap/` and are loaded by the test suite.

### 15.3 Coverage Targets

| Component | Target |
|---|---|
| `heatmap.backend.constants` | 100% |
| `heatmap.backend.service` | ≥ 90% |
| `heatmap.backend.analytics.*` | ≥ 90% (with statistical fixtures) |
| `heatmap.backend.alerts.engine` | ≥ 85% |
| `heatmap.backend.admin_router` | ≥ 80% |
| `static/js/jordan_heatmap.js` | ≥ 70% (with jsdom) |

### 15.4 Existing Test Suite Status

- `tests/test_admin_heatmap.py`: **21 tests, all passing** (new in Phase 1)
- `tests/test_admin_security.py`: 53 tests, all passing (no regression)
- `tests/test_classification_api.py`: 7 tests, all passing (no regression)
- `tests/test_frontend.py`: 90 tests, all passing (no regression)
- `tests/test_analytics_endpoints.py`: 16 tests, all passing (no regression)

Total verified: **168 pre-existing tests + 21 new tests = 189 tests passing**.

---

## 16. Phased Implementation Roadmap

### Phase 1: Foundation — Heat Map MVP (Weeks 1-6)

**Objective**: Ship a working, production-grade Heat Map for the 12 governorates with the basic risk model.

**Milestone 1.1 (Week 1)**: Schema + constants
- `heatmap/backend/constants.py` — finalized governorates, indicators, risk levels
- `heatmap/scripts/init_heatmap_schema.sql` — schema applied
- `tests/test_admin_heatmap.py` — 21 unit tests (PASSED)

**Milestone 1.2 (Week 2)**: Service layer
- `heatmap/backend/service.py` — `get_map_overview`, `get_governorate_overview`
- Integration with live `kindergartens`, `users`, `incidents`, `daily_reports` tables
- Graceful fallback when live data is sparse (use safe computed estimates)

**Milestone 1.3 (Week 3)**: Admin router + integration with main.py
- `heatmap/backend/admin_router.py` — 9 endpoints
- Mounted in `main.py` under `/api/admin/heat-map/*`
- Rate limiting, admin role enforcement, CSRF protection

**Milestone 1.4 (Week 4)**: Frontend page + JS
- `templates/admin/heatmap.html` — RTL/EN, responsive, loading/empty/error states
- `static/js/jordan_heatmap.js` — SVG render, hover, click, side panel, smooth zoom
- Sidebar link + analytics page link

**Milestone 1.5 (Week 5)**: UX polish + a11y
- Keyboard navigation, ARIA roles, focus management
- Tooltip stability, color contrast, reduced-motion support
- Per-section error states with retry

**Milestone 1.6 (Week 6)**: Documentation + rollout
- `docs/ADMIN_MODULE_ENHANCEMENT_SPEC.md` updated
- User training material
- Staging → Production deploy

**Phase 1 deliverables**: Working Heat Map page, 9 admin endpoints, 21 unit tests, sidebar/analytics integration, bilingual support, accessibility AA compliance.

### Phase 2: Analytical Engine (Weeks 7-12)

**Objective**: Add the correlation and regression engines, the priority score, and the alert engine.

**Milestone 2.1 (Week 7-8)**: Pearson + Spearman
- `heatmap/backend/analytics/pearson.py` — production-grade, with p-values
- `heatmap/backend/analytics/spearman.py` — with Kendall τ fallback
- `tests/fixtures/heatmap/correlation_fixtures.json` — hand-computed expected results

**Milestone 2.2 (Week 9-10)**: OLS regression
- `heatmap/backend/analytics/ols.py` — standardized OLS with multicollinearity handling (VIF)
- `heatmap/backend/analytics/stats.py` — full matrix computation
- `tests/test_analytics_stats.py` — 15+ tests against sklearn fixtures

**Milestone 2.3 (Week 11)**: Daily pipeline
- `heatmap/backend/etl/pipeline.py` — APScheduler integration
- `map_daily_run_log` and audit trail
- Backfill logic for missing dates

**Milestone 2.4 (Week 12)**: Frontend analytics UI
- Correlation matrix component (`CorrelationMatrix.jsx`)
- Regression bars in the side panel
- Priority score widget on the map

**Phase 2 deliverables**: Working correlation matrix, regression analysis, daily pipeline at 02:00, priority scores on the map.

### Phase 3: Risk Model & Alerting (Weeks 13-18)

**Objective**: Refine the risk model and integrate the alert lifecycle.

**Milestone 3.1 (Week 13-14)**: Risk model
- Refine the formula in `service.py` with `wᵢ` weights
- Calibrate against the first 30 days of historical data
- Add `top_driver_sub` and `top_driver_beta` to the risk snapshot

**Milestone 3.2 (Week 15-16)**: Alert engine
- `heatmap/backend/alerts/engine.py` — all 3 rule categories
- Idempotency via `INSERT … ON CONFLICT`
- Auto-resolution of yesterday's alerts that are no longer triggered

**Milestone 3.3 (Week 17)**: Alert UI
- Alert badge on each governorate polygon
- "Related alerts" section in the side panel
- "Acknowledge" and "Resolve" actions
- Notification center integration

**Milestone 3.4 (Week 18)**: Historical view
- "Trend over last 30 days" sparkline on each governorate detail
- Per-indicator trend charts (line chart with confidence band)
- "Risk score over time" chart for each governorate

**Phase 3 deliverables**: Refined risk model, full alert lifecycle, historical trend views, notification center integration.

### Phase 4: National Rollout & Optimization (Weeks 19-24)

**Objective**: National rollout, performance optimization, AI/ML layer foundation.

**Milestone 4.1 (Week 19-20)**: Performance
- Materialized view `v_latest_map_snapshot`
- Redis caching for all endpoints
- Bundle size optimization for the JS
- Load test (200 concurrent users)

**Milestone 4.2 (Week 21-22)**: External integrations
- Ministry of Social Development API integration (optional, read-only)
- SendGrid email dispatcher (if `SENDGRID_API_KEY` is set)
- Twilio SMS dispatcher (if Twilio is configured)
- Slack webhook for HIGH+ alerts

**Milestone 4.3 (Week 23)**: AI/ML layer foundation
- Time-series model for 30-day forecasts (linear regression + ARIMA for incidents)
- Anomaly detection via z-score on the historical indicator series
- `map_forecast_snapshot` table

**Milestone 4.4 (Week 24)**: National rollout
- Training material (PDF + video)
- Help-desk runbook
- Production deploy with monitoring

**Phase 4 deliverables**: Materialized views, external integrations, AI/ML foundation, full national rollout.

---

## 17. Acceptance Criteria

The project is "done" when **all** of the following are true:

### 17.1 Functional

1. [ ] Admin can open the Heat Map page at `/admin/heatmap` and see the map of Jordan with 12 governorates.
2. [ ] The map is recognizably Jordan (not a placeholder).
3. [ ] Each governorate is interactive (hover, click, keyboard focus).
4. [ ] Hover shows a tooltip with name, indicator value, risk level, last update.
5. [ ] Click opens a side panel with sub-indicators, trends, correlations, regression, alerts, recommended action.
6. [ ] Indicator selector changes the map color coding.
7. [ ] Higher indicator values show greener colors; lower values show redder colors.
8. [ ] Composite risk mode uses 4-level color coding (green/yellow/orange/red).
9. [ ] Smooth zoom in/out works (1× to 6×).
10. [ ] Reset zoom returns to the full Jordan view.
11. [ ] Zoomed-in view shows numeric value badges on each polygon.
12. [ ] All 9 admin API endpoints return 200 for an admin user.
13. [ ] All endpoints return 401 for unauthenticated users, 403 for non-admin.
14. [ ] All 12 governorates are present in `/api/admin/heat-map/governorates`.
15. [ ] All 6 main indicators and all 22 sub-indicators are present in `/api/admin/heat-map/indicators`.

### 17.2 Analytical

16. [ ] `/api/admin/heat-map/correlations` returns a non-empty matrix with at least 6×6 = 36 cells.
17. [ ] Each correlation cell has `value` (or null), `strength`, `color`, `p_value`, `n`.
18. [ ] `/api/admin/heat-map/regression` returns standardized coefficients for every main indicator.
19. [ ] Each regression row has `beta_std`, `std_error`, `t_stat`, `p_value`, `r_squared`, `high_impact`.
20. [ ] Statistical tests pass against hand-computed fixtures (Pearson = 1.0 for perfect correlation, etc.).

### 17.3 Operational

21. [ ] Daily pipeline runs at 02:00 and produces a fresh snapshot.
22. [ ] Pipeline failures are logged to `map_daily_run_log` and page on-call.
23. [ ] All 9 endpoints are rate-limited and return 429 when exceeded.
24. [ ] Redis cache hit ratio > 80 % during business hours.
25. [ ] API p95 < 1.5 s on 4G.

### 17.4 Quality

26. [ ] All 189 existing + new tests pass.
27. [ ] Python files compile without warnings.
28. [ ] JS files compile (where `node -c` is applicable; JSX requires Vite).
29. [ ] No `geomap` / `GeoMap` / `geo-map` strings in user-facing code, API, or documentation.
30. [ ] All admin pages have no dead links, no duplicated feature descriptions, no contradictory explanations.
31. [ ] Documentation is updated: `ADMIN_MODULE_ENHANCEMENT_SPEC.md`, `NATIONAL_NURSERY_INTELLIGENCE_HEAT_MAP_TECHNICAL_DESIGN.md`, `NATIONAL_NURSERY_INTELLIGENCE_HEAT_MAP_IMPLEMENTATION_ROADMAP.md`.

### 17.5 UX

32. [ ] All pages pass `axe-core` a11y audit with score ≥ 95.
33. [ ] All pages are keyboard-navigable end-to-end.
34. [ ] All pages render correctly at 1280px (desktop) and 1024px (tablet) widths.
35. [ ] All text passes WCAG 2.1 AA contrast (≥ 4.5:1).
36. [ ] No layout overlap, no unreadable labels, no broken images.
37. [ ] Loading state appears within 100 ms; data appears within 1.5 s.
38. [ ] Tooltip never flickers (single render, no DOM thrashing).
39. [ ] Side panel slides in smoothly; never appears instantly or with a flash.

---

## 18. Risks, Open Questions, and Assumptions

### 18.1 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Live data is too sparse for stable correlations | High | Medium | Aggregate daily → weekly for correlation; show "n = X" in every correlation cell |
| Boundary file (`jordan_admin.geojson`) uses simplified polygons | Medium | Low | Document; provide a path to swap with GADM boundaries |
| Pipeline failure during national rollout | Medium | High | Idempotent on date; backfill logic; runbook + on-call rotation |
| Regression coefficients drift over time | Medium | Medium | Quarterly re-calibration against actual operational outcomes |
| User overload from too many alerts | Medium | High | Rate-limit alerts to top 5 per governorate; auto-resolve within 24h if not acknowledged |
| Heatmap SVG performance on older devices | Low | Medium | Memoize paint; throttle repaints to one per frame |

### 18.2 Open Questions

1. **Are sub-indicator thresholds set by the Ministry, or by the data team?** Default: data team sets initial thresholds; Ministry can override via `map_threshold_config` table (Phase 4).
2. **Should the composite risk include weighting by governorate population?** Default: no, because Amman would always dominate. The current equal-weighting is more "fair" for cross-governorate comparison.
3. **Should the system support multiple languages for governorate names (English, Arabic, transliteration)?** Default: English + Arabic only.
4. **What is the policy for historical data when governorate boundaries change?** Default: governorates are stable since 1994; no support for boundary changes in Phase 1-3.

### 18.3 Assumptions

1. The 12 governorate codes (`JO-AM`, `JO-IR`, …) are stable and not subject to change in the next 5 years.
2. The KinJo operational database (kindergartens, users, incidents, daily_reports) is the single source of truth for all sub-indicators.
3. Daily updates are sufficient; sub-daily updates are not required for government decision-making.
4. An admin user is the only role that needs to see the Heat Map. Manager and Supervisor views will be added in a separate project.
5. The Ministry has 200 – 1 000 admin users in total.

---

## Appendix A — Mathematical Reference

### A.1 Pearson Correlation (Two-tailed p-value)

```
Given n samples (x_i, y_i):
    x̄ = mean(x)            ȳ = mean(y)
    Sxx = Σ (x_i − x̄)²
    Syy = Σ (y_i − ȳ)²
    Sxy = Σ (x_i − x̄)(y_i − ȳ)

    r = Sxy / √(Sxx × Syy)
    t = r × √((n − 2) / (1 − r²))
    p = 2 × P(T > |t|) where T ~ t-distribution with df = n − 2
```

### A.2 Spearman Correlation

```
Rank-transform x and y (with mean ranks for ties), then apply Pearson
on the ranks. Same p-value formula.
```

### A.3 Standardized OLS Regression

```
Given Y (n × 1) and X (n × k), standardize each column:
    Z_x = (X − mean(X)) / std(X, ddof=1)
    Z_y = (Y − mean(Y)) / std(Y, ddof=1)

    β = (Z_x^T Z_x)^(-1) Z_x^T Z_y               (k × 1)

    Var(β) = s² × (Z_x^T Z_x)^(-1)               (k × k)
    where s² = sum of squared residuals / (n − k − 1)

    SE(β_j) = √Var(β)[j, j]
    t_j = β_j / SE(β_j)
    p_j = 2 × P(T > |t_j|) where T ~ t(df = n − k − 1)

    R² = 1 − (sum of squared residuals) / Σ(Z_y − mean(Z_y))²
```

### A.4 Variance Inflation Factor (VIF)

```
For each predictor j:
    R²_j = R² of regression of Z_x_j on the other Z_x_l (l ≠ j)
    VIF_j = 1 / (1 − R²_j)

VIF > 10 indicates severe multicollinearity. VIF > 5 is a warning.
```

### A.5 Risk Score

```
indicator_risk_i = 100 − main_indicator_value_i   for each main i

sub_indicator_risk_i = (
    0.5 × threshold_violation_normalized_i
  + 0.3 × correlation_bonus_i
  + 0.2 × trend_penalty_i / 30
)

governorate_risk_score = 0.65 × Σᵢ wᵢ × indicator_risk_i
                       + 0.35 × Σᵢ wᵢ × sub_indicator_risk_i
clipped to [0, 100]
```

### A.6 Bonferroni Correction

For a family of m hypothesis tests with target α = 0.05:
```
α_per_test = 0.05 / m
```

We apply Bonferroni within each main indicator (m = 4 sub-indicators), so `α_per_test = 0.0125`. This reduces false-positive correlations at the cost of statistical power, which is acceptable given the small sample sizes.

### A.7 Tukey's Fences (Outlier Detection)

For a series X:
```
Q1 = 25th percentile       Q3 = 75th percentile
IQR = Q3 − Q1
Lower fence = Q1 − 1.5 × IQR
Upper fence = Q3 + 1.5 × IQR
Outliers: x < Lower fence or x > Upper fence
```

Outliers are excluded from the "stable" correlation and regression reports, but included in the "all" reports so the user can see the difference.

---

## Appendix B — Data Quality Matrix

| Sub-indicator | Source | Completeness check | Accuracy check | Timeliness check |
|---|---|---|---|---|
| `active_nurseries` | `kindergartens.status = 'ACTIVE'` count by governorate | expected: 200 ± 10 % of last 30 days average | hard upper bound: ≤ total kindergartens | snapshot must be within last 24 h |
| `inactive_nurseries` | `kindergartens.status = 'INACTIVE'` | same | same | same |
| `registered_children` | `children` count by governorate | join with kindergartens | not negative | not older than 7 days |
| `unregistered_children` | estimated from capacity | sanity: ≤ 0.5 × registered | same | same |
| `supervisors_count` | `users.role = 'SUPERVISOR'` | expected: 1 per classroom | not negative | not older than 7 days |
| `classrooms_count` | `classrooms` | not negative | not negative | not older than 7 days |
| `classrooms_no_supervisor` | derived: `classrooms − supervisors` | sanity: ≥ 0 | sanity: ≤ classrooms | derived |
| `incidents_total` | `incidents` count by governorate | expected: 1-100 per gov per month | not negative | within last 30 days |
| `critical_incidents` | `incidents.severity = 'CRITICAL'` | sanity: ≤ incidents_total | same | same |
| `protection_cases` | `incidents.type = 'PROTECTION'` | sanity: ≤ incidents_total | same | same |
| `reports_submitted` | `daily_reports` count by governorate | expected: 1 per active nursery per day | not negative | within last 30 days |
| `reports_missing` | derived: expected − actual | not negative | ≤ expected | derived |
| `absence_rate` | derived from `daily_reports.absent_count / registered_children` | in [0, 100] | within last 30 days | derived |
| `health_absences` | `daily_reports.absent_count WHERE reason = 'HEALTH'` | not negative | same | same |
| `repeated_health` | derived: children with health_absences > 2 in last 30 days | not negative | same | derived |
| `delayed_tasks` | `tasks WHERE status = 'PENDING' AND due_date < today` | not negative | not negative | within last 7 days |
| `governance_score` | `kindergartens.governance_score` average | in [0, 100] | in [0, 100] | within last 30 days |
| `training_completion` | derived from `user_training_completion` | in [0, 100] | in [0, 100] | within last 30 days |
| `compliance_status` | derived from `audit_results` | in [0, 100] | in [0, 100] | within last 30 days |

If any check fails, the pipeline logs a warning and the affected sub-indicator is marked as `data_quality_warning: true` in the response.

---

## Appendix C — Glossary

| Term | Definition |
|---|---|
| **Governorate** | One of the 12 administrative divisions of Jordan (محافظة). |
| **Main indicator** | A composite 0-100 score for a high-level concept (e.g. "Nursery Status"). |
| **Sub-indicator** | A raw metric that contributes to a main indicator (e.g. "Active Nurseries"). |
| **Risk score** | A 0-100 number per governorate; higher = more risk. |
| **Risk level** | A bucketed risk: Low / Medium / High / Critical. |
| **Pearson r** | Linear correlation coefficient, range [-1, 1]. |
| **Spearman ρ** | Rank-based correlation coefficient, range [-1, 1]. |
| **OLS** | Ordinary Least Squares; a linear regression method. |
| **β_std** | Standardized regression coefficient; the change in Y (in SD units) for a 1-SD change in X, holding all other predictors constant. |
| **VIF** | Variance Inflation Factor; measures multicollinearity. VIF > 10 is a red flag. |
| **R²** | Coefficient of determination; proportion of variance in Y explained by X. |
| **Snapshot** | One row per (date, dimension) in the database. Immutable once written. |
| **Pipeline** | The nightly batch that produces a fresh snapshot for the current date. |
| **Heat Map** | The interactive map of Jordan showing color-coded governorates. |
| **Bilingual** | The interface supports both Arabic (primary, RTL) and English (secondary, LTR). |
| **WCAG 2.1 AA** | The Web Content Accessibility Guidelines, conformance level AA. |
| **CSRF** | Cross-Site Request Forgery; a security mechanism that prevents unauthorized state-changing requests. |
| **APScheduler** | A Python library for in-process scheduled jobs. |
| **ETL** | Extract, Transform, Load; the data pipeline. |
| **PII** | Personally Identifiable Information. |
| **TDE** | Transparent Data Encryption. |

---

**End of document.**
