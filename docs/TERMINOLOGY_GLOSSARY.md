# Terminology Glossary

## Arabic

- **حضانة** – Standard term for a KinJo facility (formerly "Kindergarten", "روضة", "روضة أطفال", "رياض الأطفال", "مرفق", "منشأة").
- **الحضانة** – Definite form.
- **الحضانات** – Plural.
- **عدد الحضانات** – Number of nurseries.
- **إجمالي الحضانات** – Total nurseries.
- **أداء الحضانات** – Nursery performance.
- **بيانات الحضانة** – Nursery data.
- **مدير الحضانة** – Nursery manager.
- **مشرف الحضانة** – Nursery supervisor.
- **أطفال الحضانة** – Nursery children.
- **صفوف الحضانة** – Nursery classes.

## English

- **Nursery** – Standard term (replaces "Kindergarten", "Nursery").
- **Nurseries** – Plural.
- **Nursery Manager**
- **Nursery Supervisor**
- **Nursery Analytics**
- **Nursery Profile**
- **Nursery Performance**
- **Nursery Children**
- **Nursery Classes**

All user‑facing strings must use the terms above. Internal identifiers may retain legacy names for compatibility.

## Analytics drill-down hierarchy

The admin analytics drill-down journey has six levels. "City" is the user-facing
label for the `AREA` analytics dimension — there is no separate City model; a
nursery's finest geographic field is `Kindergarten.area`.

| Level | Dimension (`AnalyticsDimensionType`) | English | Arabic |
|---|---|---|---|
| 1 | `NETWORK` | Country / Network | الشبكة |
| 2 | `GOVERNORATE` | Governorate | المحافظة |
| 3 | `AREA` | **City** | المدينة |
| 4 | `KINDERGARTEN` | Nursery | الحضانة |
| 5 | `CLASS` | Class | الصف |
| 6 | `CHILD` | Child | الطفل |

`DISTRICT` (اللواء) exists in the data model and is accepted as an optional
intermediate between Governorate and City, but the default journey collapses to
the six levels above.

## Metric registry & data states

- **Metric registry** (`analytics/metric_registry.py` + `metric_definitions.json`):
  canonical catalog of all 33 metrics. It owns stable `metric_key`, bilingual
  titles, layer, supported dimensions, value type/direction, and privacy level.
  It does **not** duplicate computation (that stays in `analytics_gap_service.py`,
  named by each metric's `producer`) or thresholds (those stay in
  `kpi_standards.STANDARDS`, linked via `kpi_standard_key`).
- **Data states** (`analytics/metric_formatter.py`) — every metric response carries
  an explicit `data_state` so a genuine 0 is never confused with absent data:

  | State | English | Arabic |
  |---|---|---|
  | `valid` | (value shown) | — |
  | `missing` | No data | لا تتوفر بيانات |
  | `insufficient_data` | Insufficient data | بيانات غير كافية |
  | `suppressed` | Withheld for privacy | محجوب لحماية الخصوصية |
  | `not_applicable` | Not applicable | لا ينطبق |

- **`analytics:child_detail`** — individual-child (CHILD-layer) metrics are
  `privacy_level=restricted` PII, viewable by ADMIN only. Other roles receive
  `data_state=suppressed` (no values).
