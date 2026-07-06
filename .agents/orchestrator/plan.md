# Plan for KinJo Health & Safety Page and Incident Management

## 1. Initial Scan & Checklist
- Use a broad-sweep subagent to audit the existing Health & Safety page (`/safety`) and incident management workflows.
- Identify current implementation details, gaps against the requirements, and required files for updates.

## 2. Implementation Batches
- **Batch 1: Incident Management & Data (R1 & R4)**
  - Implement full incident lifecycle (Open, Under Investigation, Action Required, Resolved, Closed).
  - Setup history tracking, owner assignment, timestamps.
  - Connect UI to real API-driven data.
  - Implement secure file attachments for medical reports/photos.
  - Enforce role-based access control (nursery staff see only authorized children).
  - Optimize DB queries (N+1).
- **Batch 2: Advanced UI/UX & Filtering (R2)**
  - Implement table filtering (date, child, type, severity, status, text search) with saved states.
  - Enhance table with sorting, pagination, empty/loading/error states.
  - Add export capabilities (PDF, Excel, Print).
  - Ensure mobile responsiveness and RTL alignment consistency.
- **Batch 3: Health Alerts & Dashboard Metrics (R3)**
  - Build Health Alerts section (allergies, medications, conditions).
  - Build dashboard summary cards (open, high-severity, resolved incidents).

## 3. Verification & Testing (Role 4)
- Write automated Python verification script for filtering, pagination, and sorting logic (seeding 50 incidents).
- Write security test for RBAC (Supervisor from KG A vs KG B).
- Verify CSV/Excel export.
- Run `py_compile`, `ruff`, and specific Python tests.
- Verify CSRF, links, globals.

## 4. Independent Adversarial Review (Role 3)
- Spawn a fresh independent adversarial reviewer to check all changes.
- Ensure all P1/P2/P3 issues are fixed.
- Check CSRF, route registrations, duplication, etc.
- Iterate if issues found.

## 5. Final Report & Output (R5 & Verdict)
- Generate Markdown artifact for UI proofs.
- Deliver comprehensive audit report with explicit verdict `PRODUCTION READY`.
