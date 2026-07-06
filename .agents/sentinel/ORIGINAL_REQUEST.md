# Original User Request

## Initial Request — 2026-07-06T18:55:15Z

# Teamwork Project Prompt

Audit, redesign, and implement the Health & Safety page (`/safety`) and incident management workflows in the KinJo application, including full UI/UX, backend API, database optimizations, and a comprehensive audit report.

Working directory: `d:\Final Version`
Integrity mode: development

## Requirements

### R1. Incident Management & Data
Implement a full incident lifecycle (Open, Under Investigation, Action Required, Resolved, Closed) with history tracking, owner assignment, and timestamps. Connect the UI to real API-driven data, eliminating hardcoded samples. Include secure file attachments for medical reports and photos. Use existing vanilla architecture where possible rather than introducing large new frameworks.

### R2. Advanced UI/UX & Filtering
Implement comprehensive table filtering (date, child, type, severity, status, text search) with saved states. Enhance the incident table with sorting, pagination, and empty/loading/error states. Add export capabilities (PDF, Excel, Print) and ensure mobile responsiveness and RTL alignment consistency.

### R3. Health Alerts & Dashboard Metrics
Build a real Health Alerts section (allergies, medications, conditions) and dashboard summary cards showing open, high-severity, and resolved incidents.

### R4. Security, Permissions & Performance
Enforce role-based access control (nursery staff only see authorized children). Optimize database queries (N+1), pagination strategy, and frontend rendering.

### R5. Audit Report
Deliver a comprehensive audit report detailing bugs found, severity, root cause, exact files affected, and recommended fixes across UI, Security, Accessibility, and Performance.

## Acceptance Criteria

### Verification & Testing
- [ ] Automated Test Script: The team must write a Python verification script that seeds 50 incidents (various statuses, types, dates) and programmatically asserts that the filtering, pagination, and sorting APIs return the mathematically correct subsets.
- [ ] Security Verification: The team must write a test proving that a Supervisor from KG A cannot access or query incidents belonging to a child in KG B.
- [ ] Export Verification: The system must successfully generate a parseable CSV/Excel export of the filtered incident table.
- [ ] UI Artifact: The team must produce a Markdown artifact linking to the modified files, proving RTL alignment classes and responsive wrappers were added to the tables.
