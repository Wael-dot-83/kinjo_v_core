# 68 — Mobile Capability Gap Audit & Roadmap

**Date:** 2026-08-09  
**Module:** KinJo Flutter Mobile Operational Client  
**Branch:** main (`3a1ba45d245d1e9638cfa5558bbdd38aac9bf955`)  

---

## 1. Executive Summary

This audit establishes the baseline capability inventory for the KinJo mobile application across the three core operational roles (**Supervisor**, **Manager**, **Parent**). 

The mobile application has transitioned from static placeholders to a dashboard viewer displaying real backend statistics. To bring the application to production readiness, mobile must evolve into a **full operational client** that consumes existing, canonical FastAPI backend endpoints for daily reporting, attendance management, absence requests, and messaging without duplicating backend business rules.

---

## 2. Comprehensive Role Capability Matrix

| Capability / Workflow | Parent | Supervisor | Manager | Backend API Exists? | Canonical Endpoint | Current Mobile Status | Target Phase |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| **Authentication & Token Storage** | ✅ | ✅ | ✅ | ✅ | `POST /api/auth/login`<br>`GET /api/users/me`<br>`POST /api/auth/logout` | **Implemented** (Secure storage, JWT Bearer) | Phase 5–6 |
| **Dashboard Operational View** | ✅ | ✅ | ✅ | ✅ | `GET /api/parent/dashboard`<br>`GET /api/supervisor/dashboard`<br>`GET /api/manager/dashboard` | **Implemented** (Real API integration with error retry) | Baseline |
| **Daily Report Roster (Batch Filing)** | ❌ | ✅ | ❌ | ✅ | `POST /api/daily-reports/batch` | **Pending Phase 2** | Priority 1 |
| **Single Child Daily Report Form** | ❌ | ✅ | ❌ | ✅ | `POST /api/daily-reports/create` | **Pending Phase 2** | Priority 1 |
| **Supervisor Attendance Check-in/out** | ❌ | ✅ | ❌ | ✅ | `POST /api/attendance/check-in`<br>`POST /api/attendance/check-out` | **Pending Phase 2** | Priority 2 |
| **Supervisor Child Details View** | ❌ | ✅ | ❌ | ✅ | `GET /api/supervisor/children` | **Pending Phase 2** | Priority 2 |
| **Manager Daily Report Review** | ❌ | ❌ | ✅ | ✅ | `GET /api/manager/daily-reports`<br>`PUT /api/manager/daily-reports/{id}/approve` | **Pending Phase 3** | Priority 3 |
| **Manager Absence Request Review** | ❌ | ❌ | ✅ | ✅ | `GET /api/attendance/absence-requests`<br>`PUT /api/manager/absence-requests/{id}` | **Pending Phase 3** | Priority 3 |
| **Manager Class Overview** | ❌ | ❌ | ✅ | ✅ | `GET /api/manager/dashboard` (Classes embedded) | **Implemented** (In dashboard view) | Baseline |
| **Parent Daily Report Viewing** | ✅ | ❌ | ❌ | ✅ | `GET /api/daily-reports/child/{id}` | **Pending Phase 4** | Priority 4 |
| **Parent Attendance History** | ✅ | ❌ | ❌ | ✅ | `GET /api/parent/attendance` | **Pending Phase 4** | Priority 4 |
| **Parent Absence Request Submission** | ✅ | ❌ | ❌ | ✅ | `POST /api/attendance/absence-requests` | **Pending Phase 4** | Priority 4 |
| **Parent Child Detail View** | ✅ | ❌ | ❌ | ✅ | `GET /api/parent/children` | **Pending Phase 4** | Priority 4 |
| **Bilingual Support (AR/EN)** | ✅ | ✅ | ✅ | ✅ | `Accept-Language: ar/en` | **Partial** (Dynamic AR/EN string switching required) | Phase 8 |
| **Rate Limit & Security UX** | ✅ | ✅ | ✅ | ✅ | `HTTP 429` Handling | **Partial** (Requires distinct error UX for 429/401/403) | Phase 5 |

---

## 3. High-Priority Workflow Architecture

### A. Supervisor Operational Priority (Batch Daily Reports)
The supervisor's primary operational task is filing daily reports for children in their assigned class.
* **Canonical Contract:** `POST /api/daily-reports/batch`
* **Response Status:** `207 Multi-Status`
* **Mobile UX Requirements:**
  1. Display class roster showing children needing reports today vs already reported vs skipped.
  2. Provide top-level default controls (Default arrival `08:00`, leave `14:00`, meals provided).
  3. Allow per-child overrides (Mood selector, nap time, individual notes, skip toggle).
  4. Explicitly process the `207 Multi-Status` payload to show created, skipped, duplicate, and failed entries.
  5. Provide non-duplicating retry for failed items.

### B. Manager Operational Priority (Absence Requests & Daily Report Approvals)
* **Canonical Contracts:** `GET /api/attendance/absence-requests`, `PUT /api/manager/absence-requests/{id}`, `PUT /api/manager/daily-reports/{id}/approve`
* **Mobile UX Requirements:**
  1. Review pending parent absence requests with reason, child name, and requested date range.
  2. Approve or reject requests with confirmation dialog and error feedback.
  3. Review submitted daily reports and mark as approved/reviewed.

### C. Parent Operational Priority (Daily Reports & Absence Requests)
* **Canonical Contracts:** `GET /api/daily-reports/child/{child_id}`, `POST /api/attendance/absence-requests`
* **Mobile UX Requirements:**
  1. Tap a child card to view today's detailed report (Mood, Meals, Nap, Activities, Notes).
  2. Submit absence requests specifying child, start date, end date, and reason.
  3. View historical attendance calendar.

---

## 4. Deferred & Out-of-Scope Items

1. **Push Notifications (FCM):** Server registration endpoint `/api/notifications/register-device` is not mounted on backend; deferred until backend push infrastructure is enabled.
2. **Admin Mobile Interface:** Admin role is restricted to web operations; mobile correctly rejects Admin login attempts with clear role guidance.
3. **Database Schema Modifications:** Zero backend schema changes will be made; all mobile features consume existing backend APIs.
