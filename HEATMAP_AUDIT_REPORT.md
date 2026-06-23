# Arabic RTL Heatmap Dashboard — Full Production Audit Report

**Dashboard**: Geographic Indicator Heatmaps (خرائط المؤشرات الجغرافية)  
**Module**: Admin heatmap — Jordan governorates risk visualization  
**Date**: 2026-06-21  
**Auditor**: Production-Readiness Task Force  

---

## 1. Executive Summary

The heatmap dashboard has strong architectural foundations (SVG multi-map + Leaflet satellite single-map, indicator-based scoring, 6-category risk model, governorate drill-down). However, it suffers from **four critical trust-breaking defects**, **three medium data-integrity issues**, and **six UI/UX localization problems** that must be resolved before the dashboard is reliable for administrative decision-making.

**Verdict**: `NOT PRODUCTION READY` — requires fixes in risk classification boundary handling, loading-state management, KPI labeling, rounding consistency, and Arabic RTL polish.

---

## 2. Critical Issues

### 2.1 Loading-State Bug — Stale "جاري التحميل…" After Data Loads

**Severity**: CRITICAL  
**Evidence**: `templates/admin/heatmap.html:322-325` — the `lastUpdateStatus` chip starts with hardcoded "جاري التحميل…". The JS function `renderLastUpdate()` at `jordan_geo_intelligence.js:695-705` tries to replace it with a timestamp, but returns early (`if (!ts) return;`) if the `/daily-update` API response lacks `last_run.completed_at` or `updated_at`.

```js
// jordan_geo_intelligence.js:695-705
function renderLastUpdate(daily) {
    var el = document.getElementById("lastUpdateStatus");
    if (!el) return;
    var ts = (daily && daily.last_run && daily.last_run.completed_at) || (daily && daily.updated_at);
    if (!ts) return;  // ← if daily-update fails or has no timestamp, keeps "جاري التحميل…"
    // ... replaces text with timestamp
}
```

**Why it matters**: Administrators see "جاري التحميل…" (Loading…) while the map, KPI cards, and rankings table are fully populated. This erodes trust — users believe the data is stale or the page is broken.

**Fix**:
1. In `renderLastUpdate()`, always replace the text. If `daily` has no timestamp, use a fallback:
   - On initial page render: show `جاري التحميل…` (correct for loading state)
   - After data success + no daily-update timestamp: show `تم التحميل` (Loaded) or `البيانات متوفرة` (Data Available)
   - After data success + timestamp: show `آخر تحديث: {time}`
   - On error: show `تعذر التحديث` (Update failed)

2. Add a `data-loaded` state flag that prevents the loading text from reappearing after KPI data loads.

**Implementation**:
```js
function renderLastUpdate(daily) {
    var el = document.getElementById("lastUpdateStatus");
    if (!el) return;
    var ts = (daily && daily.last_run && daily.last_run.completed_at) || (daily && daily.updated_at);
    var d = ts ? new Date(ts) : null;
    if (d && !isNaN(d)) {
        var time = d.toLocaleTimeString(IS_AR ? "ar-JO" : "en-US", {
            hour: "2-digit", minute: "2-digit"
        });
        el.innerHTML = '<i class="bi bi-clock" aria-hidden="true"></i> ' +
            (IS_AR ? "آخر تحديث: " : "Updated: ") + time;
        el.className = "status-chip info";
    } else {
        el.innerHTML = '<i class="bi bi-check-circle" aria-hidden="true"></i> ' +
            (IS_AR ? "تم تحميل البيانات" : "Data loaded");
        el.className = "status-chip live";
    }
}
```

**Acceptance criteria**:
- Before data loads: "جاري التحميل…" is visible
- After data loads successfully: loading text disappears
- If daily-update has timestamp: "آخر تحديث: HH:MM"
- If daily-update fails: "تم تحميل البيانات" with green indicator
- If data fails entirely: error state shown

---

### 2.2 Risk Classification Boundary Gap — Non-Integer Scores Fall Through to "Critical"

**Severity**: CRITICAL  
**Evidence**: `heatmap/backend/constants.py:196-202` — `risk_level_for_score()` uses `level["min"] <= s <= level["max"]` for each band.

```python
RISK_LEVELS = [
    {"key": "low",     "min": 0,  "max": 24},
    {"key": "medium",  "min": 25, "max": 49},
    {"key": "high",    "min": 50, "max": 74},
    {"key": "critical","min": 75, "max": 100},
]

def risk_level_for_score(score: float) -> Dict:
    s = max(0.0, min(100.0, float(score or 0)))
    for level in RISK_LEVELS:
        if level["min"] <= s <= level["max"]:
            return level
    return RISK_LEVELS[-1]  # ← BUG: non-integer scores like 24.5 fall through to "critical"
```

A score of **24.5** would not match any band:
- `0 <= 24.5 <= 24` → **false** (24.5 > 24)
- `25 <= 24.5 <= 49` → **false** (24.5 < 25)
- Falls through to `return RISK_LEVELS[-1]` → **"critical" (حرج)**

The JS frontend (`jordan_geo_intelligence.js:53-58` and `jordan_heatmap.js:54-65`) uses `<` operators which correctly handle non-integer scores: `s < 25` rightly excludes 24.5 from "low".

**Why it matters**: A governorate with score 24.5 would show color green (JS correctly classifies via `< 25`), but the backend-performed classification in the API response would be "critical". Any code reading the backend's `risk_level` field would show "حرج" for a score that should be "منخفض".

**Fix**: Change backend comparison to match frontend semantics:
```python
def risk_level_for_score(score: float) -> Dict:
    s = max(0.0, min(100.0, float(score or 0)))
    if s < 25:   return RISK_BY_KEY["low"]
    if s < 50:   return RISK_BY_KEY["medium"]
    if s < 75:   return RISK_BY_KEY["high"]
    return            RISK_BY_KEY["critical"]
```

Also centralize the threshold values into a shared constant used by both frontend JS and backend Python.

**Acceptance criteria**:
| Score | Expected result | Current backend | Current frontend |
|-------|----------------|-----------------|------------------|
| 0     | منخفض          | منخفض ✅        | منخفض ✅         |
| 24    | منخفض          | منخفض ✅        | منخفض ✅         |
| 24.5  | منخفض          | **حرج ❌**      | منخفض ✅         |
| 25    | متوسط          | متوسط ✅        | متوسط ✅         |
| 49    | متوسط          | متوسط ✅        | متوسط ✅         |
| 49.5  | متوسط          | **حرج ❌**      | متوسط ✅         |
| 50    | مرتفع          | مرتفع ✅        | مرتفع ✅         |
| 74    | مرتفع          | مرتفع ✅        | مرتفع ✅         |
| 74.5  | مرتفع          | **حرج ❌**      | مرتفع ✅         |
| 75    | حرج            | حرج ✅          | حرج ✅           |
| 100   | حرج            | حرج ✅          | حرج ✅           |

---

### 2.3 Average Risk Displayed as Integer (25) Instead of 25.5

**Severity**: HIGH  
**Evidence**: The backend computes `overall_avg_risk` with `round(overall_risk_total / max(len(governors), 1), 1)` preserving one decimal (`heatmap/backend/service.py:936`). However, the JS frontend renders it as `avg.toFixed(0)` at `jordan_geo_intelligence.js:623`:

```js
if (avgEl) { avgEl.textContent = avg.toFixed(0); avgEl.style.color = rl.color; }
```

`.toFixed(0)` truncates the decimal. If the true average is 25.5, the display shows 25. The color is determined by `riskLevel(avg)` which uses the full precision value, so the color may not match the displayed integer.

**Why it matters**: Dashboard consumers see 25 (low end of medium) when the actual value is 25.5 (closer to 26). This misrepresents the national average and makes trend tracking impossible (can't detect 0.5-point movements).

**Fix**: Show one decimal place: `avg.toFixed(1)`.

**Acceptance criteria**:
- Average risk displays "25.5" not "25"
- All precision rules are consistent: tooltips, KPI cards, table column, exports
- Map choropleth fill uses the full-precision score, not the rounded display value

---

### 2.4 KPI Label Contradiction — "المؤسسات 0" vs Kindergarten Pins 218

**Severity**: HIGH  
**Evidence**: The KPI strip at `templates/admin/heatmap.html:399-403` shows "المؤسسات" (Institutions) populated by JS from `kindergarten_count`. The Leaflet map toggle at line 434 shows "أماكن الروضات" (Kindergarten Locations) with a count. If the backend API returns `kindergarten_count: 0` but the map shows 218 pins, the user sees a contradiction.

The JS rendering at `jordan_geo_intelligence.js:625` uses:
```js
if (kgEl) kgEl.textContent = totKG;   // totKG sums governorate kindergarten_count
```

If the backend returns `kindergarten_count: 0` for all or some governorates, the KPI shows 0 while the independent Leaflet KG pin layer shows 218.

**Why it matters**: Administrators lose trust when two dashboard elements that appear to measure the same thing show vastly different numbers without explanation.

**Fix**:
1. Add tooltip/helper text to the KPI card:
   - "المؤسسات المسجلة: عدد الحضانات المسجلة في قاعدة بيانات النظام"
   - "أماكن الروضات: المواقع الجغرافية المعروضة على الخريطة"
2. If `kindergarten_count` is 0 but the map has KG data, add a data-quality warning chip.
3. Rename "المؤسسات" to "الروضات المسجلة" for clarity, matching the map toggle label.
4. Add an error/partial-data state: if the backend for this metric failed, show "--" or "غير متوفرة" instead of 0.

**Implementation in KPI**: 
```html
<div class="kpi-card" title="عدد الحضانات المسجلة في قاعدة البيانات">
    <div class="kpi-label">الروضات المسجلة</div>
    <div class="kpi-value" id="kpiInstitutions">--</div>
    <div class="kpi-sub">حضانة مسجلة</div>
</div>
```

---

## 3. Data Consistency Problems

### 3.1 Backend `risk_level_for_score` Boundary Gap (See 2.2) 

### 3.2 `risk_level_for_indicator` Inversion Logic Should Be Centralized

**Severity**: MEDIUM  
**Evidence**: `heatmap/backend/constants.py:205-214` — `risk_level_for_indicator` inverts the health score (0-100, higher is better) to a risk score via `100.0 - v`. This inversion is also performed manually in `get_map_overview` and `get_governorate_overview` at `service.py:874` and `service.py:916`.

```python
# service.py:874 — duplicate inversion
risk_score += (100.0 - max(0.0, min(100.0, value))) / 6.0

# service.py:916 — duplicate inversion
risk_score = round(sum(100.0 - v for v in main.values()) / 6.0, 1)
```

This logic is duplicated across two functions and should call `risk_level_for_indicator` consistently.

---

## 4. Risk Classification Audit

### 4.1 Legend vs Code — Both Correct

The legend at `heatmap.html:456-459` and the JS `riskLevel()` function use identical boundaries:
- منخفض (0–24)
- متوسط (25–49)
- مرتفع (50–74)
- حرج (75–100)

Score 25 would correctly display as "متوسط" in both the ranking table and the map. No mismatch exists in the current JS code.

### 4.2 SVG vs Leaflet — Two Independent Color Systems

**Severity**: MEDIUM  
The multi-map SVG cards and the single Leaflet map each have their own `riskColor`/`riskLabel` implementations:
- `jordan_geo_intelligence.js:55-58` — SVG colors
- `jordan_heatmap.js:54-56` — Leaflet fill colors

Both use the same `s < 25 | s < 50 | s < 75` pattern, so they agree. But they duplicate the threshold logic. Future changes risk desynchronization.

**Fix**: Define risk thresholds once in a shared JS constant and import it in both files, or define it on the `window` global during initialization.

---

## 5. Loading/State-Management Audit

| State | Current behavior | Required |
|-------|-----------------|----------|
| Initial load | Grid loading shows ✅ | Keep |
| Data loaded | Loading text **persists** if daily-update API fails ❌ | "آخر تحديث" or "تم التحميل" |
| Partial data | No indicator shown ❌ | Warning chip: "البيانات جزئية" |
| Error (GeoJSON) | Page error shown ✅ | Keep |
| Error (KPI data) | KPI shows "--" ✅ | Keep |
| Cached data | No indicator ❌ | "بيانات مخزنة مؤقتاً" |
| Empty state | Not handled (assumes data exists) ❌ | "لا توجد بيانات للمحافظات" |

**Fix**: Add a `setDashboardState(state, detail)` function:
```js
var DASHBOARD_STATE = { LOADING: 0, LOADED: 1, PARTIAL: 2, ERROR: 3, EMPTY: 4 };

function setDashboardState(state, detail) {
    var statusEl = document.getElementById("lastUpdateStatus");
    if (!statusEl) return;
    switch (state) {
        case DASHBOARD_STATE.LOADING:
            statusEl.innerHTML = '<i class="bi bi-arrow-repeat" aria-hidden="true"></i> جاري التحميل…';
            statusEl.className = "status-chip info";
            break;
        case DASHBOARD_STATE.LOADED:
            var ts = detail || "";
            statusEl.innerHTML = '<i class="bi bi-check-circle" aria-hidden="true"></i> ' +
                (ts ? "آخر تحديث: " + ts : "تم تحميل البيانات");
            statusEl.className = "status-chip live";
            break;
        case DASHBOARD_STATE.PARTIAL:
            statusEl.innerHTML = '<i class="bi bi-exclamation-triangle" aria-hidden="true"></i> ' +
                "البيانات المعروضة جزئية";
            statusEl.className = "status-chip alert";
            break;
        case DASHBOARD_STATE.ERROR:
            statusEl.innerHTML = '<i class="bi bi-x-circle" aria-hidden="true"></i> ' +
                (detail || "تعذر تحميل البيانات");
            statusEl.className = "status-chip error";
            break;
        case DASHBOARD_STATE.EMPTY:
            statusEl.innerHTML = '<i class="bi bi-inbox" aria-hidden="true"></i> لا توجد بيانات';
            statusEl.className = "status-chip info";
            break;
    }
}
```

---

## 6. KPI Clarity Audit

| KPI | Current label | Current behavior | Issue |
|-----|--------------|-----------------|-------|
| المحافظات | Hardcoded "12" | Static in HTML | Fine for now but should be dynamic |
| متوسط الخطر | `avg.toFixed(0)` | Shows integer ❌ | Should show 1 decimal: `avg.toFixed(1)` |
| المناطق الحرجة | Count of ≥75 scores | ✅ | Fine |
| المؤسسات | Sum of `kindergarten_count` | May show 0 while map has pins ❌ | Needs tooltip + rename |

---

## 7. Arabic RTL/Localization Audit

### 7.1 English Name Subtitle in Ranking Table

**Severity**: MEDIUM  
**Evidence**: `jordan_geo_intelligence.js:656-658`:
```js
'<div class="rank-name">' + esc(name) + "</div>" +
(sub ? '<div class="rank-code">' + esc(sub) + "</div>" : "") +
```

Where `govNameAlt(g)` returns `g.name_en` (English transliteration like "Amman", "Mafraq"). This shows English names below Arabic names in the table, creating visual clutter in an Arabic RTL interface.

**Fix**: 
- Default: show Arabic names only
- Add a bilingual toggle (optional)
- If English is shown, reduce opacity and size further, or show only on hover

### 7.2 English Text in Filter Dropdown

**Severity**: LOW  
The indicator select options use bilingual labels: "مؤشر الخطر العام — Overall Risk". This is acceptable but should be configurable.

### 7.3 Sort Icons in RTL

**Severity**: LOW  
The `↕` character in the table header at `heatmap.html:529` may not render correctly in RTL on all browsers. Use a CSS arrow instead.

### 7.4 Breadcrumb Separator

The `/` separator at `heatmap.html:11` points right in LTR but should point left (`\`) in RTL or use a bidirectional-safe character like `›` or `/`.

### 7.5 Consistent Arabic Terminology

Ensure consistent use across the entire dashboard:

| Term | Arabic | Used in |
|------|--------|---------|
| Governorate | محافظة | ✅ Consistent |
| Risk | خطر / مخاطرة | Mostly "خطر" ✅ |
| Indicator | مؤشر | ✅ Consistent |
| Kindergarten | روضة / حضانة | Mixed — "الروضات" in map toggle, "المؤسسات" in KPI ❌ |
| Low | منخفض | ✅ Consistent |
| Medium | متوسط | ✅ Consistent |
| High | مرتفع | ✅ Consistent |
| Critical | حرج | ✅ Consistent |

Fix: Rename "المؤسسات" in KPI to "الروضات المسجلة" to match the map toggle "أماكن الروضات".

### 7.6 Map Badge Labels Are English Transliterations

**Severity**: MEDIUM  
**Evidence**: The Leaflet governorate badge markers (`jordan_heatmap.js` rendering `kj-gov-name`) show the English transliteration by default. In RTL mode they should show Arabic names.

---

## 8. Map Usability Audit

### 8.1 Governorate Badge Labels

The `kj-gov-name` badges show names in the current language but may overlap at small zoom levels. Consider:
- Reduce font size at lower zoom
- Cluster nearby governorates at zoom < 7
- Only show labels on hover at low zoom

### 8.2 Kindergarten Pin Clustering

218 pins on a small map will overlap severely. Without clustering, the user sees a dense cluster of markers. Consider:
- Use Leaflet.markercluster for KG pins
- Show count badges on clusters
- Only show pins at zoom ≥ 9

### 8.3 Map Synchronization

When a governorate is selected in the ranking table, the Leaflet map should highlight it. Currently `goToGov(slug)` for the SVG multi-map works but the Leaflet single-map highlight is inconsistent.

### 8.4 Color-Blind Safety

Risk colors (green, amber, orange, red) are not color-blind safe. Add:
- A `color-blind` mode toggle
- Pattern fills (hatching) as a secondary differentiator
- Ensure text labels always accompany color

---

## 9. Ranking-Table Audit

### 9.1 Sort Direction Indicator

The `↕` character shows no direction. After clicking a column header, show `↑` or `↓` to indicate sort direction.

### 9.2 Tie-Breaking

If governorates have equal scores, ranking order is undefined (the `.sort()` comparator returns 0). Add tie-breaking:
```js
// After primary score comparison:
if (av !== bv) return (av - bv) * dir;
// Tie-break by name_ar alphabetically
return (g.name_ar || "").localeCompare(h.name_ar || "") * dir;
```

### 9.3 Row-Selected Highlight

The ranking table row click highlights the governorate on the map, but no visual highlight remains on the table row itself. Add a `selected` class:
```js
trs[j].addEventListener("click", function(e) {
    // ... remove selected from all rows
    tbody.querySelectorAll(".selected").forEach(function(r) { r.classList.remove("selected"); });
    // ... add to this row
    tr.classList.add("selected");
});
```

---

## 10. Accessibility Audit

### Missing

| Feature | Status | Fix |
|---------|--------|-----|
| Governorate search field | ❌ Missing | Add `<input>` with autocomplete |
| Keyboard navigation | ❌ Missing | Tab through governorate list |
| Table-based access | ✅ Present | Ranking table exists |
| Clickable top-risk cards | ❌ Missing | Make KPI cards clickable |
| Next/prev governorate | ❌ Missing | Add keyboard arrows in side panel |
| Color contrast | ✅ Good | Dark theme has sufficient contrast |
| Non-color indicators | ⚠️ Partial | Labels accompany colors, but no pattern fills |
| Screen reader labels | ⚠️ Partial | `aria-label` on main sections, but dynamic content may not announce |
| Focus states | ⚠️ Partial | Table rows have hover but no visible focus ring |

---

## 11. Recommended Redesigned Layout

```
┌─────────────────────────────────────────────────────────┐
│ HEADER                                                   │
│ [Emblem]  خرائط المؤشرات الجغرافية                       │
│           خريطة تفاعلية لمؤشرات الأداء في المحافظات      │
│ ● بيانات مباشرة  🕐 آخر تحديث: 14:30  ⚠ 3 تنبيهات       │
├─────────────────────────────────────────────────────────┤
│ KPI STRIP                                                │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│ │ المحافظات│ │ متوسط    │ │ المناطق   │ │ الروضات      │ │
│ │ 12       │ │ الخطر    │ │ الحرجة   │ │ المسجلة 218  │ │
│ │ مغطاة    │ │ 25.5     │ │ 0        │ │ موقع جغرافي  │ │
│ └──────────┘ └──────────┘ └──────────┘ └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│ FILTERS                                                  │
│ المؤشر: [الكل ▼]  المحافظة: [الكل ▼]  [خريطة القمر] [تحديث]│
├───────────────────┬─────────────────────────────────────┤
│ LEAFLET MAP       │ SIDE PANEL                          │
│ • Choropleth      │ عمّان                               │
│ • KG pins         │ 29  متوسط                           │
│ • Badge labels    │ [عرض التقرير الكامل]                │
│                   │ مؤشرات: [bars...]                   │
│ [Legend: منخفض    │ تنبيهات: [none]                     │
│  متوسط مرتفع حرج] │ [كيف يُحسب المؤشر؟]                 │
├───────────────────┴─────────────────────────────────────┤
│ RANKING TABLE                                           │
│ # │ المحافظة        │ الدرجة │ المستوى │ [⟳]            │
│ 1 │ عمّان           │ 29     │ متوسط   │ 👁              │
│ 2 │ البلقاء         │ 26     │ متوسط   │ 👁              │
│ 3 │ إربد            │ 26     │ متوسط   │ 👁              │
│ ...                                                      │
├─────────────────────────────────────────────────────────┤
│ METHODOLOGY PANEL (expandable)                           │
│ [كيف يُحسب المؤشر؟]  ▼                                  │
│ يتم احتساب مؤشر الخطر العام بناءً على 6 مؤشرات...       │
└─────────────────────────────────────────────────────────┘
```

---

## 12. Improved Arabic Labels and Microcopy

### Status Bar

| Current | Improved | Context |
|---------|----------|---------|
| بيانات مباشرة | بيانات محدثة | "Live data" → "Updated data" |
| جاري التحميل… | جاري التحميل… | Keep for loading state |
| — (alert count) | 0 تنبيهات | Always show count with label |

### KPI Cards

| Current | Improved | Reason |
|---------|----------|--------|
| المحافظات / Governorates | المحافظات المغطاة | Clearer metric name |
| متوسط الخطر / Avg. Risk | متوسط الخطر الوطني | Matches national scope |
| المناطق الحرجة / Critical Zones | المناطق الحرجة (≥75) | Include threshold in label |
| المؤسسات / Institutions | الروضات المسجلة | Match terminology with map |

### Methodology Panel Content

```html
<details>
  <summary>كيف يُحسب المؤشر؟</summary>
  <p>يتم احتساب مؤشر الخطر العام بناءً على ستة مؤشرات فرعية:
    الحضور، الحوادث، الحوكمة، جودة البيانات، الإشغال، ووضع الحضانات.
    يتم تحويل كل مؤشر إلى درجة من 0 إلى 100 (حيث 100 = أفضل أداء)،
    ثم عكسها إلى درجة خطر (0 = آمن، 100 = حرج).</p>
  <p><strong>مستويات الخطر:</strong></p>
  <ul>
    <li>منخفض: 0–24 — مراقبة دورية</li>
    <li>متوسط: 25–49 — مراجعة خلال 30 يوماً</li>
    <li>مرتفع: 50–74 — تعيين مشرف ومعالجة خلال 14 يوماً</li>
    <li>حرج: 75–100 — تصعيد للإدارة العليا خلال 7 أيام</li>
  </ul>
  <p><strong>مصادر البيانات:</strong> سجلات الحضانات، الحضور، الحوادث، الحوكمة، التقارير اليومية.</p>
  <p><strong>تاريخ التحديث:</strong> يتم تحديث البيانات بشكل دوري حسب توفرها.</p>
</details>
```

---

## 13. Data-Validation Rules

| Check | Logic | Action on failure |
|-------|-------|-------------------|
| Risk score range | `0.0 <= score <= 100.0` | Clamp to valid range |
| Risk level match | `risk_level_for_score(score)` must match classification in API response | Recompute, log warning |
| KPI sum consistency | Sum of individual governorate kindergartens should match total | Show warning chip |
| Loading state | `lastUpdateStatus` must show loaded state if any KPI data is rendered | Always update status after data |
| Rounding precision | All scores use same decimal precision | Format consistently |
| Legend vs labels | Legend boundaries match classification function | Test on every render |

---

## 14. Test Cases

### Risk Classification Tests (Backend + Frontend)

| Input | Expected key | Expected Arabic | Expected color |
|-------|-------------|-----------------|----------------|
| 0     | low         | منخفض           | #22c55e        |
| 24    | low         | منخفض           | #22c55e        |
| 24.5  | low         | منخفض           | #22c55e        |
| 25    | medium      | متوسط           | #f59e0b        |
| 49    | medium      | متوسط           | #f59e0b        |
| 49.5  | medium      | متوسط           | #f59e0b        |
| 50    | high        | مرتفع           | #f97316        |
| 74    | high        | مرتفع           | #f97316        |
| 74.5  | high        | مرتفع           | #f97316        |
| 75    | critical    | حرج             | #ef4444        |
| 100   | critical    | حرج             | #ef4444        |
| -5    | low         | منخفض           | #22c55e        |
| 105   | critical    | حرج             | #ef4444        |
| NaN   | low         | منخفض           | #22c55e        |

### Loading State Tests

| Scenario | Expected behavior |
|----------|-------------------|
| Page loads, APIs pending | "جاري التحميل…" visible, grid spinner visible |
| All 3 APIs succeed | Loading text replaced by timestamp or "تم التحميل" |
| GeoJSON fails | Page error shown, grid loading hidden |
| Data API fails, GeoJSON succeeds | Partial data warning, map shows GeoJSON only |
| Daily-update fails | Loading text replaced by "تم تحميل البيانات" |
| Daily-update has timestamp | "آخر تحديث: HH:MM" shown |
| Data returns empty governorates | "لا توجد بيانات للمحافظات" |

### KPI Tests

| Metric | Expected value | Source |
|--------|---------------|--------|
| Average risk | `sum(risk_score) / len(govs)` rounded to 1 decimal | Backend computation |
| Critical zones | Count of governorates with `risk_score >= 75` | JS computation |
| Registered kindergartens | Sum of `kindergarten_count` from `/data` endpoint | Backend field |
| Covered governorates | Length of governorates array | JS computation |

### Localization Tests

| Element | Arabic | English |
|---------|--------|---------|
| Page title | خرائط المؤشرات الجغرافية | Geographic Indicator Heatmaps |
| KPI: governorates | المحافظات المغطاة | Covered Governorates |
| KPI: avg risk | متوسط الخطر الوطني | National Avg Risk |
| KPI: critical | المناطق الحرجة | Critical Zones |
| KPI: institutions | الروضات المسجلة | Registered Kindergartens |
| Map toggle | أماكن الروضات | Kindergarten Locations |
| Map toggle 2 | تسميات المحافظات | Governorate Labels |
| Risk low | منخفض | Low |
| Risk medium | متوسط | Medium |
| Risk high | مرتفع | High |
| Risk critical | حرج | Critical |
| Refresh | تحديث | Refresh |
| Methodology | كيف يُحسب المؤشر؟ | How is the index calculated? |

### Interaction Tests

| Action | Expected result |
|--------|-----------------|
| Click governorate on SVG map | Side panel loads, ranking row highlights |
| Click ranking row | Map highlights governorate, side panel loads |
| Select indicator filter | Map updates choropleth, ranking table resorts |
| Select governorate filter | Map zooms to governorate, table filters |
| Click "إعادة ضبط" | All filters reset, full view restored |
| Keyboard → ranking table | Arrow keys navigate rows |
| Click KG pin | Popup shows kindergarten details |

---

## 15. Implementation Checklist

### Must Fix (P0)

- [ ] Fix `risk_level_for_score()` backend → use `<` not `<=` band matching (2.2)
- [ ] Add `setDashboardState()` and always update `lastUpdateStatus` after data loads (2.1)
- [ ] Fix KPI average to show 1 decimal: `avg.toFixed(1)` (2.3)
- [ ] Add tooltip/rename for "المؤسسات" → "الروضات المسجلة" (2.4)

### Should Fix (P1)

- [ ] Centralize risk classification in one shared location (4.2)
- [ ] Add methodology panel (12)
- [ ] Make ranking table rows keyboard-accessible (10)
- [ ] Add governorate search field (10)
- [ ] Fix English name subtitle (7.1)
- [ ] Add tie-breaking to ranking sort (9.2)
- [ ] Show sort direction in table headers (9.1)

### Nice to Have (P2)

- [ ] Color-blind-safe mode (8.4)
- [ ] KG pin clustering (8.2)
- [ ] Export to PDF/Excel
- [ ] Trend indicators in KPI cards
- [ ] Bilingual toggle control
- [ ] Cached-data indicator

---

## 16. Priority Roadmap

### Week 1: Trust & Data Integrity

1. Fix backend `risk_level_for_score` boundary gap
2. Fix loading-state bug
3. Fix average risk decimal display
4. Add KPI tooltips and rename labels

### Week 2: Usability & Localization

5. Add methodology/help panel
6. Fix English subtitle in ranking table
7. Add governorate search
8. Add sort direction indicators
9. Add keyboard navigation

### Week 3: Advanced Features

10. Add color-blind-safe mode
11. Add KG marker clustering
12. Add export functionality
13. Add trend arrows and comparison

---

## 17. Final Verdict

**NOT PRODUCTION READY**

### Blocking Issues

1. **Backend risk classification boundary gap** — Non-integer scores (e.g., 24.5) are classified as "critical" instead of "low". This is a silent data-integrity defect that could mislabel any governorate with fractional scores.

2. **Loading-state bug** — The "جاري التحميل…" label persists indefinitely if the daily-update API endpoint doesn't return a timestamp, even when the map, KPI cards, and rankings are fully populated. This erodes user trust.

3. **Average risk rounding** — Displaying 25 instead of 25.5 loses a full 0.5 points of precision, making the metric meaningless for trend tracking.

4. **KPI labeling contradiction** — "المؤسسات 0" vs 218 kindergarten pins on the map creates confusion. Missing tooltips and unclear metric definitions force administrators to guess what each KPI represents.

### Conditional Pass (after P0 fixes)

Once the above issues are resolved, the dashboard has sound architecture for administrative risk visualization: multi-indicator scoring, dual-map views, governorate drill-down, and ranking. With the methodology panel, Arabic RTL polish, and accessibility improvements, it will be production-ready.