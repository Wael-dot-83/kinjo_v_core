# KinJo Platform — PostgreSQL Production Readiness & AI Integration Review

**Reviewed by:** Senior PostgreSQL Architect / AI Integration Specialist  
**Schema source:** `models.py`, `alembic/versions/7d792f81c264_initial_migration_all_tables.py`  
**Service layer:** `auth.py`, `dependencies.py`, `security.py`, `kpi_service.py`, `analytics_service.py`  
**Date:** 2026-05-07  
**Exclusions:** Payment, billing, subscriptions — out of scope.

---

## PART 1 — Critical Production Issues

### Issue 1 — No Row-Level Lock on Class Capacity

| Field                    | Value                                                                                                                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Severity**             | **CRITICAL**                                                                                                                                                                         |
| **Evidence**             | `classes.capacity_total` (Integer, NOT NULL). `enrollment_applications.class_id` FK to `classes.id`. No `SELECT ... FOR UPDATE` found anywhere in the codebase.                      |
| **Risk**                 | Two concurrent managers enrolling the last available seat both read the same count before either writes. Both succeed. Class over-enrolls. Violates regulatory child-to-staff ratio. |
| **Fix**                  | Wrap the enrollment flow in a transaction with `SELECT ... FOR UPDATE` on the `classes` row, then count active enrollments after the lock.                                           |
| **Implementation level** | Database-enforced via backend service layer                                                                                                                                          |

```sql
-- Enrollment capacity guard (backend service layer)
BEGIN;

SELECT id, capacity_total
  FROM classes
 WHERE id = :class_id
   FOR UPDATE;                    -- row-level exclusive lock

SELECT COUNT(*) AS active_count
  FROM enrollment_applications
 WHERE class_id = :class_id
   AND status IN ('ACTIVE', 'ACCEPTED');

-- If active_count < capacity_total → INSERT enrollment with status='ACTIVE'
-- Else                             → INSERT into waitlist_entries with status='WAITLISTED'

COMMIT;
```

**Defense-in-depth trigger (proposed addition):**

```sql
CREATE OR REPLACE FUNCTION enforce_class_capacity()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
  cap   INTEGER;
  used  INTEGER;
BEGIN
  IF NEW.status IN ('ACTIVE', 'ACCEPTED') THEN
    SELECT capacity_total INTO cap FROM classes WHERE id = NEW.class_id FOR UPDATE;
    SELECT COUNT(*) INTO used
      FROM enrollment_applications
     WHERE class_id = NEW.class_id
       AND status IN ('ACTIVE', 'ACCEPTED')
       AND id <> COALESCE(NEW.id, -1);
    IF used >= cap THEN
      RAISE EXCEPTION 'Class % is at capacity (%)', NEW.class_id, cap;
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_class_capacity_guard
  BEFORE INSERT OR UPDATE ON enrollment_applications
  FOR EACH ROW EXECUTE FUNCTION enforce_class_capacity();
```

**Validation test:** Spawn 2 concurrent transactions targeting the last open seat. Assert exactly 1 results in `ACTIVE` and the other in `WAITLISTED`.  
**Migration risk:** None — purely application-logic change and a new trigger; no DDL on existing columns.  
**Rollback note:** `DROP TRIGGER trg_class_capacity_guard ON enrollment_applications; DROP FUNCTION enforce_class_capacity();`

---

### Issue 2 — Audit Log Has No `old_data` / `new_data` JSONB

| Field                    | Value                                                                                                                                                                                                                                                                                                                               |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | **CRITICAL**                                                                                                                                                                                                                                                                                                                        |
| **Evidence**             | `audit_logs` columns: `action` (String), `entity_type` (String), `entity_id` (Integer), `details` (Text), `ip_address` (String), `sensitivity_level` (Integer). **No `old_data JSONB`, `new_data JSONB`, `actor_role`, or `request_id`.** `enhanced_audit_trail.py` writes only to Python's `logging` module — not to the database. |
| **Risk**                 | Cannot answer "what was the child's medical status before it was changed?" or "who changed this incident description and from what?" Ministry compliance and child protection investigations are legally indefensible without before/after state.                                                                                   |
| **Fix**                  | Add `old_data JSONB`, `new_data JSONB`, `actor_role VARCHAR(50)`, and `request_id UUID` to `audit_logs`. Add PostgreSQL triggers for all sensitive tables. Convert `details` from Text to JSONB.                                                                                                                                    |
| **Implementation level** | Database migration + trigger layer                                                                                                                                                                                                                                                                                                  |

```sql
-- Step 1: Column additions
ALTER TABLE audit_logs
  ADD COLUMN old_data    JSONB,
  ADD COLUMN new_data    JSONB,
  ADD COLUMN actor_role  VARCHAR(50),
  ADD COLUMN request_id  UUID;

-- Step 2: Convert details to JSONB (clean existing data first)
-- Pre-check: SELECT id, details FROM audit_logs WHERE details !~ '^[\[{]';
ALTER TABLE audit_logs
  ALTER COLUMN details TYPE JSONB USING details::JSONB;

-- Step 3: Trigger function for sensitive tables
CREATE OR REPLACE FUNCTION audit_sensitive_changes()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO audit_logs(
    user_id, action, entity_type, entity_id,
    old_data, new_data, actor_role, created_at
  )
  VALUES (
    current_setting('app.current_user_id', true)::INT,
    TG_OP,
    TG_TABLE_NAME,
    COALESCE(NEW.id, OLD.id),
    to_jsonb(OLD),
    to_jsonb(NEW),
    current_setting('app.current_user_role', true),
    NOW()
  );
  RETURN COALESCE(NEW, OLD);
END;
$$;

-- Step 4: Apply to all sensitive tables
DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'children','parent_profiles','enrollment_applications',
    'incidents','safeguarding_cases','health_alerts',
    'attendance_logs','daily_reports','users'
  ]
  LOOP
    EXECUTE format(
      'CREATE TRIGGER trg_audit_%I
         AFTER INSERT OR UPDATE OR DELETE ON %I
         FOR EACH ROW EXECUTE FUNCTION audit_sensitive_changes();',
      t, t
    );
  END LOOP;
END;
$$;
```

**Validation test:** `UPDATE children SET date_of_birth = '2022-01-01' WHERE id = 1;` — assert one `audit_logs` row with `old_data->>'date_of_birth'` ≠ `new_data->>'date_of_birth'`.  
**Migration risk:** Medium — converting `details` from Text to JSONB requires pre-cleaning non-JSON legacy rows. Add columns as `DEFAULT NULL`; backfill is not required for historical rows.  
**Rollback note:** Drop the trigger functions and added columns. Historical rows retain `NULL` in new columns.

---

### Issue 3 — No Soft Deletion on Any Core Entity

| Field                    | Value                                                                                                                                                                                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | **CRITICAL**                                                                                                                                                                                                                                                                                                                    |
| **Evidence**             | `children`, `parent_profiles`, `users`, `enrollment_applications`, `classes` — **none have `deleted_at` or `deleted_by`**. `classes.is_active` (Boolean) and `users.status` (Enum with INACTIVE) provide partial deactivation but are inconsistent across entities. No soft-delete pattern found anywhere in the service layer. |
| **Risk**                 | Hard-deletes destroy historical truth. Deleting a user with dependent `audit_logs.user_id`, `incidents.reported_by`, or `daily_reports.submitted_by` records causes FK `RESTRICT` errors silently. Attendance, incident, and safeguarding records become orphaned or unreachable.                                               |
| **Fix**                  | Add `deleted_at TIMESTAMPTZ` and `deleted_by INTEGER` to all primary entities. Create `active_*` partial-index views. Replace all hard-delete API paths with soft-delete updates.                                                                                                                                               |
| **Implementation level** | Database migration + backend service                                                                                                                                                                                                                                                                                            |

```sql
-- Proposed additions
ALTER TABLE users                   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE parent_profiles         ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE children                ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE classes                 ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE enrollment_applications ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE kindergarten_services   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE supervisor_assignments  ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE surveys                 ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE events                  ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);
ALTER TABLE tasks                   ADD COLUMN deleted_at TIMESTAMPTZ, ADD COLUMN deleted_by INT REFERENCES users(id);

-- Partial indexes for active-only queries
CREATE INDEX idx_users_active           ON users(id)                   WHERE deleted_at IS NULL;
CREATE INDEX idx_children_active        ON children(id)                WHERE deleted_at IS NULL;
CREATE INDEX idx_enrollments_active     ON enrollment_applications(id) WHERE deleted_at IS NULL;

-- Active views
CREATE OR REPLACE VIEW active_children AS
  SELECT * FROM children WHERE deleted_at IS NULL;

CREATE OR REPLACE VIEW active_enrollments AS
  SELECT * FROM enrollment_applications WHERE deleted_at IS NULL;

CREATE OR REPLACE VIEW active_classes AS
  SELECT * FROM classes WHERE deleted_at IS NULL;
```

**Validation test:** Soft-delete a user via `UPDATE users SET deleted_at = NOW(), deleted_by = :admin_id WHERE id = :user_id`. Assert the user does not appear in `SELECT * FROM active_children` joins. Assert all dependent audit/incident records remain fully queryable.  
**Migration risk:** Low — additive nullable columns.  
**Rollback note:** `ALTER TABLE users DROP COLUMN deleted_at, DROP COLUMN deleted_by;` (repeat per table). Drop partial indexes and views.

---

### Issue 4 — Future-Date Poisoning on attendance_logs and daily_reports

| Field                    | Value                                                                                                                                                                                                                                                                                                                                      |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Severity**             | HIGH                                                                                                                                                                                                                                                                                                                                       |
| **Evidence**             | `attendance_logs.date` (Date, NOT NULL) — no CHECK constraint blocking future dates. `daily_reports.date` (Date, NOT NULL) — no CHECK constraint blocking future dates. `daily_reports.arrival_time` and `leave_time` are `String(5)` — format not enforced at DB level. `audit_kpi.py` test inserts use `datetime.now()` which can drift. |
| **Risk**                 | Future-dated records corrupt all KPI calculations, attendance-rate analytics, chronic-absence detection, and AI feature computation. The analytics cache (`analytics_dimension_cache`, `advanced_analytics_cache`) will silently include phantom future data.                                                                              |
| **Fix**                  | Add CHECK constraints blocking future dates. Enforce `HH:MM` format for time-string columns.                                                                                                                                                                                                                                               |
| **Implementation level** | Database migration                                                                                                                                                                                                                                                                                                                         |

```sql
-- Pre-migration cleanup (run first, fix or delete bad rows)
SELECT COUNT(*) FROM attendance_logs WHERE date > CURRENT_DATE;
SELECT COUNT(*) FROM daily_reports   WHERE date > CURRENT_DATE;

-- Constraints
ALTER TABLE attendance_logs
  ADD CONSTRAINT ck_attendance_not_future CHECK (date <= CURRENT_DATE),
  ADD CONSTRAINT ck_attendance_not_ancient CHECK (date >= '2000-01-01');

ALTER TABLE daily_reports
  ADD CONSTRAINT ck_report_not_future CHECK (date <= CURRENT_DATE),
  ADD CONSTRAINT ck_arrival_time_format
    CHECK (arrival_time IS NULL OR arrival_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  ADD CONSTRAINT ck_leave_time_format
    CHECK (leave_time IS NULL OR leave_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');

-- daily_reports nap times
ALTER TABLE daily_reports
  ADD CONSTRAINT ck_nap_start_format
    CHECK (nap_start IS NULL OR nap_start ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  ADD CONSTRAINT ck_nap_end_format
    CHECK (nap_end IS NULL OR nap_end ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');
```

**Validation test:** `INSERT INTO attendance_logs(child_id, date, ...) VALUES (1, CURRENT_DATE + 1, ...)` — must raise `ERROR: new row violates check constraint`.  
**Migration risk:** Medium — existing test/seed data may contain future dates. Run the pre-migration SELECTs above and delete or backdate offending rows before applying.  
**Rollback note:** `ALTER TABLE attendance_logs DROP CONSTRAINT ck_attendance_not_future;` (repeat per constraint).

---

### Issue 5 — No Automated Waitlist Expiry Job

| Field                    | Value                                                                                                                                                                                                                                                                                           |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | HIGH                                                                                                                                                                                                                                                                                            |
| **Evidence**             | `waitlist_entries.offer_expiry_at` (DateTime, nullable). `waitlist_entries.status` Enum includes `EXPIRED`. `config.py` defines `WAITLIST_OFFER_EXPIRY_HOURS = 48`. **No pg_cron rule, APScheduler job, or trigger exists to transition `OFFERED` → `EXPIRED` when `offer_expiry_at < NOW()`.** |
| **Risk**                 | Offers remain open indefinitely. Seats are effectively locked. Other high-priority waitlisted children are never promoted. Capacity calculations are incorrect.                                                                                                                                 |
| **Fix**                  | Schedule a pg_cron job (preferred) or an APScheduler job to expire offers every 15 minutes and promote the next candidate.                                                                                                                                                                      |
| **Implementation level** | Scheduled job (pg_cron or APScheduler)                                                                                                                                                                                                                                                          |

```sql
-- Prerequisite index (proposed)
CREATE INDEX idx_waitlist_expiry_scan
  ON waitlist_entries(status, offer_expiry_at)
  WHERE status = 'OFFERED';

-- pg_cron schedule (requires pg_cron extension)
SELECT cron.schedule(
  'expire-waitlist-offers',
  '*/15 * * * *',
  $$
    WITH expired AS (
      UPDATE waitlist_entries
         SET status = 'EXPIRED',
             updated_at = NOW()
       WHERE status = 'OFFERED'
         AND offer_expiry_at < NOW()
       RETURNING enrollment_id
    )
    -- Promote next candidate per affected class
    UPDATE waitlist_entries
       SET status = 'OFFERED',
           offer_sent_at  = NOW(),
           offer_expiry_at = NOW() + INTERVAL '48 hours',
           updated_at = NOW()
      FROM (
        SELECT DISTINCT ON (ea.class_id) we.id
          FROM waitlist_entries we
          JOIN enrollment_applications ea ON ea.id = we.enrollment_id
         WHERE we.status = 'WAITLISTED'
           AND ea.class_id IN (
             SELECT ea2.class_id
               FROM enrollment_applications ea2
               JOIN expired e ON e.enrollment_id = ea2.id
           )
         ORDER BY ea.class_id, we.priority_score DESC
      ) next_candidate
     WHERE waitlist_entries.id = next_candidate.id;
  $$
);
```

**APScheduler alternative (if pg_cron is unavailable):**

```python
# In main.py startup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job("interval", minutes=15)
async def expire_waitlist_offers():
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            UPDATE waitlist_entries
               SET status = 'EXPIRED', updated_at = NOW()
             WHERE status = 'OFFERED' AND offer_expiry_at < NOW()
        """))
        await db.commit()

scheduler.start()
```

**Validation test:** Insert a waitlist entry with `status='OFFERED'` and `offer_expiry_at = NOW() - INTERVAL '1 minute'`. Run the job. Assert `status = 'EXPIRED'`.  
**Migration risk:** None — no DDL change on existing columns.  
**Rollback note:** `SELECT cron.unschedule('expire-waitlist-offers');`

---

### Issue 6 — children Has No Baseline Medical Profile

| Field                    | Value                                                                                                                                                                                                                                                                                                                                                                                                       |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | HIGH                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Evidence**             | `children` columns: `first_name`, `last_name`, `gender`, `date_of_birth`, `father_name`, mother name fields, `media_consent`, `correspondence_flag`. **No `medical_notes`, `allergy_notes`, `special_needs_notes`, `emergency_contact_name`, `emergency_contact_phone`, `blood_type`, or `vaccination_up_to_date`**. The `health_alerts` table captures event-driven alerts, not a static baseline profile. |
| **Risk**                 | Teachers have no queryable baseline medical/allergy data at point of daily care. Incident responders cannot answer "does this child have a known allergy?" without parsing `health_alerts` rows — which are event-driven, not definitional. All AI medical context for the parent AI and supervisor AI modules is missing. Ministry medical reporting is impossible.                                        |
| **Fix**                  | Add structured medical fields to `children` (all nullable). Classify at sensitivity level 5. Gate reads to SUPERVISOR, MANAGER, ADMIN and child's own parent.                                                                                                                                                                                                                                               |
| **Implementation level** | Database migration                                                                                                                                                                                                                                                                                                                                                                                          |

```sql
ALTER TABLE children
  ADD COLUMN medical_notes          TEXT,         -- free text; encrypted at rest
  ADD COLUMN allergy_notes          TEXT,         -- free text; encrypted at rest
  ADD COLUMN special_needs_notes    TEXT,         -- educational/behavioural context
  ADD COLUMN emergency_contact_name  VARCHAR(255),
  ADD COLUMN emergency_contact_phone VARCHAR(20),
  ADD COLUMN blood_type             VARCHAR(5),   -- A+, B-, O+, AB+, etc.
  ADD COLUMN vaccination_up_to_date BOOLEAN;      -- NULL = unknown

-- Full-text search on allergy notes (proposed)
CREATE INDEX idx_children_allergy_fts
  ON children USING GIN(to_tsvector('simple', COALESCE(allergy_notes, '')));
```

**Privacy guardrail:** All writes to these columns must produce `audit_logs` entries with `old_data` / `new_data`. Parent may read their own child's record. Parent may not edit after initial submission without manager approval. Columns must never appear in ministry aggregate exports.  
**Validation test:** `SELECT allergy_notes FROM children WHERE id = :id;` returns the stored value for SUPERVISOR role. Assert 403 Forbidden for PARENT accessing another parent's child.  
**Migration risk:** Low — all nullable additions.  
**Rollback note:** `ALTER TABLE children DROP COLUMN medical_notes, DROP COLUMN allergy_notes, DROP COLUMN special_needs_notes, DROP COLUMN emergency_contact_name, DROP COLUMN emergency_contact_phone, DROP COLUMN blood_type, DROP COLUMN vaccination_up_to_date;`

---

### Issue 7 — attendance_logs Has No class_id

| Field                    | Value                                                                                                                                                                                                                                                                                               |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | HIGH                                                                                                                                                                                                                                                                                                |
| **Evidence**             | `attendance_logs` columns: `child_id`, `date`, `check_in_at`, `check_out_at`, `method`, `dropped_by_name`, `picked_by_name`. **No `class_id`**. `kpi_service.py` derives the class via a JOIN to `enrollment_applications`, which is fragile for children who transferred between classes mid-year. |
| **Risk**                 | Attendance records cannot be attributed to the correct class for a historical date when a child transferred. Class-level KPI calculations (`compute_attendance_rate`) are unreliable. Ratio compliance analytics that require "how many children were present in class X on date Y?" are broken.    |
| **Fix**                  | Add `class_id INTEGER FK → classes.id` to `attendance_logs`. Populate at check-in time from the child's active `enrollment_applications` row on that date.                                                                                                                                          |
| **Implementation level** | Database migration + backend service update                                                                                                                                                                                                                                                         |

```sql
-- Migration
ALTER TABLE attendance_logs
  ADD COLUMN class_id INTEGER REFERENCES classes(id);

-- Backfill from enrollment_applications (run in batches)
UPDATE attendance_logs al
   SET class_id = (
     SELECT ea.class_id
       FROM enrollment_applications ea
      WHERE ea.child_id  = al.child_id
        AND ea.status IN ('ACTIVE', 'ACCEPTED')
        AND ea.enrollment_start_date <= al.date
        AND (ea.enrollment_end_date IS NULL OR ea.enrollment_end_date >= al.date)
      ORDER BY ea.created_at DESC
      LIMIT 1
   )
 WHERE al.class_id IS NULL;

-- Index
CREATE INDEX idx_attendance_class_date
  ON attendance_logs(class_id, date);
```

**Validation test:** Insert an attendance log. Assert `class_id` matches the child's active enrollment class for that date. Query `SELECT COUNT(*) FROM attendance_logs WHERE class_id = :cid AND date = :d` — must match expected present count.  
**Migration risk:** Medium — backfill requires JOIN against `enrollment_applications`. Run in batches (1000 rows) to avoid lock contention. Some historical rows may have no matching enrollment; leave `class_id = NULL` and investigate.  
**Rollback note:** `ALTER TABLE attendance_logs DROP COLUMN class_id;`

---

### Issue 8 — incidents Lacks reported_by, class_id, and closed_by

| Field                    | Value                                                                                                                                                                                                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | HIGH                                                                                                                                                                                                                                                                                                      |
| **Evidence**             | `incidents` columns: `child_id`, `kindergarten_id`, `type`, `severity_level`, `description`, `occurred_at`, `notify_parent_at`, `followup_required_flag`, `followup_sla_deadline`, `closed_at`. **No `reported_by` FK to `users.id`, no `class_id` FK to `classes.id`, no `closed_by` FK to `users.id`**. |
| **Risk**                 | Cannot determine which staff member reported the incident. Cannot detect under-reporting by specific staff. Cannot close the accountability loop for `followup_sla_deadline`. Cannot produce class-level incident analytics (required by the incident hotspot AI).                                        |
| **Fix**                  | Add the three missing columns.                                                                                                                                                                                                                                                                            |
| **Implementation level** | Database migration                                                                                                                                                                                                                                                                                        |

```sql
ALTER TABLE incidents
  ADD COLUMN reported_by INTEGER REFERENCES users(id),
  ADD COLUMN class_id    INTEGER REFERENCES classes(id),
  ADD COLUMN closed_by   INTEGER REFERENCES users(id);

CREATE INDEX idx_incident_reported_by  ON incidents(reported_by);
CREATE INDEX idx_incident_class_date   ON incidents(class_id, occurred_at DESC);
```

**Validation test:** Create an incident via the API. Assert `reported_by = :current_user_id` in the stored row.  
**Migration risk:** Low — all nullable additions. Existing rows retain NULL; backfill from `audit_logs` if possible.  
**Rollback note:** `ALTER TABLE incidents DROP COLUMN reported_by, DROP COLUMN class_id, DROP COLUMN closed_by;`

---

### Issue 9 — ORM / Migration Drift on messages.recipient_id

| Field                    | Value                                                                                                                                                                                                                                                                                                                                                                |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | MEDIUM                                                                                                                                                                                                                                                                                                                                                               |
| **Evidence**             | `models.py` defines `recipient_id = Column(Integer, ForeignKey("users.id"), nullable=True)` on the `Message` model. The initial Alembic migration `7d792f81c264` DDL for `messages` does not list a `recipient_id` column in its `op.create_table('messages', ...)` block. If the live database was created from this migration directly, the column does not exist. |
| **Risk**                 | Direct parent-to-teacher messaging fails silently at the database level. The `idx_message_recipient_date` index cannot be created. All `Message` ORM queries filtering on `recipient_id` will raise a `ProgrammingError`.                                                                                                                                            |
| **Fix**                  | Verify column existence in the live database. If absent, apply a corrective Alembic migration.                                                                                                                                                                                                                                                                       |
| **Implementation level** | Database migration                                                                                                                                                                                                                                                                                                                                                   |

```sql
-- Verify (run against live DB)
SELECT column_name
  FROM information_schema.columns
 WHERE table_name = 'messages'
   AND column_name = 'recipient_id';

-- Corrective migration if absent
ALTER TABLE messages
  ADD COLUMN recipient_id INTEGER REFERENCES users(id);

CREATE INDEX idx_message_recipient_date
  ON messages(recipient_id, created_at DESC);

-- Also add is_read and read_at (missing engagement tracking)
ALTER TABLE messages
  ADD COLUMN is_read BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN read_at TIMESTAMPTZ;

CREATE INDEX idx_message_recipient_unread
  ON messages(recipient_id, created_at DESC)
  WHERE is_read = FALSE;
```

**Validation test:** `SELECT recipient_id FROM messages LIMIT 1;` — must succeed without error. INSERT a direct message and confirm `recipient_id` is stored.  
**Migration risk:** Low — additive columns.  
**Rollback note:** `ALTER TABLE messages DROP COLUMN recipient_id, DROP COLUMN is_read, DROP COLUMN read_at;`

---

### Issue 10 — Missing Composite Indexes for High-Frequency Queries

| Field        | Value                                                                                                                                                                  |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity** | HIGH                                                                                                                                                                   |
| **Evidence** | The following query patterns have no composite index coverage in the migration file. `EXPLAIN ANALYZE` on these patterns will show sequential scans on growing tables. |

| Missing Index                  | Table                     | Columns                                                | Query Pattern Served                  |
| ------------------------------ | ------------------------- | ------------------------------------------------------ | ------------------------------------- |
| `idx_attendance_child_date`    | `attendance_logs`         | `(child_id, date DESC)`                                | Parent views child attendance history |
| `idx_incident_kg_date`         | `incidents`               | `(kindergarten_id, occurred_at DESC)`                  | Manager incident dashboard            |
| `idx_incident_child_date`      | `incidents`               | `(child_id, occurred_at DESC)`                         | Child safety timeline                 |
| `idx_message_recipient_date`   | `messages`                | `(recipient_id, created_at DESC)`                      | Parent/supervisor inbox               |
| `idx_observation_child_domain` | `observations`            | `(child_id, domain, observed_at DESC)`                 | Teacher curriculum view               |
| `idx_safeguarding_open`        | `safeguarding_cases`      | `(kindergarten_id, closed_at) WHERE closed_at IS NULL` | Manager open case list                |
| `idx_health_alert_child`       | `health_alerts`           | `(child_id, created_at DESC)`                          | Supervisor alert panel                |
| `idx_waitlist_expiry_scan`     | `waitlist_entries`        | `(status, offer_expiry_at) WHERE status='OFFERED'`     | Expiry automation job                 |
| `idx_enrollment_child_status`  | `enrollment_applications` | `(child_id, status)`                                   | Child enrollment history              |
| `idx_ratio_kg_date`            | `ratio_compliance`        | `(kindergarten_id, date DESC)`                         | Compliance trend queries              |

```sql
-- All indexes created CONCURRENTLY to avoid table locks in production
CREATE INDEX CONCURRENTLY idx_attendance_child_date
  ON attendance_logs(child_id, date DESC);

CREATE INDEX CONCURRENTLY idx_incident_kg_date
  ON incidents(kindergarten_id, occurred_at DESC);

CREATE INDEX CONCURRENTLY idx_incident_child_date
  ON incidents(child_id, occurred_at DESC);

CREATE INDEX CONCURRENTLY idx_message_recipient_date
  ON messages(recipient_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_observation_child_domain
  ON observations(child_id, domain, observed_at DESC);

CREATE INDEX CONCURRENTLY idx_safeguarding_open
  ON safeguarding_cases(kindergarten_id, closed_at)
  WHERE closed_at IS NULL;

CREATE INDEX CONCURRENTLY idx_health_alert_child
  ON health_alerts(child_id, created_at DESC);

CREATE INDEX CONCURRENTLY idx_waitlist_expiry_scan
  ON waitlist_entries(status, offer_expiry_at)
  WHERE status = 'OFFERED';

CREATE INDEX CONCURRENTLY idx_enrollment_child_status
  ON enrollment_applications(child_id, status);

CREATE INDEX CONCURRENTLY idx_ratio_kg_date
  ON ratio_compliance(kindergarten_id, date DESC);
```

**Validation test:** Run `EXPLAIN (ANALYZE, BUFFERS) SELECT ... FROM attendance_logs WHERE child_id = :id ORDER BY date DESC LIMIT 30;` — must show `Index Scan using idx_attendance_child_date`.  
**Migration risk:** Low — `CONCURRENTLY` does not lock. However, it cannot run inside a transaction block; execute outside of `alembic upgrade` transaction context.  
**Rollback note:** `DROP INDEX CONCURRENTLY idx_attendance_child_date;` (repeat per index).

---

### Issue 11 — health_alerts.severity Is Unconstrained String

| Field        | Value                                                                                                                                                                                               |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity** | MEDIUM                                                                                                                                                                                              |
| **Evidence** | `health_alerts.severity` is `String(50)` — no Enum, no CHECK constraint. Any value can be inserted.                                                                                                 |
| **Risk**     | Analytics that filter on `severity = 'CRITICAL'` will miss rows stored as `'critical'`, `'Critical'`, or `'HIGH RISK'`. AI alerting rules that depend on severity levels will malfunction silently. |
| **Fix**      | Add a CHECK constraint limiting to known values. Long term: replace with Enum via migration.                                                                                                        |

```sql
-- Immediate fix: CHECK constraint
ALTER TABLE health_alerts
  ADD CONSTRAINT ck_health_alert_severity
    CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL'));

-- Normalise existing data first
UPDATE health_alerts
   SET severity = UPPER(severity)
 WHERE severity NOT IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');
```

**Rollback note:** `ALTER TABLE health_alerts DROP CONSTRAINT ck_health_alert_severity;`

---

### Issue 12 — survey_responses Allows Duplicate Submissions

| Field        | Value                                                                                                                                                                      |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity** | MEDIUM                                                                                                                                                                     |
| **Evidence** | `survey_responses(survey_id, parent_id)` — **no UNIQUE constraint**. A parent can submit the same survey multiple times. NPS scores are computed from AVG across all rows. |
| **Risk**     | NPS score inflation or manipulation. Governance quality index based on NPS becomes unreliable.                                                                             |
| **Fix**      | Add a UNIQUE constraint.                                                                                                                                                   |

```sql
ALTER TABLE survey_responses
  ADD CONSTRAINT uq_survey_response_per_parent
    UNIQUE (survey_id, parent_id);
```

**Pre-migration:** `SELECT survey_id, parent_id, COUNT(*) FROM survey_responses GROUP BY 1, 2 HAVING COUNT(*) > 1;` — delete duplicates before applying.  
**Rollback note:** `ALTER TABLE survey_responses DROP CONSTRAINT uq_survey_response_per_parent;`

---

### Issue 13 — safeguarding_cases Has No Status Enum or Assigned Accountability

| Field        | Value                                                                                                                                                                                                                                                |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity** | MEDIUM                                                                                                                                                                                                                                               |
| **Evidence** | `safeguarding_cases` columns: `case_description`, `opened_at`, `escalated_at`, `closed_at`, `sla_escalation_deadline`, `sla_closure_deadline`. **No `status` Enum and no `assigned_to` FK**. Open/closed state is inferred from `closed_at IS NULL`. |
| **Risk**     | Cannot query "all open safeguarding cases assigned to me." SLA breach detection queries are ambiguous. Manager cannot see who is responsible for following up. Ministry audits require clear case ownership.                                         |
| **Fix**      | Add `status` Enum column and `assigned_to` FK.                                                                                                                                                                                                       |

```sql
CREATE TYPE safeguardingstatus AS ENUM (
  'OPEN', 'UNDER_INVESTIGATION', 'ESCALATED', 'PENDING_CLOSURE', 'CLOSED'
);

ALTER TABLE safeguarding_cases
  ADD COLUMN status      safeguardingstatus NOT NULL DEFAULT 'OPEN',
  ADD COLUMN assigned_to INTEGER REFERENCES users(id);

-- Backfill
UPDATE safeguarding_cases
   SET status = CASE
     WHEN closed_at IS NOT NULL THEN 'CLOSED'
     WHEN escalated_at IS NOT NULL THEN 'ESCALATED'
     ELSE 'OPEN'
   END;

CREATE INDEX idx_safeguarding_assigned
  ON safeguarding_cases(assigned_to, status)
  WHERE status <> 'CLOSED';
```

---

### Issue 14 — In-Memory Rate Limiter Has No Persistence

| Field                    | Value                                                                                                                                                                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity**             | MEDIUM                                                                                                                                                                                                                                                    |
| **Evidence**             | `security.py` `RateLimiter` stores `_requests`, `_login_attempts`, and `_blocked_ips` in in-process Python `defaultdict`. State is lost on restart. `config.py` defines `REDIS_URL` but it is not used by the rate limiter. HSTS header is commented out. |
| **Risk**                 | Brute-force login attempts reset after process restart. Multi-worker deployments share no rate-limit state. IP blocks evaporate.                                                                                                                          |
| **Fix**                  | Migrate rate-limit counters to Redis using `aioredis` with TTL-keyed counters.                                                                                                                                                                            |
| **Implementation level** | Backend application                                                                                                                                                                                                                                       |

```python
# Redis-backed rate check (pseudo-code)
import aioredis

redis = aioredis.from_url(settings.REDIS_URL)

async def check_login_rate(ip: str) -> bool:
    key = f"login_attempts:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)   # 1-minute window
    return count <= 5                 # allow max 5 per minute
```

---

### Issue 15 — Duplicate Enum Definitions in models.py

| Field        | Value                                                                                                                                                                               |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Severity** | LOW                                                                                                                                                                                 |
| **Evidence** | `AnalyticsDimensionType` and `AnalyticsPeriodType` are defined twice in `models.py` — once near lines 22-37 and again near lines 700-720. Python silently uses the last definition. |
| **Risk**     | If a developer modifies one but not the other, enum values diverge. The earlier definition used by some ORM columns may produce unexpected behaviour.                               |
| **Fix**      | Delete the duplicate definitions at the bottom of the file. Keep the definitions at lines 22-37.                                                                                    |

---

## PART 2 — AI Capability Map

### AI-1 — Parent Daily Report Narrative

| Attribute             | Detail                                                                                                                                                                                                                                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**       | Parent                                                                                                                                                                                                                                                                                                |
| **Database tables**   | `daily_reports`, `children`, `attendance_logs`                                                                                                                                                                                                                                                        |
| **Exact columns**     | `daily_reports.breakfast`, `daily_reports.snack`, `daily_reports.milk`, `daily_reports.lunch`, `daily_reports.nap_duration_minutes`, `daily_reports.activities`, `daily_reports.notes`, `daily_reports.date`, `attendance_logs.check_in_at`, `attendance_logs.check_out_at`, `children.date_of_birth` |
| **Trigger / event**   | `daily_reports.status` transitions to `APPROVED`                                                                                                                                                                                                                                                      |
| **AI technique**      | Rule-based template fill for meals and sleep; local LLM (Ollama) for natural-language narrative only                                                                                                                                                                                                  |
| **Output**            | "Today Omar had a great lunch, slept for 90 minutes, and worked on a drawing activity."                                                                                                                                                                                                               |
| **Output storage**    | `ai_parent_recommendations` (proposed) with `recommendation_type = 'daily_summary'`                                                                                                                                                                                                                   |
| **Privacy guardrail** | Scoped to `child_id` matching authenticated parent. `daily_reports.notes` never sent to LLM if it contains keywords matching `children.allergy_notes`. No diagnosis. No fabrication of absent data fields.                                                                                            |
| **Human review**      | `human_reviewed` defaults to FALSE. Parent sees content only after supervisor approval OR auto-approval 6 hours after `APPROVED` status if no review is triggered.                                                                                                                                    |

---

### AI-2 — Absence Wellness Signal (Rule-Based)

| Attribute           | Detail                                                                                                                                                                                   |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**     | Supervisor, Manager                                                                                                                                                                      |
| **Database tables** | `attendance_logs`, `operating_calendar`, `enrollment_applications`, `children`                                                                                                           |
| **Exact columns**   | `attendance_logs.date`, `attendance_logs.child_id`, `operating_calendar.is_open`, `operating_calendar.date`, `enrollment_applications.status`, `enrollment_applications.kindergarten_id` |
| **AI technique**    | Window function — consecutive absent school days                                                                                                                                         |
| **Output**          | Alert: "Child [ID] has been absent for 3 consecutive school days." → `ai_manager_alerts`                                                                                                 |

```sql
-- Consecutive absence detection
WITH school_days AS (
  SELECT date
    FROM operating_calendar
   WHERE kindergarten_id = :kg_id
     AND is_open = TRUE
     AND date BETWEEN CURRENT_DATE - 14 AND CURRENT_DATE
),
child_attendance AS (
  SELECT s.date, ea.child_id,
         (al.id IS NOT NULL) AS present
    FROM school_days s
   CROSS JOIN (
     SELECT DISTINCT child_id
       FROM enrollment_applications
      WHERE kindergarten_id = :kg_id AND status = 'ACTIVE'
   ) ea
    LEFT JOIN attendance_logs al
           ON al.child_id = ea.child_id AND al.date = s.date
),
streak AS (
  SELECT child_id,
         SUM(CASE WHEN NOT present THEN 1 ELSE 0 END)
           OVER (PARTITION BY child_id ORDER BY date
                 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS absent_streak
    FROM child_attendance
)
SELECT DISTINCT child_id
  FROM streak
 WHERE absent_streak >= 3;
```

---

### AI-3 — Allergy and Incident Precaution Alert (Rule-Based)

| Attribute             | Detail                                                                                                                                                                                    |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**       | Supervisor, Teacher on duty                                                                                                                                                               |
| **Database tables**   | `children` (proposed `allergy_notes`), `health_alerts`, `incidents`                                                                                                                       |
| **Exact columns**     | `children.allergy_notes` (proposed), `health_alerts.alert_type`, `health_alerts.description`, `incidents.type`, `incidents.occurred_at`, `incidents.severity_level`, `incidents.child_id` |
| **AI technique**      | Rule-based SQL + PostgreSQL full-text search on `allergy_notes`                                                                                                                           |
| **Output**            | "⚠ Child [ID] has a documented nut allergy. Check today's snack menu."                                                                                                                    |
| **Privacy guardrail** | Allergy data visible only to SUPERVISOR, MANAGER, ADMIN roles, and the child's own parent. Not exposed in any public or ministry API.                                                     |

```sql
-- Alert: child with known allergy present today and recent ILLNESS incident
SELECT c.id AS child_id,
       c.allergy_notes,
       i.description AS recent_incident
  FROM children c
  JOIN attendance_logs al
    ON al.child_id = c.id AND al.date = CURRENT_DATE
  LEFT JOIN incidents i
    ON i.child_id = c.id
   AND i.type = 'ILLNESS'
   AND i.occurred_at >= NOW() - INTERVAL '72 hours'
 WHERE to_tsvector('simple', COALESCE(c.allergy_notes, '')) @@
       plainto_tsquery('simple', :menu_items);
```

---

### AI-4 — Incident Hotspot Detection (Z-Score)

| Attribute           | Detail                                                                                                                                     |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Target user**     | Manager, Administrator                                                                                                                     |
| **Database tables** | `incidents` (after `class_id` addition), `enrollment_applications`                                                                         |
| **Exact columns**   | `incidents.class_id` (proposed), `incidents.occurred_at`, `incidents.severity_level`, `incidents.type`, `incidents.reported_by` (proposed) |
| **AI technique**    | Z-score anomaly detection using PostgreSQL window functions                                                                                |
| **Output**          | Alert: "Class [ID] had 4 incidents this week vs. network average of 0.8 (z=2.6). Review supervision."                                      |

```sql
WITH weekly_counts AS (
  SELECT class_id,
         DATE_TRUNC('week', occurred_at) AS week,
         COUNT(*) AS n
    FROM incidents
   WHERE occurred_at >= NOW() - INTERVAL '8 weeks'
     AND class_id IS NOT NULL
   GROUP BY class_id, DATE_TRUNC('week', occurred_at)
),
stats AS (
  SELECT class_id,
         AVG(n)    AS avg_n,
         STDDEV(n) AS std_n
    FROM weekly_counts
   GROUP BY class_id
),
current_week AS (
  SELECT class_id, n
    FROM weekly_counts
   WHERE week = DATE_TRUNC('week', NOW())
)
SELECT c.class_id,
       c.n              AS this_week,
       s.avg_n,
       ROUND(((c.n - s.avg_n) / NULLIF(s.std_n, 0))::NUMERIC, 2) AS z_score
  FROM current_week c
  JOIN stats s USING (class_id)
 WHERE (c.n - s.avg_n) / NULLIF(s.std_n, 0) > 2.0
 ORDER BY z_score DESC;
```

---

### AI-5 — Waitlist Next-Candidate Recommendation (Rule-Based)

| Attribute           | Detail                                                                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Target user**     | Manager                                                                                                                                                                        |
| **Database tables** | `waitlist_entries`, `enrollment_applications`, `children`, `classes`                                                                                                           |
| **Exact columns**   | `waitlist_entries.priority_score`, `waitlist_entries.status`, `enrollment_applications.class_id`, `children.date_of_birth`, `classes.min_age_months`, `classes.max_age_months` |
| **AI technique**    | Deterministic SQL rank — no ML required                                                                                                                                        |

```sql
SELECT we.id AS waitlist_entry_id,
       ea.child_id,
       we.priority_score,
       EXTRACT(MONTH FROM AGE(NOW(), c.date_of_birth))::INT AS age_months
  FROM waitlist_entries we
  JOIN enrollment_applications ea ON ea.id = we.enrollment_id
  JOIN children c ON c.id = ea.child_id
  JOIN classes  cl ON cl.id = ea.class_id
 WHERE we.status = 'WAITLISTED'
   AND cl.id = :class_id
   AND EXTRACT(MONTH FROM AGE(NOW(), c.date_of_birth))
         BETWEEN cl.min_age_months AND cl.max_age_months
 ORDER BY we.priority_score DESC
 LIMIT 1;
```

---

### AI-6 — Staff Ratio Compliance Forecast (Rule-Based + Moving Average)

| Attribute           | Detail                                                                                                                                                                                                                                       |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**     | Manager, Ministry Regulator                                                                                                                                                                                                                  |
| **Database tables** | `ratio_compliance`, `staff_presence_logs`, `attendance_logs`, `enrollment_applications`                                                                                                                                                      |
| **Exact columns**   | `ratio_compliance.compliant_minutes`, `ratio_compliance.operating_minutes`, `ratio_compliance.staff_count_avg`, `ratio_compliance.child_count_avg`, `staff_presence_logs.date`, `staff_presence_logs.start_at`, `staff_presence_logs.end_at` |
| **AI technique**    | 4-week moving average + threshold rule                                                                                                                                                                                                       |
| **Output**          | "Based on the last 4 Sundays, ratio compliance averages 74%. Consider requesting additional staff cover."                                                                                                                                    |

```sql
SELECT kindergarten_id,
       EXTRACT(DOW FROM date) AS day_of_week,
       AVG(compliant_minutes::FLOAT / NULLIF(operating_minutes, 0)) AS avg_compliance_rate,
       COUNT(*) AS sample_weeks
  FROM ratio_compliance
 WHERE date >= CURRENT_DATE - INTERVAL '28 days'
 GROUP BY kindergarten_id, EXTRACT(DOW FROM date)
HAVING AVG(compliant_minutes::FLOAT / NULLIF(operating_minutes, 0)) < 0.80
 ORDER BY avg_compliance_rate ASC;
```

---

### AI-7 — Ministry Enrollment Demand Forecast (Cohort SQL)

| Attribute             | Detail                                                                                                                                                   |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**       | Administrator, Ministry Planner                                                                                                                          |
| **Database tables**   | `children`, `parent_profiles`, `enrollment_applications`, `kindergartens`                                                                                |
| **Exact columns**     | `children.date_of_birth`, `parent_profiles.home_governorate`, `parent_profiles.home_city`, `enrollment_applications.status`, `kindergartens.governorate` |
| **AI technique**      | Cohort-based time-series projection — deterministic SQL                                                                                                  |
| **Privacy guardrail** | Aggregate only. No individual child data in ministry output. Minimum cohort size = 5 before reporting.                                                   |

```sql
SELECT pp.home_governorate,
       DATE_TRUNC('month', c.date_of_birth + INTERVAL '24 months') AS eligible_from_month,
       COUNT(*) AS projected_enrollments
  FROM children c
  JOIN parent_profiles pp ON pp.id = c.parent_id
 WHERE c.date_of_birth + INTERVAL '24 months'
         BETWEEN NOW() AND NOW() + INTERVAL '12 months'
   AND c.deleted_at IS NULL
 GROUP BY pp.home_governorate,
          DATE_TRUNC('month', c.date_of_birth + INTERVAL '24 months')
HAVING COUNT(*) >= 5
 ORDER BY pp.home_governorate, eligible_from_month;
```

---

### AI-8 — Teacher Observation Summary (LLM, Human-Reviewed)

| Attribute             | Detail                                                                                                                                                                                    |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**       | Supervisor, Parent (after review)                                                                                                                                                         |
| **Database tables**   | `observations`, `curriculum_outcomes`, `children`                                                                                                                                         |
| **Exact columns**     | `observations.observation_text`, `observations.domain`, `observations.mastery_level`, `observations.observed_at`, `curriculum_outcomes.description`, `curriculum_outcomes.indicator_code` |
| **AI technique**      | PostgreSQL full-text keyword extraction for feature building; LLM (Ollama local) for narrative generation only                                                                            |
| **Output storage**    | `ai_parent_recommendations` with `recommendation_type = 'observation_summary'`                                                                                                            |
| **Privacy guardrail** | Raw `observation_text` never sent to external LLM. Structured domain-level feature JSON is the LLM input. Supervisor must set `human_reviewed = TRUE` before parent sees any content.     |

---

### AI-9 — Governance Score Trend Alert (Window Function)

| Attribute           | Detail                                                                                                                                      |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**     | Administrator                                                                                                                               |
| **Database tables** | `governance_scores`, `kpi_snapshots`                                                                                                        |
| **Exact columns**   | `governance_scores.final_governance_score`, `governance_scores.band`, `governance_scores.period_start`, `governance_scores.kindergarten_id` |
| **AI technique**    | `LAG()` window function — 2 consecutive below-threshold periods                                                                             |

```sql
SELECT kindergarten_id,
       period_start,
       final_governance_score,
       band,
       LAG(final_governance_score) OVER (
         PARTITION BY kindergarten_id ORDER BY period_start
       ) AS prev_score
  FROM governance_scores
 WHERE final_governance_score < 60
   AND LAG(final_governance_score) OVER (
     PARTITION BY kindergarten_id ORDER BY period_start
   ) < 60;
```

---

### AI-10 — Semantic Behavior Pattern Search (pgvector)

| Attribute             | Detail                                                                                                                                                          |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Target user**       | Supervisor, Teacher                                                                                                                                             |
| **Database tables**   | `observations`, `daily_reports`, `ai_embeddings` (proposed)                                                                                                     |
| **Exact columns**     | `observations.observation_text`, `daily_reports.notes`, `daily_reports.activities`                                                                              |
| **AI technique**      | pgvector cosine similarity; embedding model: `nomic-embed-text` via Ollama local                                                                                |
| **Privacy guardrail** | Embeddings stored in `ai_embeddings` with no raw PII. Cross-child similarity results show domain and count only, never names. Minimum observation age: 30 days. |

---

## PART 3 — AI Database Infrastructure (Proposed Tables)

### ai_parent_recommendations

```sql
CREATE TABLE ai_parent_recommendations (
  id                  SERIAL PRIMARY KEY,
  child_id            INTEGER      NOT NULL REFERENCES children(id),
  report_date         DATE         NOT NULL,
  source_report_id    INTEGER      REFERENCES daily_reports(id),
  recommendation_type VARCHAR(50)  NOT NULL,
  content_ar          TEXT,
  content_en          TEXT,
  model_version       VARCHAR(50),
  prompt_version      VARCHAR(20),
  confidence          FLOAT,
  evidence_json       JSONB,
  parent_feedback     VARCHAR(20)  CHECK (parent_feedback IN ('helpful','not_helpful','incorrect')),
  feedback_at         TIMESTAMPTZ,
  human_reviewed      BOOLEAN      NOT NULL DEFAULT FALSE,
  reviewed_by         INTEGER      REFERENCES users(id),
  review_note         TEXT,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_parent_child_date
  ON ai_parent_recommendations(child_id, report_date DESC);

CREATE INDEX idx_ai_parent_unreviewed
  ON ai_parent_recommendations(reviewed_by, created_at)
  WHERE human_reviewed = FALSE;
```

### ai_manager_alerts

```sql
CREATE TABLE ai_manager_alerts (
  id                  SERIAL PRIMARY KEY,
  kindergarten_id     INTEGER      NOT NULL REFERENCES kindergartens(id),
  alert_type          VARCHAR(100) NOT NULL,
  severity            VARCHAR(20)  NOT NULL
                        CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  target_entity_type  VARCHAR(50),
  target_entity_id    INTEGER,
  details             JSONB        NOT NULL,
  rule_version        VARCHAR(20),
  acknowledged        BOOLEAN      NOT NULL DEFAULT FALSE,
  acknowledged_by     INTEGER      REFERENCES users(id),
  acknowledged_at     TIMESTAMPTZ,
  dismissed           BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_manager_alerts_open
  ON ai_manager_alerts(kindergarten_id, created_at DESC)
  WHERE acknowledged = FALSE AND dismissed = FALSE;
```

### ai_job_logs

```sql
CREATE TABLE ai_job_logs (
  id             SERIAL PRIMARY KEY,
  job_name       VARCHAR(100) NOT NULL,
  job_type       VARCHAR(50)  NOT NULL
                   CHECK (job_type IN ('rule_based','llm','ml','embedding')),
  started_at     TIMESTAMPTZ  NOT NULL,
  finished_at    TIMESTAMPTZ,
  status         VARCHAR(20)  NOT NULL
                   CHECK (status IN ('running','completed','failed')),
  records_in     INTEGER,
  records_out    INTEGER,
  error_message  TEXT,
  model_version  VARCHAR(50),
  prompt_version VARCHAR(20),
  metadata       JSONB
);
```

### ai_features

```sql
CREATE TABLE ai_features (
  id             SERIAL PRIMARY KEY,
  entity_type    VARCHAR(50)  NOT NULL,
  entity_id      INTEGER      NOT NULL,
  feature_name   VARCHAR(100) NOT NULL,
  feature_value  FLOAT,
  feature_json   JSONB,
  computed_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  valid_until    TIMESTAMPTZ,
  model_version  VARCHAR(50)
);

CREATE UNIQUE INDEX idx_ai_features_entity_feature
  ON ai_features(entity_type, entity_id, feature_name);
```

### ai_model_versions

```sql
CREATE TABLE ai_model_versions (
  id           SERIAL PRIMARY KEY,
  model_name   VARCHAR(100) NOT NULL,
  version      VARCHAR(20)  NOT NULL,
  model_type   VARCHAR(50)  NOT NULL
                 CHECK (model_type IN ('rule','llm','ml','embedding')),
  description  TEXT,
  parameters   JSONB,
  deployed_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  retired_at   TIMESTAMPTZ,
  deployed_by  INTEGER REFERENCES users(id),
  UNIQUE(model_name, version)
);
```

### ai_feedback

```sql
CREATE TABLE ai_feedback (
  id            SERIAL PRIMARY KEY,
  source_table  VARCHAR(100) NOT NULL,
  source_id     INTEGER      NOT NULL,
  user_id       INTEGER      NOT NULL REFERENCES users(id),
  user_role     VARCHAR(50),
  feedback_type VARCHAR(50)  NOT NULL
                  CHECK (feedback_type IN ('correct','incorrect','helpful','harmful')),
  feedback_note TEXT,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
```

### ai_embeddings (requires pgvector)

```sql
-- Prerequisite
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE ai_embeddings (
  id             SERIAL PRIMARY KEY,
  source_table   VARCHAR(100) NOT NULL,
  source_id      INTEGER      NOT NULL,
  child_id       INTEGER      REFERENCES children(id),
  embedding      vector(768),
  model_version  VARCHAR(50),
  created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  refreshed_at   TIMESTAMPTZ
);

-- HNSW index for fast approximate nearest-neighbour search
CREATE INDEX idx_ai_embeddings_hnsw
  ON ai_embeddings USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
```

---

## PART 4 — Phased Implementation Roadmap

### Phase 1 — Critical Database Fixes

**Goal:** Make the schema safe for production before any user data migrates or AI features launch.

| #    | Task                                                                   | Tables/Objects                                                                                                                                            | Acceptance Criteria                                  |
| ---- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| 1.1  | `SELECT ... FOR UPDATE` in enrollment service                          | `classes`, `enrollment_applications`                                                                                                                      | Concurrent last-seat test: exactly 1 ACTIVE          |
| 1.2  | Capacity enforcement trigger                                           | `classes`, `enrollment_applications`                                                                                                                      | INSERT over capacity raises exception                |
| 1.3  | Add `old_data`, `new_data`, `actor_role`, `request_id` to `audit_logs` | `audit_logs`                                                                                                                                              | Child update produces before/after audit row         |
| 1.4  | Convert `audit_logs.details` to JSONB                                  | `audit_logs`                                                                                                                                              | JSON operators work on `details` column              |
| 1.5  | Audit triggers for 9 sensitive tables                                  | `children`, `parent_profiles`, `enrollment_applications`, `incidents`, `safeguarding_cases`, `health_alerts`, `attendance_logs`, `daily_reports`, `users` | All UPDATEs produce audit rows                       |
| 1.6  | Add `deleted_at` / `deleted_by` to core entities                       | 10 tables                                                                                                                                                 | No hard-delete in API; soft-delete viewable by admin |
| 1.7  | Create `active_*` views                                                | `children`, `enrollments`, `classes`                                                                                                                      | Views exclude soft-deleted rows                      |
| 1.8  | Add `ck_attendance_not_future` and `ck_report_not_future`              | `attendance_logs`, `daily_reports`                                                                                                                        | Future date insert fails                             |
| 1.9  | Add `arrival_time`/`leave_time`/`nap_start`/`nap_end` format CHECKs    | `daily_reports`                                                                                                                                           | Invalid `HH:MM` insert fails                         |
| 1.10 | Add `class_id` to `attendance_logs` + backfill                         | `attendance_logs`, `enrollment_applications`                                                                                                              | Attendance records carry class context               |
| 1.11 | Add medical/allergy/emergency columns to `children`                    | `children`                                                                                                                                                | Fields queryable, role-gated                         |
| 1.12 | Add `reported_by`, `class_id`, `closed_by` to `incidents`              | `incidents`                                                                                                                                               | Incident form captures reporter                      |
| 1.13 | Fix `messages.recipient_id` schema drift; add `is_read`/`read_at`      | `messages`                                                                                                                                                | Column exists; direct message stored                 |
| 1.14 | Apply 10 composite indexes (CONCURRENTLY)                              | multiple                                                                                                                                                  | EXPLAIN shows index usage                            |
| 1.15 | Add `ck_health_alert_severity` CHECK                                   | `health_alerts`                                                                                                                                           | Invalid severity values rejected                     |
| 1.16 | Add `uq_survey_response_per_parent` UNIQUE                             | `survey_responses`                                                                                                                                        | Duplicate submission rejected                        |
| 1.17 | Add `status` Enum + `assigned_to` to `safeguarding_cases`              | `safeguarding_cases`                                                                                                                                      | Open cases queryable by assigned user                |
| 1.18 | Implement waitlist expiry job (pg_cron or APScheduler)                 | `waitlist_entries`                                                                                                                                        | OFFERED entries expire after 48 h                    |
| 1.19 | Migrate rate limiter to Redis                                          | `security.py`, `config.py`                                                                                                                                | Brute-force blocked after process restart            |
| 1.20 | Enable HSTS header in `security.py`                                    | `security.py`                                                                                                                                             | `Strict-Transport-Security` header present           |
| 1.21 | Remove duplicate enum definitions                                      | `models.py`                                                                                                                                               | Single definition per enum class                     |

**Estimated risk:** Medium overall. Data migrations (attendance backfill, details JSONB conversion, survey deduplification) must be scripted and tested against a staging copy before production.

---

### Phase 2 — Rule-Based AI

**Goal:** Deliver measurable AI value using only SQL, window functions, triggers, and scheduled jobs — no LLMs.  
**Dependency:** Phase 1 complete.

| #    | Capability                               | Technique              | Output Table        | Acceptance Criteria                                                            |
| ---- | ---------------------------------------- | ---------------------- | ------------------- | ------------------------------------------------------------------------------ |
| 2.1  | Create `ai_parent_recommendations` table | DDL                    | —                   | Table created, indexes active                                                  |
| 2.2  | Create `ai_manager_alerts` table         | DDL                    | —                   | Table created                                                                  |
| 2.3  | Create `ai_job_logs` table               | DDL                    | —                   | All jobs log start/finish/status                                               |
| 2.4  | Create `ai_features` store               | DDL                    | —                   | Feature rows computed per child                                                |
| 2.5  | Consecutive absence detection            | Window function        | `ai_manager_alerts` | Alert fires for known 3-day test case                                          |
| 2.6  | Allergy precaution alert at check-in     | Full-text search       | `ai_manager_alerts` | Alert appears when child with nut allergy checks in on nut-menu day            |
| 2.7  | Waitlist next-candidate recommendation   | Deterministic SQL rank | `ai_manager_alerts` | Correct child surfaced by `priority_score`                                     |
| 2.8  | Incident hotspot detection               | Z-score SQL            | `ai_manager_alerts` | Alert for class with z > 2.0                                                   |
| 2.9  | Ratio compliance day-of-week forecast    | Moving average SQL     | `ai_manager_alerts` | Alert 3 days before projected breach day                                       |
| 2.10 | Ministry enrollment cohort report        | Cohort SQL             | `kpi_snapshots`     | Matches manual count ± 1                                                       |
| 2.11 | Governance score drop alert              | LAG window             | `ai_manager_alerts` | Alert for 2 consecutive below-60 periods                                       |
| 2.12 | SLA breach detector for safeguarding     | Date comparison job    | `ai_manager_alerts` | Alert fires when `sla_escalation_deadline < NOW()` and `status <> 'ESCALATED'` |

---

### Phase 3 — LLM Integration

**Goal:** Generate natural-language summaries for parents, supervisors, and administrators using a local LLM (Ollama). No external paid APIs.  
**Dependency:** Phase 2 complete. Medical/allergy columns exist. All AI infrastructure tables created.

| #   | Capability                                        | LLM Input                                                                        | LLM Role                              | Guardrail                                                                                       |
| --- | ------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 3.1 | Daily report parent summary                       | Structured feature JSON from `daily_reports` booleans and `nap_duration_minutes` | Narrative wording only                | No raw `notes` if medical keywords detected. Supervisor auto-approves after 6 h unless flagged. |
| 3.2 | Weekly observation narrative for parent portfolio | Domain-level mastery summary, no raw observation text                            | Narrative wording only                | Supervisor sets `human_reviewed = TRUE` before delivery.                                        |
| 3.3 | Incident follow-up letter draft                   | Incident type, severity, date — no child name or PII                             | Draft text for manager to edit        | Manager must edit and explicitly send. LLM cannot send.                                         |
| 3.4 | Admin governance case study                       | Anonymised KPI trends from `governance_scores` and `kpi_snapshots`               | Narrative summary for ministry report | Aggregate only. Min cohort = 5.                                                                 |
| 3.5 | Curriculum activity suggestion                    | `curriculum_outcomes.description` + child's `observations.mastery_level`         | Activity recommendation text          | Linked to indicator codes. Human confirmation before acting.                                    |
| 3.6 | Create `ai_model_versions` table                  | —                                                                                | Version tracking for all LLM models   | Every LLM call records model and prompt version in `ai_parent_recommendations`.                 |
| 3.7 | Create `ai_feedback` table                        | —                                                                                | Cross-cutting user feedback           | Feedback loop informs prompt iteration.                                                         |

**LLM constraints (non-negotiable):**

- LLM receives structured feature JSON only — never raw PII, never raw medical text.
- All LLM outputs stored with `model_version`, `prompt_version`, `confidence`.
- All LLM outputs have `human_reviewed = FALSE` by default.
- LLM cannot make enrollment, medical, safeguarding, legal, or HR decisions.
- No external LLM API calls. All inference runs locally via Ollama.

---

### Phase 4 — Predictive ML

**Goal:** Train lightweight models on historical data for structured prediction.  
**Dependency:** Phase 3 complete. Minimum 6 months of clean historical data from Phase 1 fixes.

| #   | Capability                              | Model Type          | Input Features (from `ai_features` store)                                                                                  | Output                                                             |
| --- | --------------------------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| 4.1 | Child attendance forecast (next 5 days) | ARIMA or Prophet    | Rolling 30-day absence rate, day-of-week, `operating_calendar` flags                                                       | Absence probability per child per day → `ai_features`              |
| 4.2 | Ministry seat demand by governorate     | Linear regression   | `children.date_of_birth` cohorts, historical enrollment rate by `home_governorate`                                         | Demand forecast ± CI → `kpi_snapshots`                             |
| 4.3 | Incident risk score per child           | Logistic regression | Age in months, class, recent absence streak, 90-day incident count                                                         | Risk score 0–1 → `ai_features` with `valid_until = NOW() + 7 days` |
| 4.4 | Staff burnout signal                    | K-means clustering  | Weekly hours from `staff_presence_logs`, incident report count from `incidents.reported_by`, daily report submission count | Cluster label → `ai_manager_alerts` severity HIGH                  |

**Data quality gate:** All Phase 1 constraints must be active before model training to prevent future-dated or missing-class records from corrupting training sets.

---

### Phase 5 — Semantic Search and pgvector

**Goal:** Enable similarity-based retrieval over behavioral observations, activity notes, and incident descriptions.  
**Dependency:** Phase 4. pgvector extension installed on PostgreSQL host.

| #   | Task                                                                        | Technique                                                            | Privacy                                                                              |
| --- | --------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 5.1 | `CREATE EXTENSION IF NOT EXISTS vector;`                                    | DDL                                                                  | N/A                                                                                  |
| 5.2 | Create `ai_embeddings` table + HNSW index                                   | Proposed DDL                                                         | Child IDs retained in restricted table                                               |
| 5.3 | Nightly embedding job: `observations.observation_text`                      | Ollama `nomic-embed-text` → `ai_embeddings`                          | Raw text never stored in embedding table; only embedding vector and source_id        |
| 5.4 | Nightly embedding job: `daily_reports.activities` and `daily_reports.notes` | Same pipeline                                                        | Medical keyword filtering before embedding                                           |
| 5.5 | Similar-behavior matching for supervisor                                    | `<=>` cosine distance                                                | Cross-child results: domain + count only, never names. Min observation age: 30 days. |
| 5.6 | Activity recommendation engine                                              | Cosine similarity to past activities that preceded `EXCEEDS` mastery | Linked to `curriculum_outcomes.indicator_code`                                       |
| 5.7 | Semantic incident search                                                    | Embed `incidents.description`                                        | SUPERVISOR+ role only. Min incident age: 30 days before cross-child use.             |

---

## PART 5 — Executive Summary

### 1. Production Readiness Verdict

**Not production-ready.** The schema has strong structural foundations — well-chosen enums, meaningful CHECK constraints (`ck_checkout_after_checkin`, `ck_capacity_positive`, `ck_age_band_valid`, `ck_parent_identity_validation`, `ck_event_end_after_start`), FK relationships covering all core entities, and a partial analytics cache layer. However, **five critical blockers** will cause data corruption, regulatory failure, or privacy exposure under real production load before any AI features are considered.

---

### 2. Top Five Blockers

| Rank | Blocker                                | Evidence                                                                                                       | Consequence if Unresolved                                                     |
| ---- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 1    | **No row-level lock on enrollment**    | Zero `SELECT ... FOR UPDATE` in codebase; `classes.capacity_total` unguarded                                   | Over-enrollment; regulatory child-to-staff ratio violation                    |
| 2    | **Audit log cannot reconstruct state** | `audit_logs.details` is Text; no `old_data`/`new_data`; `enhanced_audit_trail.py` writes only to Python logger | Legally indefensible for child protection and ministry audit                  |
| 3    | **No medical baseline on children**    | No `medical_notes`, `allergy_notes`, or `emergency_contact` on `children`                                      | Staff cannot query allergies at point of care; AI medical context missing     |
| 4    | **No soft delete on any entity**       | No `deleted_at`/`deleted_by` on `children`, `users`, `parent_profiles`, `enrollment_applications`, `classes`   | Hard deletes destroy historical truth; orphaned incident/safeguarding records |
| 5    | **Waitlist offers never expire**       | `offer_expiry_at` exists; `WAITLIST_OFFER_EXPIRY_HOURS = 48` defined; zero expiry automation found             | Seats permanently locked; priority queue broken; capacity analytics wrong     |

---

### 3. Highest-Value AI Opportunities (Ordered by Immediate Impact)

| Rank | Capability                              | Technique                               | Existing Data Ready?                                                           |
| ---- | --------------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------ |
| 1    | **Daily report parent narrative**       | LLM (Ollama) on structured feature JSON | Yes — `daily_reports` has meal booleans, `nap_duration_minutes`, `activities`  |
| 2    | **Absence wellness signal**             | Pure SQL window function                | Yes — `attendance_logs`, `operating_calendar`, `enrollment_applications`       |
| 3    | **Incident hotspot detection**          | Z-score SQL                             | After Phase 1: needs `incidents.class_id`                                      |
| 4    | **Ministry enrollment cohort forecast** | Cohort SQL                              | Yes — `children.date_of_birth`, `parent_profiles.home_governorate`             |
| 5    | **Observation semantic search**         | pgvector cosine similarity              | Text exists in `observations.observation_text`; needs Phase 5 pgvector install |

---

### 4. What Can Be Built Immediately on Existing Data

| Capability                             | Tables                                        | Technique                                                        |
| -------------------------------------- | --------------------------------------------- | ---------------------------------------------------------------- |
| Enrollment funnel dashboard            | `enrollment_applications`, `classes`          | `COUNT GROUP BY status`                                          |
| Attendance rate by kindergarten        | `attendance_logs`, `enrollment_applications`  | Count present / expected, date-filtered                          |
| Incident severity trend (last 90 days) | `incidents`                                   | `COUNT GROUP BY severity_level, DATE_TRUNC('week', occurred_at)` |
| KPI governance score trend             | `governance_scores`                           | `SELECT + LAG()` window                                          |
| Waitlist priority queue (read-only)    | `waitlist_entries`, `enrollment_applications` | `ORDER BY priority_score DESC`                                   |
| Parent message inbox                   | `messages`                                    | `SELECT WHERE recipient_id = :user_id`                           |
| NPS score trend                        | `survey_responses`                            | `AVG(nps_score) GROUP BY DATE_TRUNC('month', created_at)`        |
| Staff coverage heatmap                 | `staff_presence_logs`, `ratio_compliance`     | `GROUP BY date, kindergarten_id`                                 |

---

### 5. What Requires New Schema Objects

| Requirement                                                                    | Phase   |
| ------------------------------------------------------------------------------ | ------- |
| `old_data`/`new_data` JSONB + audit triggers                                   | Phase 1 |
| `children.medical_notes`, `allergy_notes`, `emergency_contact`                 | Phase 1 |
| `incidents.class_id`, `reported_by`, `closed_by`                               | Phase 1 |
| `attendance_logs.class_id`                                                     | Phase 1 |
| `deleted_at`/`deleted_by` + `active_*` views                                   | Phase 1 |
| Capacity enforcement trigger                                                   | Phase 1 |
| Waitlist expiry pg_cron job                                                    | Phase 1 |
| 10 composite indexes                                                           | Phase 1 |
| `safeguarding_cases.status` Enum + `assigned_to`                               | Phase 1 |
| `ai_parent_recommendations`, `ai_manager_alerts`, `ai_job_logs`, `ai_features` | Phase 2 |
| `ai_model_versions`, `ai_feedback`                                             | Phase 3 |
| pgvector extension + `ai_embeddings` table                                     | Phase 5 |

---

### 6. What Must Never Be Automated Without Human Approval

These decisions require an explicit human approval step regardless of AI confidence level. This constraint is enforced at the database level via `human_reviewed = FALSE` default and the API layer refusing to surface content without an approval record.

| Decision                                                   | Reason                                   |
| ---------------------------------------------------------- | ---------------------------------------- |
| Safeguarding case escalation or closure                    | Child protection law; criminal liability |
| Medical or allergy alert content sent to parent            | Medical accuracy; harm risk if incorrect |
| Incident description content in any outbound communication | Legal and medical accuracy               |
| Enrollment acceptance or rejection                         | Administrative and regulatory authority  |
| Observation summary delivered to parent                    | Educational professional judgment        |
| Staff burnout flag surfaced to HR or manager               | Employment law; fairness                 |
| Any LLM output with `confidence < 0.70`                    | Accuracy threshold — do not surface      |

---

_End of KinJo Platform PostgreSQL Production Readiness & AI Integration Review_
