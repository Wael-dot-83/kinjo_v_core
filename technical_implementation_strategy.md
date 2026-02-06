Technical Implementation Strategy (Phase C):
---

**1. Guiding Principles for Implementation:**
*   **Layered Approach:** Strict separation of concerns (Backend, API, Frontend).
*   **Backward Compatibility:** All new/modified endpoints or data structures must support existing functionalities or be versioned.
*   **Performance First:** Optimize queries, leverage caching, minimize data transfer.
*   **RTL-First Design:** Ensure UI components and layout naturally support Right-to-Left languages.
*   **Reusability:** Maximize reuse of existing components, validators, and utility functions.
*   **Modularity:** New components should be self-contained and easily pluggable.

**2. Backend/Data Layer (Python - `kpi_service.py`, `models.py`, `database.py`)**

*   **New Aggregations/Queries Needed:**
    *   **GCEI Calculation:** The `compute_governance_score` already exists, which computes the final score and band. This will be reused as the core GCEI calculation.
    *   **Training & Development Completion Rate:**
        *   **Requirement:** Need a new model (`TrainingRecord`) and corresponding data to track staff training. This will involve:
            *   `models.py`: Add `TrainingModule` (name, mandatory status) and `StaffTrainingCompletion` (user_id, module_id, completion_date).
            *   `kpi_service.py`: Implement `compute_training_completion_rate(db, kindergarten_id, period_start, period_end)` to query `StaffTrainingCompletion`.
    *   **Report Submission Rate:**
        *   **Requirement:** Need to track total expected daily reports vs. submitted daily reports.
        *   `kpi_service.py`: Implement `compute_report_submission_rate(db, kindergarten_id, period_start, period_end)`. This would involve counting active children per day * days in period for expected, and submitted reports.
    *   **Capacity Utilization Rate:**
        *   `kpi_service.py`: Implement `compute_capacity_utilization_rate(db, kindergarten_id, period_start, period_end)`. This involves total capacity from classes vs. active enrollments.
    *   **New Enrollments (Period):**
        *   `kpi_service.py`: Implement `compute_new_enrollments(db, kindergarten_id, period_start, period_end)`. Query `EnrollmentApplication` filtered by `created_at`.
    *   **Trend Data for all KPIs:** For time-series charts, extend existing `get_network_trends` (from `analytics_service.py`) or create a similar function in `kpi_service.py` to get daily/weekly/monthly KPI values for selected metrics over a period.
    *   **Anomaly/Thresholds:**
        *   **Requirement:** Store KPI targets/baselines.
        *   `models.py`: Potentially add `KPITarget` model (kindergarten_id, kpi_name, target_value, threshold_red, threshold_amber, effective_date).
        *   `kpi_service.py`: Functions to retrieve targets for a given KPI.

*   **API Endpoints:**
    *   **Versioning:** Prefix new endpoints with `/api/v2/kpi/` or use query parameters to indicate a new dashboard version if radical changes. For now, extend existing endpoints.
    *   **Consolidated Dashboard Data Endpoint (New):**
        *   `@router.get("/kpi/dashboard-data", response_model=NewDashboardResponse)`
        *   **Purpose:** Replaces `/api/kpi/summary` and `/api/kpi/student-distribution` for the new dashboard.
        *   **Parameters:** `kindergarten_ids: Optional[List[int]]`, `governorate: Optional[str]`, `period_start: date`, `period_end: date`.
        *   **Logic:** This endpoint will orchestrate calls to various `KPIService` methods, aggregating data for selected filters. For multi-kindergarten selection, it will aggregate across chosen KGs.
    *   **KPI Trend Data Endpoint (Extend Existing):**
        *   Extend `/api/analytics/time-series` or create new `@router.get("/kpi/trends", response_model=List[TimeSeriesPoint])`
        *   **Parameters:** `metric: str`, `kindergarten_ids: Optional[List[int]]`, `granularity: str`, `period_start: date`, `period_end: date`.
        *   **Logic:** Calculates historical values for a specific KPI metric.
    *   **Top/Bottom Performers Endpoint (Reuse):** The existing `/api/analytics/rankings/{metric}` can be reused.

*   **Performance Optimization:**
    *   **Caching:** Implement a caching layer (e.g., Redis) for frequently accessed KPI calculations, especially for historical data or network-wide aggregates. Cache invalidation strategies are crucial (e.g., on data change in `models.py`).
    *   **Materialized Views:** For complex, slow, and frequently accessed aggregates (e.g., network-wide GCEI trends), consider creating database materialized views that are refreshed periodically (e.g., nightly Celery task).
    *   **Query Optimization:** Use `EXPLAIN ANALYZE` for all complex queries. Ensure proper indexing on `date` columns, `kindergarten_id`, `child_id`, `class_id`, `status` in `models.py`.
    *   **Pagination & Limits:** For any drill-down tables or large lists (e.g., anomaly lists), ensure pagination is implemented at the API level.

**3. API Contract (JSON Shapes)**

*   **`NewDashboardResponse` (Pydantic Model - for `/api/v2/kpi/dashboard-data`)**
    ```python
    class TrendDataPoint(BaseModel):
        date: date
        value: float

    class KPICardData(BaseModel):
        value: float
        unit: Optional[str] = None
        trend_indicator: Optional[str] = None # "up", "down", "flat"
        trend_change: Optional[float] = None # percentage change vs prev period
        band: Optional[str] = None # "GREEN", "AMBER", "RED"
        alert: Optional[str] = None # "anomaly", "threshold_breached"
        tooltip: Optional[str] = None

    class StudentDistributionItem(BaseModel):
        label: str
        value: int

    class TopBottomPerformer(BaseModel):
        id: int
        name: str
        value: float
        rank: Optional[int] = None
        governorate: Optional[str] = None

    class AlertsSummary(BaseModel):
        type: str
        message: str
        priority: str
        entity_id: Optional[int] = None

    class NewDashboardResponse(BaseModel):
        period_start: date
        period_end: date
        kindergarten_id: Optional[int] = None # if filtered for single KG
        governorate: Optional[str] = None # if filtered for single Governorate

        overall_gcei: KPICardData
        attendance_rate: KPICardData
        ratio_compliance: KPICardData
        training_completion_rate: KPICardData
        report_submission_rate: KPICardData

        incident_rate: KPICardData
        serious_incident_rate: KPICardData
        incident_followup_sla: KPICardData
        chronic_absence_rate: KPICardData

        capacity_utilization_rate: KPICardData
        active_enrollments: KPICardData
        new_enrollments: KPICardData

        student_distribution: List[StudentDistributionItem]
        top_performers_by_gcei: List[TopBottomPerformer]
        low_performers_by_gcei: List[TopBottomPerformer]
        
        attendance_trend: List[TrendDataPoint] # Default to monthly/weekly for trends section
        incidents_trend: List[TrendDataPoint]
        enrollment_trend: List[TrendDataPoint]
        gcei_trend: List[TrendDataPoint]

        alerts: List[AlertsSummary]
    ```
*   **No Sensitive Fields:** Ensure no raw user passwords, internal system IDs that are not necessary for frontend display, or excessive audit trail details are exposed. Use DTOs (Data Transfer Objects) and explicit `response_model` definitions to control output.

**4. Frontend Integration (HTML/CSS/JS)**

*   **Introduce New Components/Widgets:**
    *   Refactor `templates/kpi/dashboard.html` to implement the new layout.
    *   Create dedicated reusable HTML partials/components for:
        *   `global_filters.html`: Date range, Kindergarten, Governorate selectors.
        *   `kpi_card.html`: Generic card structure for KPI data, including value, unit, trend indicator, color band, and tooltip.
        *   `chart_container.html`: Placeholder for Chart.js instances.
        *   `top_bottom_list.html`: For comparative views.
    *   These components will be included in `dashboard.html` using Jinja2 `{% include %}`.
*   **Reuse Shared Components & Styling:**
    *   Leverage existing `base.html`, `kinjo.css`, `bootstrap.rtl.min.css`.
    *   Utilize existing color semantics (`bg-success`, `bg-warning`, `bg-danger`) for KPI bands.
    *   Re-use `fetchWithAuth`, `showToast` functions.
*   **Manage State for Filters:**
    *   Use a JavaScript state object (`dashboardState = { period_start, period_end, kindergarten_ids, governorate }`) to manage filter selections.
    *   Filter changes will trigger `loadDashboardData()` function, which will call the new consolidated API endpoint with updated parameters.
    *   The `loadDashboardData()` function will parse the `NewDashboardResponse` and update all relevant UI components.
*   **Loading Skeletons:** Extend the existing `showSkeletonLoaders()` and `hideSkeletonLoaders()` logic to cover all new KPI cards and charts, providing a smooth user experience during data fetching.
*   **RTL-Friendly Typography:** Ensure Arabic fonts and text alignment are correctly applied through CSS.

**5. Testing & Quality Gate**

*   **Unit/Integration Tests (Backend - Pytest):**
    *   Tests for each new `KPIService` method (e.g., `compute_training_completion_rate`) to ensure correct calculation logic.
    *   Tests for the new `dashboard-data` endpoint to verify correct data aggregation and filtering.
    *   Tests for `KPITarget` model (CRUD, retrieval).
*   **API Tests (Backend - Pytest/FastAPI TestClient):**
    *   Validate response schemas for `NewDashboardResponse` against defined Pydantic models.
    *   Verify correct authorization (Admin vs. Manager vs. Supervisor roles).
    *   Test edge cases: no data, invalid filter parameters, large date ranges.
*   **UI Tests (Frontend - Selenium/Playwright or Jest/Vue Test Utils if a framework is used):**
    *   Verify correct rendering of all KPI cards, charts, and lists.
    *   Test filter functionality (date range, kindergarten, governorate) and its impact on displayed data.
    *   Test drill-down navigation.
    *   Verify loading skeletons appear and disappear correctly.
    *   Non-regression tests to ensure existing pages (e.g., basic dashboard, analytics) and shared components are not affected.
*   **Performance Tests:** Benchmark `dashboard-data` endpoint with various filter combinations and data volumes.
*   **Accessibility (A11y) & RTL Testing:** Manual and automated checks to ensure the dashboard is usable and visually correct for RTL users.

**6. Migration / Rollout**

*   **Feature Flag:** Implement a feature flag (e.g., in `config.py` or a database setting) to toggle between the old and new KPI dashboards. This allows for a controlled rollout.
*   **Beta View:** Deploy the new dashboard behind a beta URL (e.g., `/kpi/dashboard/new`) or accessible only to specific admin users.
*   **Progressive Enhancement:** Start with core KPI cards and gradually add more intelligent behaviors (trends, anomalies) in subsequent iterations.
*   **Clean Rollback:** Ensure all changes are modular and can be easily reverted if issues arise. New endpoints should not overwrite existing ones unless explicitly replacing.
*   **Database Migrations:** Use `alembic` for any `models.py` changes (e.g., `TrainingModule`, `StaffTrainingCompletion`, `KPITarget`) to manage database schema evolution.
---
