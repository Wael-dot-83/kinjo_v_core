# Manual integration tests

These require a **live, populated database** and are **not part of the automated suite**.

## Why they live here

They previously sat at the repository root. `pytest.ini` sets `testpaths = tests`, so
nothing ever collected them: **74 test functions across 5 files, run by no CI job and
no local `pytest` invocation.** They looked like coverage and provided none.

They are not broken suite tests. They open `database.SessionLocal()` directly rather
than using the `test_db` fixture, so they read whatever `DATABASE_URL` points at
instead of the per-test in-memory schema. Against the default test database their
tables do not exist and roughly 45 of the 74 fail with `OperationalError` — by
construction, not by regression.

Moving them into `tests/` unchanged would have added those ~45 failures to the gate;
deleting them would have destroyed deliberate integration coverage. So they are kept,
marked, and deselected by default.

## Running them

They are auto-marked `manual` by `conftest.py` here, and `pytest.ini` deselects that
marker by default. To run them, point `DATABASE_URL` at a populated database and
opt in:

```bash
DATABASE_URL=postgresql://... python -m pytest tests/manual -m manual
```

Expect failures against an empty database — that is the point of the marker.

## If you touch them

The honest options are to finish them (convert to the `test_db` fixture so they join
the suite) or to delete them. Leaving them half-wired is what produced the original
problem. See `.kilo/phase1_reports/20_RECONCILED_IMPLEMENTATION_BACKLOG.md`, **D-6**.
