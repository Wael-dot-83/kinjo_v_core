# Endpoint Inventory and Implementation Status

## Executive Summary

- **Total Endpoints Identified**: 291 across all modules (inventory parse; refresh after changes)
- **Current Coverage**: overall TBD; missing_endpoints.py 38% (last recorded)
- **Priority**: Missing Endpoints (Phase 1) - Raise from 38% -> 70% -> 100%

## Router Prefixes

- `/api` - Core API endpoints (missing_endpoints.py)
- `/comm` - Communication endpoints (communication_service.py)
- `/api` - Safety endpoints (safety_service.py)
- `/api` - KPI endpoints (kpi_service.py)
- `/api` - Analytics endpoints (analytics_service.py)
- `/api` - Admin endpoints (admin_endpoints.py)
- `/api` - Audit endpoints (audit_service.py)
- `/monitoring` - Monitoring endpoints (monitoring_endpoints.py)
- `/ws` - Analytics WebSocket (analytics_ws.py)
- `/` - Frontend HTML routes (frontend.py)
- `/` - Direct app routes (main.py)

## Endpoint Inventory (Deduplicated)

### Core API Endpoints (missing_endpoints.py) - 38% coverage (last recorded)

| Method | Path                                                       | Status         | Owner Module         | Tests Added | Notes                          |
| ------ | ---------------------------------------------------------- | -------------- | -------------------- | ----------- | ------------------------------ |
| GET | /api/users/me | Implemented | missing_endpoints.py | Yes | User profile endpoint |
| POST | /api/users/change-password | Implemented | missing_endpoints.py | Yes | Password change |
| GET | /api/users | Implemented | missing_endpoints.py | Yes | List users with pagination |
| GET | /api/users/export | Implemented | missing_endpoints.py | Yes | Export users to CSV |
| POST | /api/users | Implemented | missing_endpoints.py | Yes | Create user |
| POST | /api/staff/create | Implemented | missing_endpoints.py | Yes | Create staff user |
| GET | /api/users/{user_id} | Implemented | missing_endpoints.py | Yes | Get user by ID |
| PUT | /api/users/{user_id} | Implemented | missing_endpoints.py | Yes | Update user |
| DELETE | /api/users/{user_id} | Implemented | missing_endpoints.py | Yes | Delete user |
| POST | /api/users/{user_id}/admin-reset-password | Implemented | missing_endpoints.py | Yes | Admin password reset |
| POST | /api/users/request-password-reset | Implemented | missing_endpoints.py | Yes | Request password reset |
| POST | /api/users/reset-password | Implemented | missing_endpoints.py | Yes | Reset password |
| POST | /api/users/bulk-status-update | Implemented | missing_endpoints.py | Yes | Bulk status update |
| POST | /api/users/bulk-delete | Implemented | missing_endpoints.py | Yes | Bulk delete users |
| POST | /api/users/bulk-create | Implemented | missing_endpoints.py | Yes | Bulk create users |
| POST | /api/kindergartens | Implemented | missing_endpoints.py | Yes | Create kindergarten |
| GET | /api/kindergartens | Implemented | missing_endpoints.py | Yes | List kindergartens |
| GET | /api/kindergartens/{kindergarten_id} | Implemented | missing_endpoints.py | Yes | Get kindergarten by ID |
| PUT | /api/kindergartens/{kindergarten_id} | Implemented | missing_endpoints.py | Yes | Update kindergarten |
| DELETE | /api/kindergartens/{kindergarten_id} | Implemented | missing_endpoints.py | Yes | Delete kindergarten |
| POST | /api/kindergartens/{kindergarten_id}/archive | Implemented | missing_endpoints.py | Yes | Archive kindergarten |
| POST | /api/kindergartens/{kindergarten_id}/restore | Implemented | missing_endpoints.py | Yes | Restore kindergarten |
| GET | /api/kindergartens/{kindergarten_id}/services | Implemented | missing_endpoints.py | Yes | Get kindergarten services |
| POST | /api/kindergartens/{kindergarten_id}/services | Implemented | missing_endpoints.py | Yes | Add kindergarten service |
| PUT | /api/kindergartens/{kindergarten_id}/services/{service_id} | Implemented | missing_endpoints.py | Yes | Update kindergarten service |
| DELETE | /api/kindergartens/{kindergarten_id}/services/{service_id} | Implemented | missing_endpoints.py | Yes | Delete kindergarten service |
| POST | /api/classes | Implemented | missing_endpoints.py | Yes | Create class |
| GET | /api/classes | Implemented | missing_endpoints.py | Yes | List classes |
| GET | /api/classes/{class_id}/capacity-status | Implemented | missing_endpoints.py | Yes | Get class capacity status |
| GET | /api/classes/{class_id} | Implemented | missing_endpoints.py | Yes | Get class by ID |
| PUT | /api/classes/{class_id} | Implemented | missing_endpoints.py | Yes | Update class |
| PUT | /api/classes/{class_id}/deactivate | Implemented | missing_endpoints.py | Yes | Deactivate class |
| DELETE | /api/classes/{class_id} | Implemented | missing_endpoints.py | Yes | Delete class |
| POST | /api/enrollments/{enrollment_id}/assign-class | Implemented | missing_endpoints.py | Yes | Assign class to enrollment |
| GET | /api/enrollments | Implemented | missing_endpoints.py | Yes | List enrollments |
| GET | /api/manager/dashboard | Implemented | missing_endpoints.py | Yes | Manager dashboard data |
| GET | /api/manager/alerts | Implemented | missing_endpoints.py | Yes | Manager alerts |
| GET | /api/admin/dashboard | Implemented | missing_endpoints.py | Yes | Admin dashboard data |
| GET | /api/manager/reports/submitted | Implemented | missing_endpoints.py | Yes | Manager submitted reports |
| GET | /api/manager/supervisors/stats | Implemented | missing_endpoints.py | Yes | Manager supervisors stats |
| GET | /api/manager/classes | Implemented | missing_endpoints.py | Yes | Manager classes |
| GET | /api/manager/accounts | Implemented | missing_endpoints.py | Yes | Manager accounts |
| POST | /api/manager/reports/{report_id}/approve | Implemented | missing_endpoints.py | Yes | Approve report |
| POST | /api/manager/reports/{report_id}/reject | Implemented | missing_endpoints.py | Yes | Reject report |
| DELETE | /api/manager/classes/{class_id} | Implemented | missing_endpoints.py | Yes | Delete manager class |
| GET | /api/parent/dashboard | Implemented | missing_endpoints.py | Yes | Parent dashboard data |
| POST | /api/tasks | Implemented | missing_endpoints.py | Yes | Create task |
| GET | /api/tasks | Implemented | missing_endpoints.py | Yes | List tasks |
| GET | /api/tasks/{task_id} | Implemented | missing_endpoints.py | Yes | Get task by ID |
| PUT | /api/tasks/{task_id} | Implemented | missing_endpoints.py | Yes | Update task |
| POST | /api/tasks/{task_id}/toggle | Implemented | missing_endpoints.py | Yes | Toggle task completion |
| DELETE | /api/tasks/{task_id} | Implemented | missing_endpoints.py | Yes | Delete task |
| POST | /api/register/parent | Implemented | missing_endpoints.py | Yes | Register parent |
| POST | /api/enrollment/apply | Implemented | missing_endpoints.py | Yes | Apply for enrollment |
| POST | /api/enrollment/{enrollment_id}/submit | Implemented | missing_endpoints.py | Yes | Submit enrollment |
| POST | /api/enrollment/{enrollment_id}/review | Implemented | missing_endpoints.py | Yes | Review enrollment |
| GET | /api/attendance | Implemented | missing_endpoints.py | Yes | Attendance summary (supports optional date); tests in tests/test_attendance_summary.py |
| GET | /api/attendance/today | Implemented | missing_endpoints.py | Yes | Attendance summary for today; tests in tests/test_attendance_summary.py |
| GET | /api/attendance/{attendance_date} | Implemented | missing_endpoints.py | Yes | Attendance summary for specific date; tests in tests/test_attendance_summary.py |
| POST | /api/attendance/check-in | Implemented | missing_endpoints.py | Yes | Check-in attendance |
| POST | /api/attendance/check-out | Implemented | missing_endpoints.py | Yes | Check-out attendance |
| GET | /api/attendance/report | Implemented | missing_endpoints.py | Yes | Attendance report |
| POST | /api/daily-reports/create | Implemented | missing_endpoints.py | Yes | Create daily report |
| GET | /api/daily-reports/missing | Implemented | missing_endpoints.py | Yes | Missing daily reports |
| GET | /api/daily-reports/alerts | Implemented | missing_endpoints.py | Yes | Daily report alerts |
| GET | /api/daily-reports/supervisor/my-children | Implemented | missing_endpoints.py | Yes | Supervisor children reports |
| GET | /api/daily-reports/parent/my-children | Implemented | missing_endpoints.py | Yes | Parent children reports |
| GET | /api/daily-reports/submitted | Implemented | missing_endpoints.py | Yes | Submitted daily reports |
| POST | /api/daily-reports/{report_id}/submit | Implemented | missing_endpoints.py | Yes | Submit daily report |
| POST | /api/daily-reports/{report_id}/approve | Implemented | missing_endpoints.py | Yes | Approve daily report |
| GET | /api/daily-reports/{report_id} | Implemented | missing_endpoints.py | Yes | Get daily report by ID |
| PUT | /api/daily-reports/{report_id}/supervisor | Implemented | missing_endpoints.py | Yes | Update report (supervisor) |
| PUT | /api/daily-reports/{report_id}/manager | Implemented | missing_endpoints.py | Yes | Update report (manager) |
| POST | /api/daily-reports/{report_id}/approve-and-send | Implemented | missing_endpoints.py | Yes | Approve and send report |
| POST | /api/daily-reports/{report_id}/reject | Implemented | missing_endpoints.py | Yes | Reject daily report |
| POST | /api/daily-reports/manager/create-and-send | Implemented | missing_endpoints.py | Yes | Manager create and send |
| GET | /api/daily-reports/child/{child_id} | Implemented | missing_endpoints.py | Yes | Child daily reports |
| GET | /api/notifications | Implemented | missing_endpoints.py | Yes | List notifications |
| POST | /api/notifications/{notification_id}/read | Implemented | missing_endpoints.py | Yes | Mark notification read |
| POST | /api/notifications/read-all | Implemented | missing_endpoints.py | Yes | Mark all notifications read |
| PUT | /api/parent-profiles/{parent_id} | Implemented | missing_endpoints.py | Yes | Update parent profile |
| PUT | /api/children/{child_id} | Implemented | missing_endpoints.py | Yes | Update child |
| POST | /api/incidents/create | Implemented | missing_endpoints.py | Yes | Create incident (alternative) |
| POST | /api/supervisor/assign | Implemented | missing_endpoints.py | Yes | Assign supervisor |
| POST | /api/supervisor/assign-replacement | Implemented | missing_endpoints.py | Yes | Assign replacement supervisor |
| POST | /api/observations | Implemented | missing_endpoints.py | Yes | Create observation |
| GET | /api/children/{child_id}/observations | Implemented | missing_endpoints.py | Yes | Child observations |
| POST | /api/supervisor/observations/record | Implemented | missing_endpoints.py | Yes | Record supervisor observation |
| GET | /api/supervisor/children | Implemented | missing_endpoints.py | Yes | Supervisor children |
| GET | /api/children | Implemented | missing_endpoints.py | Yes | List children |
| GET | /api/supervisor/my-classes | Implemented | missing_endpoints.py | Yes | Supervisor classes |
| GET | /api/supervisor/dashboard | Implemented | missing_endpoints.py | Yes | Supervisor dashboard |
| GET | /api/portfolios | Implemented | missing_endpoints.py | Yes | List portfolios |
| GET | /api/children/{child_id}/portfolio | Implemented | missing_endpoints.py | Yes | Child portfolio |
| POST | /api/portfolios | Implemented | missing_endpoints.py | Yes | Create portfolio |
| POST | /api/portfolios/{portfolio_id}/publish | Implemented | missing_endpoints.py | Yes | Publish portfolio |
| DELETE | /api/health-alerts/{alert_id} | Implemented | missing_endpoints.py | Yes | Delete health alert |
| GET | /api/supervisor/present-children | Implemented | missing_endpoints.py | Yes | Present children |
| GET | /api/supervisor/daily-reports | Implemented | missing_endpoints.py | Yes | Supervisor daily reports |
| POST | /api/supervisor/daily-reports | Implemented | missing_endpoints.py | Yes | Create supervisor daily report |
| PUT | /api/supervisor/daily-reports/{report_id} | Implemented | missing_endpoints.py | Yes | Update supervisor daily report |
| POST | /api/supervisor/daily-reports/submit | Implemented | missing_endpoints.py | Yes | Submit supervisor daily report |
| GET | /api/manager/daily-reports | Implemented | missing_endpoints.py | Yes | Manager daily reports |
| PUT | /api/manager/daily-reports/{report_id}/review | Implemented | missing_endpoints.py | Yes | Review manager daily report |
| POST | /api/manager/daily-reports/{report_id}/send-to-parent | Implemented | missing_endpoints.py | Yes | Send report to parent |
| POST | /api/manager/daily-reports/create-missing | Implemented | missing_endpoints.py | Yes | Create missing reports |
| GET | /api/supervisor/attendance/children | Implemented | missing_endpoints.py | Yes | Supervisor attendance children |
| POST | /api/supervisor/attendance/record | Implemented | missing_endpoints.py | Yes | Record supervisor attendance |


### Communication Endpoints (communication_service.py)

| Method | Path                                       | Status         | Owner Module             | Tests Added | Notes                   |
| ------ | ------------------------------------------ | -------------- | ------------------------ | ----------- | ----------------------- |
| POST | /comm/messages | Implemented | communication_service.py | No | Send message |
| GET | /comm/audience/options | Implemented | communication_service.py | No | Audience options |
| POST | /comm/audience/preview | Implemented | communication_service.py | No | Preview audience |
| GET | /comm/messages | Implemented | communication_service.py | No | List messages |
| GET | /comm/messages/unread/count | Implemented | communication_service.py | No | Unread message count |
| GET | /comm/messages/{message_id} | Implemented | communication_service.py | No | Get message by ID |
| POST | /comm/messages/{message_id}/read | Implemented | communication_service.py | No | Mark message read |
| DELETE | /comm/messages/{message_id} | Implemented | communication_service.py | No | Delete message |
| POST | /comm/messages/{message_id}/archive | Implemented | communication_service.py | No | Archive message |
| POST | /comm/messages/{message_id}/unarchive | Implemented | communication_service.py | No | Unarchive message |
| POST | /comm/messages/bulk | Implemented | communication_service.py | No | Bulk message actions |
| POST | /comm/messages/{message_id}/replies | Implemented | communication_service.py | No | Reply to message |
| GET | /comm/messages/{message_id}/replies | Implemented | communication_service.py | No | Get message replies |
| POST | /comm/messages/{message_id}/attachments | Implemented | communication_service.py | No | Add message attachment |
| GET | /comm/messages/{message_id}/attachments | Implemented | communication_service.py | No | Get message attachments |
| GET | /comm/messages/attachments/{attachment_id} | Implemented | communication_service.py | No | Download attachment |
| GET | /comm/messages/available-recipients | Implemented | communication_service.py | No | Available recipients |
| POST | /comm/notifications/devices | Implemented | communication_service.py | No | Register device token |
| DELETE | /comm/notifications/devices/{token} | Implemented | communication_service.py | No | Unregister device token |
| POST | /comm/events | Implemented | communication_service.py | No | Create event |
| GET | /comm/events | Implemented | communication_service.py | No | List events |
| POST | /comm/surveys | Implemented | communication_service.py | No | Create survey |
| GET | /comm/surveys | Implemented | communication_service.py | No | List surveys |
| POST | /comm/surveys/{survey_id}/submit | Implemented | communication_service.py | No | Submit survey response |


### Admin Endpoints (admin_endpoints.py)

| Method | Path                                            | Status         | Owner Module       | Tests Added | Notes                        |
| ------ | ----------------------------------------------- | -------------- | ------------------ | ----------- | ---------------------------- |
| GET | /api/admin/users | Implemented | admin_endpoints.py | No | Admin list users |
| POST | /api/admin/users | Implemented | admin_endpoints.py | No | Admin create user |
| GET | /api/admin/users/{user_id} | Implemented | admin_endpoints.py | No | Admin get user |
| PUT | /api/admin/users/{user_id} | Implemented | admin_endpoints.py | No | Admin update user |
| DELETE | /api/admin/users/{user_id} | Implemented | admin_endpoints.py | No | Admin delete user |
| POST | /api/admin/users/{user_id}/admin-reset-password | Implemented | admin_endpoints.py | No | Admin reset password |
| POST | /api/admin/password-reset-request | Implemented | admin_endpoints.py | No | Admin password reset request |
| POST | /api/admin/password-reset-confirm | Implemented | admin_endpoints.py | No | Admin password reset confirm |
| POST | /api/admin/users/bulk-status-update | Implemented | admin_endpoints.py | No | Admin bulk status update |
| POST | /api/admin/users/bulk-delete | Implemented | admin_endpoints.py | No | Admin bulk delete |
| POST | /api/admin/users/bulk-create | Implemented | admin_endpoints.py | No | Admin bulk create |
| POST | /api/admin/users/import-csv | Implemented | admin_endpoints.py | No | Admin import CSV |
| GET | /api/admin/users/import-csv/error-report | Implemented | admin_endpoints.py | No | Admin import error report |
| GET | /api/admin/users/export | Implemented | admin_endpoints.py | No | Admin export users |
| GET | /api/admin/message-recipients | Implemented | admin_endpoints.py | No | Admin message recipients |
| POST | /api/admin/messages | Implemented | admin_endpoints.py | No | Admin send message |
| GET | /api/admin/options/governorates | Implemented | admin_endpoints.py | No | Admin governorate options |
| GET | /api/admin/message-recipients/preview | Implemented | admin_endpoints.py | No | Admin recipient preview |
| POST | /api/admin/messages/preview | Implemented | admin_endpoints.py | No | Admin message preview |
| GET | /api/admin/options/kindergartens | Implemented | admin_endpoints.py | No | Admin kindergarten options |
| GET | /api/performance/metrics | Implemented | admin_endpoints.py | No | Performance metrics |
| GET | /api/performance/requests | Implemented | admin_endpoints.py | No | Request metrics |
| GET | /api/performance/database | Implemented | admin_endpoints.py | No | Database metrics |
| GET | /api/performance/system | Implemented | admin_endpoints.py | No | System metrics |
| POST | /api/backup/create | Implemented | admin_endpoints.py | No | Create backup |
| GET | /api/backup/list | Implemented | admin_endpoints.py | No | List backups |
| POST | /api/backup/restore/{backup_name} | Implemented | admin_endpoints.py | No | Restore backup |
| DELETE | /api/backup/{backup_name} | Implemented | admin_endpoints.py | No | Delete backup |
| GET | /api/backup/info/{backup_name} | Implemented | admin_endpoints.py | No | Backup info |
| POST | /api/backup/cleanup | Implemented | admin_endpoints.py | No | Cleanup backups |
| POST | /api/backup/validate/{backup_name} | Implemented | admin_endpoints.py | No | Validate backup |


### KPI Endpoints (kpi_service.py)

| Method | Path                               | Status         | Owner Module   | Tests Added | Notes                      |
| ------ | ---------------------------------- | -------------- | -------------- | ----------- | -------------------------- |
| POST | /api/kpi/populate-ratio-compliance | Implemented | kpi_service.py | No | Populate ratio compliance |
| GET | /api/kpi/student-distribution | Implemented | kpi_service.py | No | Student distribution |
| GET | /api/kpi/summary | Implemented | kpi_service.py | No | Route in kpi_service.py; role: manager/admin |
| GET | /api/kpi/attendance-rate | Implemented | kpi_service.py | No | Attendance rate KPI |
| GET | /api/kpi/governance-score | Implemented | kpi_service.py | No | Governance score KPI |
| POST | /api/kpi/monthly-snapshots | Implemented | kpi_service.py | No | Monthly snapshots |
| GET | /api/kpi/dashboard-data | Implemented | kpi_service.py | No | KPI dashboard data |
| GET | /api/kpi/filters | Implemented | kpi_service.py | No | KPI filters |
| GET | /api/kpi/manager/dashboard | Implemented | kpi_service.py | No | Manager KPI dashboard |
| GET | /api/manager/dashboard/enhanced | Implemented | kpi_service.py | No | Enhanced manager dashboard |


### Safety Endpoints (safety_service.py)

| Method | Path                                   | Status         | Owner Module      | Tests Added | Notes                    |
| ------ | -------------------------------------- | -------------- | ----------------- | ----------- | ------------------------ |
| POST | /api/incidents | Implemented | safety_service.py | No | Create incident |
| GET | /api/incidents | Implemented | safety_service.py | No | List incidents |
| PUT | /api/incidents/{incident_id} | Implemented | safety_service.py | No | Update incident |
| POST | /api/children/{child_id}/health-alerts | Implemented | safety_service.py | No | Create health alert |
| GET | /api/children/{child_id}/health-alerts | Implemented | safety_service.py | No | Get health alerts |
| POST | /api/safeguarding/create | Implemented | safety_service.py | No | Create safeguarding case |


### Analytics Endpoints (analytics_service.py)

| Method | Path                                           | Status         | Owner Module         | Tests Added | Notes                    |
| ------ | ---------------------------------------------- | -------------- | -------------------- | ----------- | ------------------------ |
| GET | /api/analytics/kpi | Implemented | analytics_service.py | No | Route in analytics_service.py; auth required |
| GET | /api/analytics/attendance | Implemented | analytics_service.py | No | Route in analytics_service.py; auth required |
| GET | /api/analytics/dashboard | Implemented | analytics_service.py | No | Route in analytics_service.py; auth required |
| GET | /api/analytics/metadata | Implemented | analytics_service.py | No | Analytics metadata |
| GET | /api/analytics/advanced-cache | Implemented | analytics_service.py | No | Advanced analytics cache |
| POST | /api/analytics/advanced-cache/invalidate | Implemented | analytics_service.py | No | Invalidate cache |
| POST | /api/analytics/advanced-cache/warm | Implemented | analytics_service.py | No | Warm cache |
| GET | /api/analytics/network-summary | Implemented | analytics_service.py | No | Network summary |
| GET | /api/analytics/governorate-breakdown | Implemented | analytics_service.py | No | Governorate breakdown |
| GET | /api/analytics/dashboard-data | Implemented | analytics_service.py | No | Dashboard data |
| GET | /api/analytics/trends | Implemented | analytics_service.py | No | Trends data |
| GET | /api/analytics/risk-radar | Implemented | analytics_service.py | No | Risk radar |
| POST | /api/analytics/export/sync | Implemented | analytics_service.py | No | Sync export |
| GET | /api/analytics/overview | Implemented | analytics_service.py | No | Analytics overview |
| GET | /api/analytics/drilldown/{dimension_type}/{dimension_id} | Implemented | analytics_service.py | No | Drilldown analytics |
| GET | /api/analytics/time-series | Implemented | analytics_service.py | No | Time series data |
| GET | /api/analytics/compare | Implemented | analytics_service.py | No | Compare analytics |
| GET | /api/analytics/rankings/{metric} | Implemented | analytics_service.py | No | Rankings |
| GET | /api/analytics/governance-distribution | Implemented | analytics_service.py | No | Governance distribution |
| GET | /api/analytics/enrollments/summary | Implemented | analytics_service.py | No | Enrollments summary |
| GET | /api/analytics/attendance/summary | Implemented | analytics_service.py | No | Attendance summary |
| GET | /api/analytics/daily-reports/summary | Implemented | analytics_service.py | No | Daily reports summary |
| GET | /api/analytics/safety/summary | Implemented | analytics_service.py | No | Safety summary |
| GET | /api/analytics/staffing/summary | Implemented | analytics_service.py | No | Staffing summary |
| POST | /api/analytics/export | Implemented | analytics_service.py | No | Export analytics |
| GET | /api/analytics/export/{job_id} | Implemented | analytics_service.py | No | Get export job |
| GET | /api/analytics/export/{job_id}/file | Implemented | analytics_service.py | No | Download export file |


### Audit Endpoints (audit_service.py)

| Method | Path                   | Status         | Owner Module     | Tests Added | Notes             |
| ------ | ---------------------- | -------------- | ---------------- | ----------- | ----------------- |
| GET | /api/audit-logs | Implemented | audit_service.py | No | List audit logs |
| GET | /api/audit-logs/export | Implemented | audit_service.py | No | Export audit logs |


### Monitoring Endpoints (monitoring_endpoints.py)

| Method | Path               | Status         | Owner Module            | Tests Added | Notes             |
| ------ | ------------------ | -------------- | ----------------------- | ----------- | ----------------- |
| GET | /monitoring/health | Implemented | monitoring_endpoints.py | No | Health check |
| GET | /monitoring/metrics | Implemented | monitoring_endpoints.py | No | System metrics |
| GET | /monitoring/metrics/detailed | Implemented | monitoring_endpoints.py | No | Detailed metrics |
| POST | /monitoring/health/run-checks | Implemented | monitoring_endpoints.py | No | Run health checks |
| GET | /monitoring/system/info | Implemented | monitoring_endpoints.py | No | System info |
| GET | /monitoring/logs/recent | Implemented | monitoring_endpoints.py | No | Recent logs |


### Analytics WebSocket (analytics_ws.py)

| Method | Path                        | Status         | Owner Module    | Tests Added | Notes                         |
| ------ | --------------------------- | -------------- | --------------- | ----------- | ----------------------------- |
| WS | /ws/analytics/dashboard | Implemented | analytics_ws.py | No | Analytics dashboard WebSocket |


### Frontend HTML Routes (frontend.py)

| Method | Path                                                       | Status         | Owner Module | Tests Added | Notes                   |
| ------ | ---------------------------------------------------------- | -------------- | ------------ | ----------- | ----------------------- |
| GET | / | Implemented | frontend.py | Yes | Home page |
| GET | /login | Implemented | frontend.py | Yes | Login page |
| GET | /register | Implemented | frontend.py | Yes | Registration page |
| GET | /favicon.ico | Implemented | frontend.py | Yes | Favicon |
| GET | /change-password | Implemented | frontend.py | Yes | Change password page |
| GET | /dashboard | Implemented | frontend.py | Yes | Main dashboard |
| GET | /supervisor/dashboard | Implemented | frontend.py | Yes | Supervisor dashboard |
| GET | /parent/dashboard | Implemented | frontend.py | Yes | Parent dashboard |
| GET | /kindergartens | Implemented | frontend.py | Yes | List kindergartens |
| GET | /kindergartens/create | Implemented | frontend.py | Yes | Create kindergarten |
| GET | /kindergartens/{kg_id} | Implemented | frontend.py | Yes | View kindergarten |
| GET | /kindergartens/{kg_id}/edit | Implemented | frontend.py | Yes | Edit kindergarten |
| GET | /enrollments | Implemented | frontend.py | Yes | List enrollments |
| GET | /enrollments/create | Implemented | frontend.py | Yes | Create enrollment |
| GET | /enrollments/{app_id} | Implemented | frontend.py | Yes | View enrollment |
| GET | /attendance/history | Implemented | frontend.py | Yes | Attendance history |
| GET | /reports | Implemented | frontend.py | Yes | List reports |
| GET | /reports/create | Implemented | frontend.py | Yes | Create report |
| GET | /reports/{report_id} | Implemented | frontend.py | Yes | View report |
| GET | /kpi/dashboard | Implemented | frontend.py | Yes | KPI dashboard |
| GET | /communication | Implemented | frontend.py | Yes | Communication page |
| GET | /communication/messages | Implemented | frontend.py | Yes | Messages page |
| GET | /communication/events | Implemented | frontend.py | Yes | Events page |
| GET | /communication/surveys | Implemented | frontend.py | Yes | Surveys page |
| GET | /tasks | Implemented | frontend.py | Yes | Tasks page |
| GET | /safety | Implemented | frontend.py | Yes | Safety page |
| GET | /safety/incidents/new | Implemented | frontend.py | Yes | New incident page |
| GET | /attendance | Implemented | frontend.py | Yes | Attendance page |
| GET | /attendance/daily | Implemented | frontend.py | Yes | Daily attendance |
| GET | /attendance/check-in | Implemented | frontend.py | Yes | Check-in page |
| GET | /daily-reports | Implemented | frontend.py | Yes | Daily reports page |
| GET | /daily-reports/create | Implemented | frontend.py | Yes | Create daily report |
| GET | /enrollments/new | Implemented | frontend.py | Yes | New enrollment page |
| GET | /incidents/create | Implemented | frontend.py | Yes | Create incident page |
| GET | /messages | Implemented | frontend.py | Yes | Messages page |
| GET | /messages/new | Implemented | frontend.py | Yes | New message page |
| GET | /profile | Implemented | frontend.py | Yes | User profile page |
| GET | /settings | Implemented | frontend.py | Yes | Settings page |
| GET | /notifications | Implemented | frontend.py | Yes | Notifications page |
| GET | /kpi | Implemented | frontend.py | Yes | KPI page |
| GET | /classes/{class_id} | Implemented | frontend.py | Yes | View class |
| GET | /children/{child_id} | Implemented | frontend.py | Yes | View child |
| GET | /enroll | Implemented | frontend.py | Yes | Enrollment page |
| GET | /my-reports | Implemented | frontend.py | Yes | My reports page |
| GET | /contact | Implemented | frontend.py | Yes | Contact page |
| GET | /audit-logs | Implemented | frontend.py | Yes | Audit logs page |
| GET | /admin/users | Implemented | frontend.py | Yes | Admin users page |
| GET | /admin/users/create | Implemented | frontend.py | Yes | Admin create user |
| GET | /admin/users/{user_id}/edit | Implemented | frontend.py | Yes | Admin edit user |
| GET | /admin/messages/compose | Implemented | frontend.py | Yes | Admin compose message |
| GET | /admin/analytics | Implemented | frontend.py | Yes | Admin analytics |
| GET | /admin/analytics/reports | Implemented | frontend.py | Yes | Admin analytics reports |
| GET | /admin/messages | Implemented | frontend.py | Yes | Admin messages |
| GET | /admin/analytics/drilldown/{dimension_type}/{dimension_id} | Implemented | frontend.py | Yes | Admin drilldown |
| GET | /help | Implemented | frontend.py | Yes | Help page |
| GET | /privacy | Implemented | frontend.py | Yes | Privacy page |
| GET | /terms | Implemented | frontend.py | Yes | Terms page |


### Direct App Routes (main.py)

| Method | Path                                | Status         | Owner Module | Tests Added | Notes                 |
| ------ | ----------------------------------- | -------------- | ------------ | ----------- | --------------------- |
| POST | /token | Implemented | main.py | No | OAuth2 token endpoint |
| POST | /api/auth/login | Implemented | main.py | No | Login endpoint |
| POST | /api/auth/logout | Implemented | main.py | No | Logout endpoint |
| POST | /api/auth/refresh | Implemented | main.py | No | Refresh token |
| POST | /api/auth/register | Implemented | main.py | No | User registration |
| GET | /health | Implemented | main.py | No | Basic health check |
| GET | /api/health | Implemented | main.py | No | API health check |
| GET | /api/metrics | Implemented | main.py | No | API metrics |
| GET | /api/scaling/history | Implemented | main.py | No | Scaling history |
| GET | /api/analytics/predict/attendance | Implemented | main.py | No | Predict attendance |
| GET | /api/analytics/predict/incidents | Implemented | main.py | No | Predict incidents |
| GET | /api/analytics/predict/capacity | Implemented | main.py | No | Predict capacity |
| GET | /api/analytics/trends/{metric_type} | Implemented | main.py | No | Analytics trends |
| GET | /api/analytics/insights | Implemented | main.py | No | Analytics insights |

## Duplicate Endpoint Definitions (Resolve Ownership)

None detected after cleanup. If future duplicates appear, list them here.

## Implementation Priority Analysis

### High Priority (Reported 404 in Tests - Verify in Code)

| Method | Path | Status | Owner Module | Priority | Notes |
| ------ | ---- | ------ | ------------ | -------- | ----- |
| GET | /api/kpi/summary | Implemented | kpi_service.py | HIGH | Route exists |
| GET | /api/analytics/kpi | Implemented | analytics_service.py | HIGH | Route exists; duplicates removed |
| GET | /api/attendance | Implemented | missing_endpoints.py | HIGH | Attendance summary added; tests in tests/test_attendance_summary.py |
| GET | /api/analytics/attendance | Implemented | analytics_service.py | HIGH | Route exists; duplicates removed |
| GET | /api/analytics/dashboard | Implemented | analytics_service.py | HIGH | Route exists; duplicates removed |

### Medium Priority (Partial implementation or missing features)

1. User export functionality - CSV generation issues
2. Bulk operations - May have validation issues
3. Analytics endpoints - Verify router inclusion and remove duplicates
4. KPI endpoints - Some moved but not fully implemented

### Low Priority (Working but need optimization)

1. Error handling standardization
2. Response format consistency
3. Pagination improvements

## Status Snapshot

### Coverage Confirmed: 38% for missing_endpoints.py

- **Total Lines**: 2,923
- **Covered Lines**: 1,114
- **Missing Lines**: 1,809
- **Coverage**: 38%

### Recent Fixes

- DONE: Validation messages converted to English
- DONE: Phone validation tests passing

### Test Status

- LAST RECORDED: 9/9 tests passing in test_api.py (core API tests)
- TODO: Run P0 tests (pytest -m "p0") for attendance summary (tests/test_attendance_summary.py)
- NOTE: P0/P1 runs require SECRET_KEY and DATABASE_URL (use sqlite:///:memory: for CI/local if not set in .env).

## Next Steps

1. Implement or verify the high-priority endpoints above and update this inventory.
2. Add integration tests for each implemented endpoint.
3. Re-run coverage and update the Executive Summary metrics.
4. Phase 2: Move to messaging permissions enforcement.
5. Phase 3: Frontend gap analysis.
6. Phase 4: Notification service completion.
