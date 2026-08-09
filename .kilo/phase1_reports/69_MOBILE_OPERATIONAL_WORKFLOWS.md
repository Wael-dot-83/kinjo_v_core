# 69 — Mobile Operational Workflows Implementation

**Date:** 2026-08-09  
**Module:** KinJo Flutter Mobile Operational Client  
**Status:** Implemented & Verified  

---

## 1. Supervisor Operational Workflows

### A. Daily-Report Roster Batch Submission
* **Contract:** `POST /api/daily-reports/batch`
* **Request Schema:**
  ```json
  {
    "date": "2026-08-09",
    "arrival_time": "08:00",
    "leave_time": "14:00",
    "breakfast": true,
    "snack": true,
    "milk": true,
    "lunch": true,
    "children": [
      {
        "child_id": 101,
        "mood": "happy",
        "health_notes": "",
        "activities": "رسم ولعب بالصلصال",
        "notes": "طفل ممتاز اليوم",
        "skip": false
      }
    ]
  }
  ```
* **Response Status (`207 Multi-Status`):**
  ```json
  {
    "date": "2026-08-09",
    "created": 1,
    "skipped": 0,
    "failed": 0,
    "results": [
      { "child_id": 101, "status": "created", "report_id": 501 },
      { "child_id": 102, "status": "skipped", "detail": "Skipped by supervisor" },
      { "child_id": 103, "status": "failed", "code": 409, "detail": "Daily report for this child and date already exists" }
    ]
  }
  ```
* **Mobile Screen Component:** `SupervisorRosterScreen` ([`mobile/lib/screens/supervisor_roster_screen.dart`](file:///d:/Final%20Version_mvp_ADMIN/mobile/lib/screens/supervisor_roster_screen.dart))
* **Multi-Status UI:** Displays a dedicated dialog parsing `created`, `skipped`, and `failed` counts with individual per-child status indicators and error details. Non-duplicating retry updates status without duplicating existing reports.

---

## 2. Manager Operational Workflows

### A. Absence Request Review & Decisions
* **Contract:** `GET /api/attendance/absence-requests`, `POST /api/attendance/absence-requests/{id}/approve`, `POST /api/attendance/absence-requests/{id}/reject`
* **Mobile Screen Component:** `ManagerOperationsScreen` ([`mobile/lib/screens/manager_operations_screen.dart`](file:///d:/Final%20Version_mvp_ADMIN/mobile/lib/screens/manager_operations_screen.dart))
* **Workflow:** Tab 1 lists pending parent absence requests with child name, parent name, requested dates, and reason. The manager can approve or reject with instant feedback and list refresh.

### B. Daily Report Approvals
* **Contract:** `GET /api/manager/daily-reports`, `POST /api/daily-reports/{id}/approve`
* **Workflow:** Tab 2 lists daily reports in `SUBMITTED` state and allows one-tap manager approval to publish to parents.

---

## 3. Parent Operational Workflows

### A. Child Reports Feed & Viewer
* **Contract:** `GET /api/daily-reports/child/{child_id}`
* **Mobile Screen Component:** `ParentOperationsScreen` ([`mobile/lib/screens/parent_operations_screen.dart`](file:///d:/Final%20Version_mvp_ADMIN/mobile/lib/screens/parent_operations_screen.dart))
* **Workflow:** Parents can tap any of their children to view published daily reports with date, mood, meal status, and teacher notes.

### B. Absence Request Submission
* **Contract:** `POST /api/attendance/absence-requests`
* **Workflow:** Dialog allows parents to pick an active child, select start and end dates, specify the absence reason, and submit to the kindergarten manager.

---

## 4. Authentication & Error UX Handling

* **Rate Limit Handling (`429 Too Many Requests`):** Rejects invalid rapid login attempts with a distinct amber rate limit alert:
  *"لقد تجاوزت عدد المحاولات المسموح بها. يُرجى الانتظار قليلاً ثم المحاولة مرة أخرى."*
* **Invalid Credentials (`401 Unauthorized`):** Displays red error alert: *"اسم المستخدم أو كلمة المرور غير صحيحة."*
* **Admin Mobile Fallback:** ADMIN login on mobile renders a clean guidance screen directing the user to the web portal.
