Dashboard Redesign Specification (Phase B):
---

**1. Vision & Guiding Principles:**
The KPI Dashboard should transform from a static display of numbers into an interactive "Performance Cockpit" for administrative users. It will provide actionable insights, clear trends, and contextualize performance against targets, enabling proactive management and strategic decision-making.

**Guiding Principles:**
*   **Intelligent:** Derives insights (trends, anomalies, thresholds).
*   **Attractive:** Clean, hierarchical, visually appealing, RTL-friendly.
*   **Meaningful:** Every KPI answers a key business question (governance, operations, safety, utilization, trends).
*   **Actionable:** Supports drill-down and filtering for targeted interventions.
*   **Scalable:** Designed to support network-wide views for Admin and specific Kindergarten views for Managers/Supervisors.

---

**2. Information Architecture & Dashboard Sections:**

The dashboard will be structured into logical sections, each focusing on a specific aspect of kindergarten operations.

*   **Global Filters (Persistent at Top):**
    *   **Date Range Selector:** Custom range, pre-sets (Today, Last 7 Days, Last 30 Days, Current Month, Last Month, Current Quarter, Last Quarter, Current Year, Last Year).
    *   **Kindergarten Selector:** (Multi-select for Admin, single-select for Manager) - "All Kindergartens" (Admin only), Specific Kindergarten(s).
    *   **Governorate Selector:** (Multi-select for Admin, single-select for Manager) - "All Governorates" (Admin only), Specific Governorate(s). *Note: This filter will dynamically populate based on selected kindergartens if applicable, or vice-versa.*

*   **Section 1: Overall Governance & Child Experience Index (GCEI)**
    *   **Purpose:** High-level summary of overall performance and quality.
    *   **KPIs:**
        *   **Overall Governance & Child Experience Index (GCEI):**
            *   **Visualization:** Large Gauge Chart + Score (0-100) + Color Band (Green/Amber/Red) + Trend Indicator (vs. previous period).
            *   **Definition:** Weighted average of Governance Quality Index (GQI) and Child Experience Index (CEI).
            *   **Formula:** GCEI = (GQI * 0.60) + (CEI * 0.40).
            *   **Time Window:** Configurable by Global Filter.
            *   **Segmentation:** Network-wide, per Kindergarten (via filter).
            *   **Interaction:** Hover for GQI/CEI breakdown. Click for GCEI details/methodology.

*   **Section 2: Operational Excellence & Staffing**
    *   **Purpose:** Monitors efficiency, compliance, and staff-related performance.
    *   **KPIs:**
        *   **Attendance Rate:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator (vs. prev period).
            *   **Units:** %
            *   **Thresholds:** Green (>=90%), Amber (70-89%), Red (<70%).
        *   **Staff-Child Ratio Compliance:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Units:** %
            *   **Thresholds:** Green (>=95%), Amber (80-94%), Red (<80%).
        *   **Training & Development Completion Rate:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Definition:** Percentage of staff completing mandatory training modules.
            *   **Formula:** (Count of completed training modules / Total count of assigned training modules) * 100.
            *   **Units:** %
            *   **Thresholds:** Green (>=90%), Amber (75-89%), Red (<75%).
        *   **Report Submission Rate (Daily Reports):**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Definition:** Percentage of expected daily reports submitted on time.
            *   **Units:** %
            *   **Thresholds:** Green (>=95%), Amber (85-94%), Red (<85%).
        *   **Top 5 / Bottom 5 Kindergartens (by selected metric):**
            *   **Visualization:** Sortable List.
            *   **Interaction:** Configurable metric (e.g., Attendance Rate, Ratio Compliance). Drill-down on Kindergarten name.

*   **Section 3: Safety & Wellbeing**
    *   **Purpose:** Tracks child safety, health, and incident management.
    *   **KPIs:**
        *   **Incident Rate (per 100 child-days):**
            *   **Visualization:** Number Card + Value + Trend Indicator.
            *   **Units:** Incidents per 100 Child-Days.
            *   **Thresholds:** Green (<=0.5), Amber (0.51-1.0), Red (>1.0).
        *   **Serious Incident Rate (High/Critical):**
            *   **Visualization:** Number Card + Value + Trend Indicator + Anomaly Highlight.
            *   **Units:** Incidents per 100 Child-Days.
            *   **Thresholds:** Green (0), Amber (>0 and <=0.1), Red (>0.1).
            *   **Anomaly Highlight:** If current value is >20% higher than average of previous 3 periods.
        *   **Incident Follow-up SLA Compliance:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Definition:** % of required incident follow-ups completed within SLA (e.g., 48 hours).
            *   **Units:** %
            *   **Thresholds:** Green (100%), Amber (90-99%), Red (<90%).
        *   **Chronic Absence Rate:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Units:** % (Children with >10% absence).
            *   **Thresholds:** Green (<=5%), Amber (5.1-10%), Red (>10%).

*   **Section 4: Enrollment & Engagement**
    *   **Purpose:** Monitors student enrollment, capacity utilization, and engagement.
    *   **KPIs:**
        *   **Capacity Utilization Rate:**
            *   **Visualization:** Number Card + Percentage + Trend Indicator.
            *   **Units:** %
            *   **Thresholds:** Green (90-100%), Amber (80-89% or >100%), Red (<80%).
        *   **Active Enrollments:**
            *   **Visualization:** Number Card + Count + Trend Indicator.
        *   **Student Distribution by Level/Class:**
            *   **Visualization:** Doughnut Chart.
            *   **Interaction:** Hover for counts, Drill-down to specific class rosters.
        *   **New Enrollments (Period):**
            *   **Visualization:** Number Card + Count.

*   **Section 5: Trends & Forecasts**
    *   **Purpose:** Provides historical context and future projections.
    *   **KPIs:**
        *   **Attendance Trend (Network/KG):**
            *   **Visualization:** Line Chart (Daily/Weekly/Monthly granularity, selectable).
            *   **Dimensions:** Selectable by Network, Kindergarten (if filtered).
        *   **Incidents Trend (Network/KG):**
            *   **Visualization:** Line Chart (Daily/Weekly/Monthly granularity, selectable).
        *   **Enrollment Trend (Network/KG):**
            *   **Visualization:** Line Chart (Daily/Weekly/Monthly granularity, selectable).
        *   **GCEI Trend (Network/KG):**
            *   **Visualization:** Line Chart (Daily/Weekly/Monthly granularity, selectable).

---

**3. KPI Definitions (Examples):**

*   **Overall Governance & Child Experience Index (GCEI):**
    *   **Definition:** A composite index reflecting the overall quality of kindergarten operations, encompassing both governance (compliance, efficiency) and child-centric aspects (safety, wellbeing, experience).
    *   **Formula:** GCEI = (Governance Quality Index (GQI) * 0.60) + (Child Experience Index (CEI) * 0.40).
    *   **Required Data:** All data required for GQI and CEI sub-components.
    *   **Thresholds:** Green (>=80), Amber (60-79), Red (<60).
    *   **Trend-based:** Yes, time series and comparison to previous period.

*   **Training & Development Completion Rate:**
    *   **Definition:** Measures the percentage of mandatory staff training modules completed by eligible staff within the reporting period.
    *   **Formula:** (Count of completed training modules / Total count of assigned training modules) * 100.
    *   **Required Data:** Staff training records (assigned modules, completion dates).
    *   **Thresholds:** Green (>=90%), Amber (75-89%), Red (<75%).
    *   **Trend-based:** Yes.

---

**4. Layout & UX (RTL-first emphasis):**

*   **Grid System:** Responsive Bootstrap 5 grid.
*   **Above the Fold:** Global Filters, prominent GCEI card, and top operational/safety KPIs will be visible immediately.
*   **Filters:**
    *   Date Range: Prominent input group at the top-right of the page header (similar to existing analytics dashboard).
    *   Kindergarten/Governorate: Dropdowns in the main filter area, potentially as multi-selects for Admin roles. Should be clear and intuitive.
*   **Responsive Behavior:**
    *   Desktop: Multi-column layout as described in sections.
    *   Small Screens: Stacking vertically, prioritizing critical KPIs. Charts might become scrollable horizontally if necessary.
*   **Tooltips & Legends:**
    *   **Tooltips:** Implement for every KPI card, explaining "What this means," "How it's calculated," and "Why it's important."
    *   **Legends:** Clear, concise legends for all charts.
    *   **Empty States:** Graceful handling for periods with no data (e.g., "No data available for this period/filter").
    *   **Loading Skeletons:** Animated skeleton loaders (as implemented in the previous task) for all KPI cards and charts during data fetching.

---

**5. Intelligent Behaviors:**

*   **Anomaly/High-Risk Highlighting:**
    *   Automatically detect and highlight KPIs that show significant deviations from historical averages or expected norms (e.g., a sudden drop in attendance rate, a spike in incident rate). Visual cues (e.g., red border, warning icon).
    *   Risk flags (e.g., "License expiring soon" from the audit report) will be integrated into a dedicated alert area.
*   **Comparative Views:**
    *   For each KPI, display a small trend indicator (up/down/flat arrow) alongside the current value, comparing it to the previous period (e.g., "vs. Last Month").
    *   "Top 5 / Bottom 5" lists for key metrics to highlight best/worst performing kindergartens.
*   **Simple Forecasts/Trend Lines:**
    *   Line charts in the "Trends & Forecasts" section will show historical data and potentially a simple linear regression forecast for the next period.
*   **Drill-down:** Clicking on a KPI card or chart segment will navigate to a more detailed report or a specific entity (e.g., clicking on a kindergarten in a "Top/Bottom" list navigates to its individual KPI page).

---
