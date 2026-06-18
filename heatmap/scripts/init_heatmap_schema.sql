-- PostgreSQL / PostGIS schema for heatmap indicators
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS heatmap_indicators (
    id                          SERIAL PRIMARY KEY,
    date                        DATE         NOT NULL,
    admin_id                    VARCHAR(20)  NOT NULL,
    -- raw sub-indicators
    kindergartens_active        INTEGER      NOT NULL DEFAULT 0,
    kindergartens_inactive      INTEGER      NOT NULL DEFAULT 0,
    enrolled_children           INTEGER      NOT NULL DEFAULT 0,
    unregistered_children       INTEGER      NOT NULL DEFAULT 0,
    supervisors_count           INTEGER      NOT NULL DEFAULT 0,
    classes_count               INTEGER      NOT NULL DEFAULT 0,
    classes_without_supervisor  INTEGER      NOT NULL DEFAULT 0,
    critical_incidents          INTEGER      NOT NULL DEFAULT 0,
    protection_issues           INTEGER      NOT NULL DEFAULT 0,
    daily_reports_count         INTEGER      NOT NULL DEFAULT 0,
    absences_total              INTEGER      NOT NULL DEFAULT 0,
    absences_health_alerts      INTEGER      NOT NULL DEFAULT 0,
    tasks_overdue               INTEGER      NOT NULL DEFAULT 0,
    governance_score            NUMERIC(5,2) NOT NULL DEFAULT 0,
    training_completion_pct     NUMERIC(5,2) NOT NULL DEFAULT 0,
    -- composite indicators (0-100)
    kindergarten_status         NUMERIC(6,2),
    children_enrollment         NUMERIC(6,2),
    staff_classrooms            NUMERIC(6,2),
    safety_incidents            NUMERIC(6,2),
    reports_attendance          NUMERIC(6,2),
    tasks_governance            NUMERIC(6,2),
    -- audit
    ingested_at                 TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (date, admin_id)
);

CREATE INDEX IF NOT EXISTS idx_heatmap_date     ON heatmap_indicators (date);
CREATE INDEX IF NOT EXISTS idx_heatmap_admin_id ON heatmap_indicators (admin_id);

CREATE TABLE IF NOT EXISTS heatmap_alerts (
    id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    severity     VARCHAR(10)  NOT NULL,
    admin_id     VARCHAR(20)  NOT NULL,
    rule         VARCHAR(80)  NOT NULL,
    message      TEXT         NOT NULL,
    meta         JSONB        DEFAULT '{}',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    acknowledged BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS heatmap_stats (
    id               SERIAL PRIMARY KEY,
    computed_at      DATE         NOT NULL,
    main_indicator   VARCHAR(40)  NOT NULL,
    sub_indicator    VARCHAR(60)  NOT NULL,
    pearson_r        NUMERIC(8,4),
    p_value          NUMERIC(10,6),
    strong_correlation BOOLEAN,
    beta_std         NUMERIC(8,4),
    se               NUMERIC(8,4),
    t_stat           NUMERIC(8,4),
    ols_p_value      NUMERIC(10,6),
    high_impact      BOOLEAN,
    UNIQUE (computed_at, main_indicator, sub_indicator)
);
