# Professional Implementation Plan: KPI Dashboard Remediation

This document outlines the complete technical strategy to fix critical and major issues in the KPI Dashboard. The plan covers root cause analysis, architecture-aligned fixes, updated API contracts, and a comprehensive testing and QA process.

---

### 1. Root Cause Summary

| Defect ID | Issue | Root Cause Analysis |
| :--- | :--- | :--- |
| **CRITICAL #1/#2** | **Dashboard data does not auto-load.** | The frontend component (`KpiDashboard.vue` or similar) lacks a data-fetching call within its initial lifecycle hook (`onMounted` or `useEffect`). The data fetch logic is incorrectly bound only to a manual user action (clicking the "تحديث" button). |
| **MAJOR #3** | **Duplicate Kindergartens in dropdown.** | The backend API endpoint responsible for populating filters (`/api/kpi/filters`) executes a database query that does not enforce uniqueness (e.g., missing `SELECT DISTINCT` or `GROUP BY` on the kindergarten ID). This is likely compounded by a lack of a `UNIQUE` constraint in the `kindergartens` database table. |
| **MAJOR #4** | **Inconsistent Governorate localization.** | The database schema stores location names (e.g., in the `governorates` table) in a single language. The backend API serves this data as-is, and the frontend renders it directly, leading to a mix of languages when the UI locale and the data's language differ. |
| **MAJOR #5** | **Incorrect "Bottom 5 Performers" list.** | The backend query for this metric is flawed. It likely applies its `LIMIT 5` clause before ensuring the uniqueness of the institutions, and/or it uses an incorrect sorting direction (`DESC` instead of `ASC` for bottom performers). |
| **MAJOR #6** | **Poor filter UX feedback.** | The frontend component's state management is incomplete. It fails to track the `isLoading` status of API calls, preventing the UI from providing necessary user feedback (e.g., disabling buttons, showing spinners, or updating status messages). |

---

### 2. Architecture-Aligned Fix Strategy

#### **Frontend (Vue.js / React)**

1.  **State Management:**
    *   Introduce `isLoading: boolean` and `appliedFilters: object` to the component's state (e.g., using `ref` in Vue 3, `useState` in React, or a dedicated store like Pinia/Zustand).
    *   `isLoading` will control the visibility of skeleton loaders and the disabled state of form controls.
    *   `appliedFilters` will be the single source of truth for the "Applied Filters" banner.

2.  **Lifecycle Hooks for Auto-Load:**
    *   A central data-fetching function, `async function fetchDashboardData(filters)`, will be implemented.
    *   This function will be invoked within the `onMounted` (Vue) or `useEffect(..., [])` (React) lifecycle hook, using a set of default filters (e.g., current month).

3.  **UX Enhancement:**
    *   The "Apply Filters" button will be disabled when `isLoading` is `true`.
    *   A spinner icon will be displayed next to the button text (e.g., "جارٍ التطبيق…") during the loading state.
    *   The "Applied Filters" banner will be updated *only* after a successful API response, using the `appliedFilters` state.

#### **Backend (Python / FastAPI)**

1.  **Query Correctness:**
    *   **Kindergarten Filter:** The repository method fetching kindergartens will be modified to use `SELECT DISTINCT id, name_ar, name_en FROM kindergartens...`.
    *   **Bottom 5 Performers:** The query logic will be re-written to guarantee uniqueness and correct ordering. A common robust pattern is using window functions or a subquery:
        ```sql
        SELECT id, name, score
        FROM (
            SELECT DISTINCT ON (k.id) k.id, COALESCE(k.name_ar, k.name_en) as name, m.score
            FROM kindergartens k
            JOIN kpi_metrics m ON k.id = m.kindergarten_id
            WHERE -- ... filter conditions
            ORDER BY k.id, m.created_at DESC -- Get latest score for each KG
        ) AS latest_scores
        ORDER BY score ASC
        LIMIT 5;
        ```

2.  **DTOs / Response Models (Pydantic):**
    *   API responses will be standardized using Pydantic models to align with the `APIResponse` class pattern, ensuring consistent and predictable data contracts.

3.  **Internationalization (i18n):**
    *   The strategy will be **database-driven**. All relevant API endpoints will accept a `locale: str = 'ar'` query parameter.
    *   The backend services will use this parameter to dynamically select the correct column (e.g., `name_ar` vs. `name_en`).

#### **Database (PostgreSQL / MySQL)**

1.  **Schema Modification (Migration Required):**
    *   The `kindergartens` and `governorates` tables will be altered to include `name_ar: VARCHAR` and `name_en: VARCHAR` columns.
    *   A data migration script will be required to populate the new columns based on existing data.

2.  **Data Integrity (Migration Required):**
    *   A cleanup script will be executed to remove duplicate kindergartens.
        ```sql
        -- Example for PostgreSQL
        DELETE FROM kindergartens k1
        USING kindergartens k2
        WHERE k1.id > k2.id AND k1.name_en = k2.name_en AND k1.governorate_id = k2.governorate_id;
        ```
    *   Following cleanup, a `UNIQUE` constraint will be applied to the table to prevent future duplicates, e.g., `ALTER TABLE kindergartens ADD CONSTRAINT uq_kg_name_gov UNIQUE (name_en, governorate_id);`.

---

### 3. API Contract

#### **Endpoint 1: Get Dashboard KPIs**
`GET /api/kpi/dashboard-data`

*   **Query Parameters:**
    *   `start_date: string` (YYYY-MM-DD)
    *   `end_date: string` (YYYY-MM-DD)
    *   `kg_ids[]: integer` (Optional)
    *   `gov_ids[]: integer` (Optional)
    *   `locale: string` ('ar' or 'en', defaults to 'ar')

*   **Success Response (200 OK):**
    ```json
    {
      "code": 0,
      "message": "Success",
      "data": {
        "summary": { "total_kpis": 1500, "average_score": 85.5 },
        "top_5_performers": [ { "id": 12, "name": "روضة الأمل", "score": 99.8 } ],
        "bottom_5_performers": [ { "id": 34, "name": "روضة المستقبل", "score": 45.1 } ],
        "performance_over_time": [ { "date": "2026-01-01", "score": 88.0 } ]
      }
    }
    ```

*   **Error Response (400/500):**
    ```json
    {
      "code": 1,
      "message": "Error: Invalid date range provided.",
      "data": null
    }
    ```

#### **Endpoint 2: Get Filter Data**
`GET /api/kpi/filters`

*   **Query Parameters:**
    *   `locale: string` ('ar' or 'en', defaults to 'ar')

*   **Success Response (200 OK):**
    ```json
    {
      "code": 0,
      "message": "Success",
      "data": {
        "kindergartens": [ { "id": 12, "name": "روضة الأمل" } ],
        "governorates": [ { "id": 1, "name": "عمّان" } ]
      }
    }
    ```

---

### 4. Implementation Steps

| Phase | Team | Step | Code Touchpoints | Risk | Validation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1. BE/DB**| DBA | 1. Create DB migration for `name_ar`/`name_en` columns. | `alembic/versions/`, `models.py` | Low | Migration applies successfully on dev DB. |
| | DBA | 2. Create cleanup script for duplicates and apply `UNIQUE` constraint. | `scripts/dedupe_kgs.py` | Medium | Script runs without error; constraint is active. |
| | Backend | 3. Fix "Bottom 5" query in service layer. | `kpi_service.py` | Medium | Unit tests for this specific function pass. |
| | Backend | 4. Fix KG filter query to be `DISTINCT`. | `kpi_service.py` | Low | API response for `/filters` shows no duplicates. |
| | Backend | 5. Implement `locale` handling in all KPI endpoints. | `kpi_service.py`, `main.py` | Low | API response returns correct language strings. |
| **2. FE** | Frontend | 6. Implement state variables (`isLoading`, etc.). | `KpiDashboard.vue` | Low | Component state updates correctly in Vue Devtools. |
| | Frontend | 7. Create `fetchDashboardData` and call on `onMounted`. | `KpiDashboard.vue` | Medium | Network tab shows API call on page load. |
| | Frontend | 8. Wire UI elements (button, skeletons) to `isLoading` state. | `KpiDashboard.vue` | Low | Skeletons/spinners display correctly during load. |
| **3. QA** | QA / Test | 9. Write unit tests for BE query logic. | `tests/test_kpi_service.py` | Low | New tests pass in CI. |
| | QA / Test | 10. Write E2E test for auto-load functionality. | `e2e/tests/dashboard.spec.js` | Medium | E2E test passes, proving data loads without clicks. |
| | QA / Test | 11. Perform full manual regression testing on staging. | N/A | Low | QA sign-off. |

---

### 5. Testing & QA Plan

*   **Unit Tests:**
    *   **Backend:** A new test case `test_get_bottom_5_performers_are_unique_and_sorted_asc` will be added. It will use a mock database seeded with duplicate institutions and verify the output is 5 unique, correctly sorted records.
    *   **Frontend:** The state management logic for `isLoading` will be tested. Trigger a mock API call and assert that `isLoading` is `true` at the start and `false` on completion/failure.

*   **Integration Tests (API Level):**
    *   A test will call `GET /api/kpi/dashboard-data` against a test database and assert that the `bottom_5_performers` array contains exactly 5 unique items.
    *   Another test will call `GET /api/kpi/filters?locale=en` and assert that the `name` fields are in English.

*   **End-to-End (E2E) Tests (Cypress/Playwright):**
    *   A test script will navigate to `/kpi/dashboard`.
    *   It will `cy.intercept()` the `GET /api/kpi/dashboard-data` call and wait for its response.
    *   It will then assert that the KPI charts/tables are visible on the screen **without** having to `cy.click()` the update button.

*   **Test Data Requirements:**
    *   The test DB must contain at least two kindergartens with the same name.
    *   At least 7 distinct institutions must have low KPI scores to properly test the Bottom 5 logic.
    *   All `governorates` and `kindergartens` must have both `name_ar` and `name_en` fields populated.

---

### 6. Definition of Done

- [ ] All backend queries for the KPI dashboard are refactored, optimized, and unit-tested for correctness.
- [ ] Database migrations for schema changes (`i18n` columns) and constraints (`UNIQUE`) are approved and have been successfully applied to all environments.
- [ ] The two primary API endpoints (`/dashboard-data`, `/filters`) are implemented according to the specified contract.
- [ ] The frontend dashboard component automatically fetches and renders data on initial page load.
- [ ] All UI feedback mechanisms (loading states, disabled buttons, spinners, and filter banners) are implemented and function correctly.
- [ ] All kindergarten and governorate names are correctly localized based on the selected UI language.
- [ ] All new unit, integration, and E2E tests are passing in the CI/CD pipeline.
- [ ] The project has been successfully deployed to a staging environment and has passed a full manual QA regression cycle.
- [ ] Product owner has provided final sign-off on the delivered functionality.