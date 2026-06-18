# Admin Module Tree Structure - Implementation TODO

## Task

Organize admin web pages to show as a tree structure with root and sub-root categories

## Current State

Admin navigation in templates/admin_base.html shows flat list:

- Dashboard
- Users
- Communication
- Contact Messages
- Analytics & Reports
- Jordan Heat Map
- Governance & Compliance
- Data Management
- Security & Audit

## Implementation Plan

### Step 1: Design Tree Structure

Organize into hierarchical categories:

**Root: Dashboard**

- Sub: Overview, System Health

**Root: User Management**

- Sub: User List, Create User, Import Users

**Root: Communication**

- Sub: Messages, Compose, Contact Messages

**Root: Analytics & Reports**

- Sub: Dashboard, Reports, Daily Reports, Drilldown, Incident Reports

**Root: Jordan Heat Map**

- Sub: Overview, Governorates

**Root: Governance & Compliance**

- Sub: Reports, Leaderboard, Reminders

**Root: Data Management**

- Sub: Import Kindergartens, Imported Kindergartens, Import Logs

**Root: Security & Audit**

- Sub: Audit Logs, Alerts, Impersonation

### Step 2: Update admin_base.html

- Add collapsible tree navigation
- Add proper hierarchy classes for styling

### Step 3: Test

- Verify navigation works correctly
- Check responsive design

## Status: DONE

### Completed

- `templates/admin_base.html` — full 8-section collapsible tree with Font Awesome icons, chevron
  animation, active-link highlighting, and `localStorage` persistence
- `frontend.py` — 3 new routes added: `/admin/users/import`, `/admin/import-logs`,
  `/admin/governance/reminders`
- `templates/admin/import_users.html` — CSV upload with template download and inline error table
- `templates/admin/import_logs.html` — filterable import history table with detail modal
- `templates/admin/governance_reminders.html` — stat cards, reminder log, send-now modal
