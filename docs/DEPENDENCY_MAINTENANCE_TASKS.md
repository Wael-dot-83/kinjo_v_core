# Dependency Maintenance Tasks

## TASK-DEP-001: Eliminate `datetime.utcnow()` Deprecation Warnings from Auth Stack

- Status: Open
- Priority: Medium
- Blocking: No
- Opened: 2026-02-11
- Scope: Authentication/JWT dependency chain and internal UTC timestamp usage

### Problem

Test runs emit deprecation warnings from `python-jose` (`jose/jwt.py`) due to `datetime.utcnow()` usage, which is deprecated in Python 3.13+.

### Objectives

- Remove deprecation warnings originating from JWT token handling.
- Keep token issuance/validation behavior unchanged.
- Preserve backward compatibility for existing signed tokens where applicable.

### Proposed Work

1. Audit current version constraints for `python-jose` in dependency manifests.
2. Evaluate latest compatible release (or maintained fork) that replaces `datetime.utcnow()` with timezone-aware APIs.
3. If no upstream fix is available, implement a controlled patch strategy:
   - Vendor patch or local wrapper with timezone-aware datetime handling.
   - Keep patch isolated and documented.
4. Add regression tests for token generation/verification timestamps and expiry behavior.
5. Run full test suite and compare warning baseline before/after.

### Acceptance Criteria

- No `datetime.utcnow()` deprecation warnings from `jose/jwt.py` during `pytest` runs.
- Auth and token tests remain green.
- Dependency/patch decision documented with rollback notes.
