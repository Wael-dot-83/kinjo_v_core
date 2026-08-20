"""ADMIN-PERF-001 — baseline measurement for the admin report endpoints.

This records timings. It does not gate on them.

The specification sets a 500ms p95 budget at 1,375 kindergartens and 20,000
children. Asserting that number before anything has been measured would bake in
a target nobody has earned; if the seeded baseline already sits inside it, the
whole performance phase needs re-justifying, and that is much cheaper to learn
now than after a materialized view has been built. So the assertion here is
HTTP 200, and the numbers are written to an artifact for the branch that
follows.

Postgres only. The default SQLite path cannot answer a question about index
selection, and the schema it builds is not the schema that ships (#97).

Seeding is at target scale, so it is slow (single-digit minutes). The fixture is
session-scoped and the module carries the `slow` marker.
"""

import json
import os
import random
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

import models
from conftest import _IS_POSTGRES, TestingSessionLocal, bearer_headers, engine

pytestmark = [
    pytest.mark.slow,
    # The suite runs at --timeout=30. Seeding at target scale and then timing
    # the endpoints needs far longer, and the first run showed why: an endpoint
    # can exceed 30s outright on this population, which is the measurement, not
    # a hang.
    pytest.mark.timeout(1800),
    pytest.mark.skipif(
        not _IS_POSTGRES,
        reason="performance baseline requires the TEST_DATABASE_URL Postgres path",
    ),
]

# Deterministic: the same seed must produce the same population, or successive
# baselines are not comparable.
SEED = 20260820
TARGET_KINDERGARTENS = 1375
TARGET_CHILDREN = 20000

GOVERNORATES = {
    "Amman": ["Amman", "Wadi Al-Seer", "Marka", "Sahab"],
    "Irbid": ["Irbid", "Al-Ramtha", "Al-Koura"],
    "Zarqa": ["Zarqa", "Al-Ruseifa", "Al-Hashimiyah"],
    "Balqa": ["Salt", "Fuheis", "Deir Alla"],
    "Madaba": ["Madaba", "Dhiban"],
    "Mafraq": ["Mafraq", "Al-Ruwaished"],
    "Karak": ["Al-Karak", "Al-Qasr"],
    "Tafilah": ["Tafilah", "Al-Hasa"],
    "Ma'an": ["Ma'an", "Petra"],
    "Ajloun": ["Ajloun", "Kofranjah"],
    "Jerash": ["Jerash", "Sakib"],
    "Aqaba": ["Aqaba", "Al-Quwayrah"],
}
# Amman-weighted, roughly matching the real distribution.
GOV_POOL = (
    ["Amman"] * 5 + ["Irbid"] * 3 + ["Zarqa"] * 3 + ["Balqa"] * 2 + ["Madaba"] * 2
    + ["Mafraq", "Karak", "Tafilah", "Ma'an", "Ajloun", "Jerash", "Aqaba"]
)

ENDPOINTS = [
    ("overview", "/api/admin/reports/overview?level=jordan"),
    ("children_summary", "/api/admin/reports/children/summary?level=jordan"),
    ("compliance", "/api/admin/reports/compliance?level=jordan"),
    ("data_quality", "/api/admin/reports/data-quality?level=jordan"),
    ("risk_ranking", "/api/admin/reports/risk-ranking?level=jordan"),
    ("children_geography", "/api/admin/reports/children/geography?level=jordan"),
    (
        "compliance_governorate",
        "/api/admin/reports/compliance?level=governorate&governorate=Amman",
    ),
]


def _bulk(conn, table, rows, chunk=2000):
    """Core executemany in chunks. The ORM is far too slow at this scale."""
    for i in range(0, len(rows), chunk):
        conn.execute(table.insert(), rows[i:i + chunk])


@pytest.fixture(scope="module")
def seeded_at_scale(_schema_source):
    """Build a 1,375 kindergarten / 20,000 child population, once.

    Every field here was read off models.py. Notable NOT NULL columns that a
    naive fixture misses: Kindergarten needs address_line and contact_phone;
    Class needs class_code, min_age_months and max_age_months; Child needs
    parent_id plus father_name and the three mother_* fields; DailyReport needs
    submitted_by and arrival_time.
    """
    rng = random.Random(SEED)
    today = date.today()

    # Idempotent: seeding 20,000 children takes minutes, so a re-run against a
    # database that already holds the population reuses it rather than
    # colliding on ix_users_username. Also makes the fixture safe to interrupt.
    with engine.connect() as probe:
        existing = probe.execute(
            models.Kindergarten.__table__.select().where(
                models.Kindergarten.__table__.c.license_number.like("PERF-%")
            )
        ).fetchall()
        if len(existing) >= TARGET_KINDERGARTENS:
            children = probe.execute(
                models.Child.__table__.select().where(
                    models.Child.__table__.c.last_name == "Perf"
                )
            ).fetchall()
            classes = probe.execute(
                models.Class.__table__.select().where(
                    models.Class.__table__.c.class_code.like("C%")
                )
            ).fetchall()
            if len(children) >= TARGET_CHILDREN:
                yield {
                    "kindergartens": len(existing),
                    "children": len(children),
                    "classes": len(classes),
                    "reused": True,
                }
                return

    with engine.begin() as conn:
        # A single parent profile owns every child. Child.parent_id is NOT NULL
        # and this test measures report aggregation, not parent fan-out.
        conn.execute(
            models.User.__table__.insert(),
            [{
                "username": "perf_parent",
                "hashed_password": "x" * 60,
                "role": models.UserRole.PARENT,
                "status": models.UserStatus.ACTIVE,
                "public_id": "perf-parent-0000",
            }],
        )
        parent_user_id = conn.execute(
            models.User.__table__.select().where(
                models.User.__table__.c.username == "perf_parent"
            )
        ).first().id
        conn.execute(
            models.ParentProfile.__table__.insert(),
            [{
                "user_id": parent_user_id,
                "first_name": "Perf",
                "last_name": "Parent",
                "phone_number": "+962790000000",
                "gender": models.Gender.MALE,
                "nationality": "Jordanian",
                "home_governorate": "Amman",
                "home_district": "Amman",
                "home_area": "Abdoun",
                "home_address_line": "1 Test Street",
            }],
        )
        parent_id = conn.execute(
            models.ParentProfile.__table__.select().where(
                models.ParentProfile.__table__.c.user_id == parent_user_id
            )
        ).first().id

        # ── kindergartens ───────────────────────────────────────────────────
        kgs = []
        for i in range(TARGET_KINDERGARTENS):
            gov = rng.choice(GOV_POOL)
            kgs.append({
                "name_ar": f"حضانة {gov} {i}",
                "name_en": f"Kindergarten {gov} {i}",
                "license_number": f"PERF-{i:06d}",
                "governorate": gov,
                "district": rng.choice(GOVERNORATES[gov]),
                "area": f"Area {rng.randint(1, 6)}",
                "address_line": f"{i} Test Street",
                "contact_phone": f"+96279{i:07d}",
                "status": models.KindergartenStatus.ACTIVE,
                # ~8% with no coordinates: a risk-score input.
                "latitude": None if i % 12 == 0 else rng.uniform(29.5, 33.3),
                "longitude": None if i % 12 == 0 else rng.uniform(35.0, 39.2),
                "public_id": f"perf-kg-{i:06d}",
            })
        _bulk(conn, models.Kindergarten.__table__, kgs)
        kg_ids = [
            r.id for r in conn.execute(
                models.Kindergarten.__table__.select().where(
                    models.Kindergarten.__table__.c.license_number.like("PERF-%")
                )
            )
        ]

        # ── classes: 1-4 per kindergarten ───────────────────────────────────
        classes = []
        for kg_id in kg_ids:
            for c in range(rng.randint(1, 4)):
                classes.append({
                    "kindergarten_id": kg_id,
                    "name_ar": f"صف {c + 1}",
                    "name_en": f"Class {c + 1}",
                    "class_code": f"C{kg_id}-{c}",
                    "age_group": "AGE_2_4",
                    "capacity_total": rng.choice([15, 20, 25, 30]),
                    "min_age_months": 24,
                    "max_age_months": 48,
                    "is_active": True,
                })
        _bulk(conn, models.Class.__table__, classes)
        class_rows = [
            (r.id, r.kindergarten_id) for r in conn.execute(
                models.Class.__table__.select().where(
                    models.Class.__table__.c.class_code.like("C%")
                )
            )
        ]

        # ── children ────────────────────────────────────────────────────────
        children = []
        for i in range(TARGET_CHILDREN):
            # ~3% with no usable date of birth: a data-quality input. The column
            # is NOT NULL, so "missing" is modelled as an out-of-range age
            # rather than a null.
            age_days = rng.randint(365, 300) if False else rng.randint(730, 2190)
            if i % 33 == 0:
                age_days = rng.randint(60, 300)  # too young for a nursery
            children.append({
                "parent_id": parent_id,
                "first_name": f"Child{i}",
                "last_name": "Perf",
                "gender": rng.choice([models.Gender.MALE, models.Gender.FEMALE]),
                "date_of_birth": today - timedelta(days=age_days),
                "father_name": "Perf Father",
                "mother_first_name": "Perf",
                "mother_last_name": "Mother",
                "mother_nationality": "Jordanian",
                "public_id": f"perf-child-{i:06d}",
            })
        _bulk(conn, models.Child.__table__, children)
        child_ids = [
            r.id for r in conn.execute(
                models.Child.__table__.select().where(
                    models.Child.__table__.c.last_name == "Perf"
                )
            )
        ]

        # ── enrollments ─────────────────────────────────────────────────────
        enrollments = []
        for idx, child_id in enumerate(child_ids):
            class_id, kg_id = class_rows[idx % len(class_rows)]
            active = idx % 10 != 0
            enrollments.append({
                "child_id": child_id,
                "kindergarten_id": kg_id,
                "class_id": class_id,
                "status": (
                    models.EnrollmentStatus.ACTIVE if active
                    else models.EnrollmentStatus.PENDING_REVIEW
                ),
                # uq_enrollment_child_active is unique on (child_id, is_active),
                # so only the active rows may carry True.
                "is_active": True if active else None,
                "public_id": f"perf-enr-{idx:06d}",
            })
        _bulk(conn, models.EnrollmentApplication.__table__, enrollments)

        # ── supervisors, with ~8% of classes deliberately unsupervised ──────
        supervisors = [{
            "username": f"perf_sup_{i}",
            "hashed_password": "x" * 60,
            "role": models.UserRole.SUPERVISOR,
            "status": models.UserStatus.ACTIVE,
            "public_id": f"perf-sup-{i:06d}",
        } for i in range(200)]
        _bulk(conn, models.User.__table__, supervisors)
        sup_ids = [
            r.id for r in conn.execute(
                models.User.__table__.select().where(
                    models.User.__table__.c.username.like("perf_sup_%")
                )
            )
        ]
        assignments = [
            {
                "class_id": class_id,
                "supervisor_id": sup_ids[i % len(sup_ids)],
                "start_date": today - timedelta(days=120),
            }
            for i, (class_id, _kg) in enumerate(class_rows)
            if i % 12 != 0
        ]
        _bulk(conn, models.SupervisorAssignment.__table__, assignments)

    yield {
        "kindergartens": len(kg_ids),
        "children": len(child_ids),
        "classes": len(class_rows),
    }


class TestPopulationIsAtScale:
    def test_seed_reached_target(self, seeded_at_scale):
        """A baseline taken on a toy population measures nothing."""
        assert seeded_at_scale["kindergartens"] >= TARGET_KINDERGARTENS
        assert seeded_at_scale["children"] >= TARGET_CHILDREN


class TestAdminReportBaseline:
    def test_endpoints_respond_and_are_measured(
        self, seeded_at_scale, client, admin_token, record_property
    ):
        """Record response times. Assert 200, not a threshold.

        The specification's 500ms p95 is reported here, never enforced. Once
        3c-3f land, re-measure and decide whether the budget is achievable or
        whether the budget is wrong.
        """
        results = []

        for name, url in ENDPOINTS:
            samples = []
            for _ in range(5):
                start = time.perf_counter()
                response = client.get(url, headers=bearer_headers(admin_token))
                elapsed_ms = (time.perf_counter() - start) * 1000
                assert response.status_code == 200, f"{name}: {response.text[:200]}"
                samples.append(elapsed_ms)

            samples.sort()
            p95 = samples[int(len(samples) * 0.95) - 1]
            results.append({
                "endpoint": name,
                "url": url,
                "min_ms": round(samples[0], 1),
                "median_ms": round(samples[len(samples) // 2], 1),
                "p95_ms": round(p95, 1),
                "max_ms": round(samples[-1], 1),
                "spec_budget_ms": 500,
                "within_spec_budget": p95 < 500,
            })
            record_property(f"{name}_p95_ms", round(p95, 1))

        payload = {
            "population": seeded_at_scale,
            "note": (
                "Baseline only. The spec's 500ms p95 is reported, not gated. "
                "Re-measure after ADMIN-PERF-001 indexes, caching and the MV."
            ),
            "endpoints": results,
        }
        out = Path(os.environ.get("PERF_ARTIFACT_DIR", ".")) / "admin_perf_baseline.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        print("\n=== admin report baseline ===")
        for row in results:
            flag = "" if row["within_spec_budget"] else "  <-- over spec budget"
            print(f"  {row['endpoint']:24} p95 {row['p95_ms']:8.1f} ms{flag}")
