-- ===========================================================================
-- Jordan Heat Map — daily snapshot schema
-- Reference: docs/JORDAN_HEAT_MAP_TECHNICAL_SPECIFICATION.md §4.3
--
-- These tables back the Admin Heat Map dashboard.  Every read returns the
-- *most recent successful snapshot*.  Snapshots are immutable once written;
-- to "correct" a snapshot the pipeline writes a new row for the same date
-- (idempotent upsert).
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. Indicator snapshot (one row per date × governorate × main indicator)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_indicator_snapshot (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,
    main_indicator    VARCHAR(40)  NOT NULL,
    value             NUMERIC(6,2) NOT NULL CHECK (value BETWEEN 0 AND 100),
    previous_value    NUMERIC(6,2),
    trend_pct         NUMERIC(6,2),
    sample_size       INTEGER      NOT NULL DEFAULT 0,
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, governorate_code, main_indicator)
);
CREATE INDEX IF NOT EXISTS idx_mis_latest  ON map_indicator_snapshot (snapshot_date DESC, governorate_code);
CREATE INDEX IF NOT EXISTS idx_mis_history ON map_indicator_snapshot (governorate_code, main_indicator, snapshot_date DESC);

-- ---------------------------------------------------------------------------
-- 2. Sub-indicator value (one row per date × governorate × sub-indicator)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_sub_indicator_value (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,
    sub_indicator     VARCHAR(40)  NOT NULL,
    raw_value         NUMERIC(14,4) NOT NULL,
    threshold_high    NUMERIC(14,4),
    threshold_low     NUMERIC(14,4),
    above_threshold   BOOLEAN      NOT NULL DEFAULT FALSE,
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, governorate_code, sub_indicator)
);
CREATE INDEX IF NOT EXISTS idx_ssiv_gov ON map_sub_indicator_value (snapshot_date DESC, governorate_code);

-- ---------------------------------------------------------------------------
-- 3. Correlation snapshot (one row per date × main × sub × method)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_correlation_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    main_indicator  VARCHAR(40)  NOT NULL,
    sub_indicator   VARCHAR(40)  NOT NULL,
    method          VARCHAR(10)  NOT NULL CHECK (method IN ('pearson', 'spearman', 'kendall_tau')),
    coefficient     NUMERIC(6,4),
    p_value         NUMERIC(10,6),
    n_samples       INTEGER      NOT NULL,
    strength        VARCHAR(15)  NOT NULL,
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, main_indicator, sub_indicator, method)
);
CREATE INDEX IF NOT EXISTS idx_corr_latest ON map_correlation_snapshot (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_corr_pair   ON map_correlation_snapshot (main_indicator, sub_indicator, snapshot_date DESC);

-- ---------------------------------------------------------------------------
-- 4. Regression snapshot (one row per date × main × sub)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_regression_snapshot (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    main_indicator  VARCHAR(40)  NOT NULL,
    sub_indicator   VARCHAR(40)  NOT NULL,
    beta_std        NUMERIC(8,4) NOT NULL,
    std_error       NUMERIC(8,4),
    t_stat          NUMERIC(10,4),
    p_value         NUMERIC(10,6),
    r_squared       NUMERIC(6,4),
    adj_r_squared   NUMERIC(6,4),
    high_impact     BOOLEAN      NOT NULL DEFAULT FALSE,
    vif             NUMERIC(10,4),
    vif_flag        VARCHAR(10)  NOT NULL DEFAULT 'ok',
    n_samples       INTEGER      NOT NULL,
    ridge_used      BOOLEAN      NOT NULL DEFAULT FALSE,
    fit_warning     VARCHAR(40),
    computed_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, main_indicator, sub_indicator)
);
CREATE INDEX IF NOT EXISTS idx_reg_latest ON map_regression_snapshot (snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_reg_main   ON map_regression_snapshot (main_indicator, snapshot_date DESC);

-- ---------------------------------------------------------------------------
-- 5. Risk snapshot (one row per date × governorate)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_risk_snapshot (
    id                BIGSERIAL PRIMARY KEY,
    snapshot_date     DATE         NOT NULL,
    governorate_code  VARCHAR(8)   NOT NULL,
    risk_score        NUMERIC(5,2) NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    risk_level        VARCHAR(10)  NOT NULL CHECK (risk_level IN ('low','medium','high','critical')),
    top_driver_sub    VARCHAR(40),
    top_driver_beta   NUMERIC(8,4),
    trend_pct         NUMERIC(6,2),
    contributing_subs JSONB        NOT NULL DEFAULT '[]',
    computed_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (snapshot_date, governorate_code)
);
CREATE INDEX IF NOT EXISTS idx_risk_latest ON map_risk_snapshot (snapshot_date DESC);

-- ---------------------------------------------------------------------------
-- 6. Alert history (append-only, one row per open alert)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_alert_history (
    id              BIGSERIAL PRIMARY KEY,
    snapshot_date   DATE         NOT NULL,
    governorate_code VARCHAR(8),
    sub_indicator   VARCHAR(40)  NOT NULL,
    rule            VARCHAR(80)  NOT NULL,
    severity        VARCHAR(10)  NOT NULL CHECK (severity IN ('low','medium','high','critical')),
    current_value   NUMERIC(14,4),
    threshold       NUMERIC(14,4),
    message         TEXT         NOT NULL,
    meta            JSONB        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by INTEGER       REFERENCES users(id),
    resolved_at     TIMESTAMPTZ,
    resolved_by     INTEGER       REFERENCES users(id),
    UNIQUE (snapshot_date, governorate_code, sub_indicator, rule)
);
CREATE INDEX IF NOT EXISTS idx_alert_open ON map_alert_history (snapshot_date DESC, acknowledged_at) WHERE acknowledged_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alert_gov  ON map_alert_history (governorate_code, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_alert_sub  ON map_alert_history (sub_indicator, snapshot_date DESC);

-- ---------------------------------------------------------------------------
-- 7. Daily run log (append-only, audit trail for the ETL pipeline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS map_daily_run_log (
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
CREATE INDEX IF NOT EXISTS idx_run_started ON map_daily_run_log (started_at DESC);

-- ---------------------------------------------------------------------------
-- 8. Seed data: 12 Jordan governorates (referenced by every snapshot)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS governorate (
    code            VARCHAR(8)   PRIMARY KEY,             -- 'JO-AM'
    slug            VARCHAR(20)  NOT NULL UNIQUE,         -- 'amman'
    name_en         VARCHAR(40)  NOT NULL,
    name_ar         VARCHAR(40)  NOT NULL,
    center_lon      NUMERIC(8,4) NOT NULL,
    center_lat      NUMERIC(8,4) NOT NULL,
    display_order   INTEGER      NOT NULL,
    active          BOOLEAN      NOT NULL DEFAULT TRUE
);

INSERT INTO governorate (code, slug, name_en, name_ar, center_lon, center_lat, display_order) VALUES
    ('JO-AM', 'amman',   'Amman',   'عمان',    35.95, 31.95,  1),
    ('JO-IR', 'irbid',   'Irbid',   'إربد',    35.85, 32.55,  2),
    ('JO-ZA', 'zarqa',   'Zarqa',   'الزرقاء', 36.10, 32.07,  3),
    ('JO-MA', 'mafraq',  'Mafraq',  'المفرق',  36.20, 32.34,  4),
    ('JO-JA', 'jerash',  'Jerash',  'جرش',    35.90, 32.28,  5),
    ('JO-AJ', 'ajloun',  'Ajloun',  'عجلون',  35.75, 32.33,  6),
    ('JO-BA', 'balqa',   'Balqa',   'البلقاء', 35.78, 32.04,  7),
    ('JO-MD', 'madaba',  'Madaba',  'مادبا',  35.79, 31.72,  8),
    ('JO-KA', 'karak',   'Karak',   'الكرك',  35.70, 31.18,  9),
    ('JO-TA', 'tafileh', 'Tafileh', 'الطفيلة', 35.60, 30.83, 10),
    ('JO-MN', 'maan',    'Ma''an', 'معان',    35.73, 30.20, 11),
    ('JO-AQ', 'aqaba',   'Aqaba',   'العقبة', 35.00, 29.53, 12)
ON CONFLICT (code) DO UPDATE SET
    slug = EXCLUDED.slug,
    name_en = EXCLUDED.name_en,
    name_ar = EXCLUDED.name_ar,
    center_lon = EXCLUDED.center_lon,
    center_lat = EXCLUDED.center_lat,
    display_order = EXCLUDED.display_order;
