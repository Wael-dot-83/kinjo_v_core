# KPI Documentation

## Kindergarten Management System - KPIs, Formulas, and Calculations

This document provides a comprehensive reference of all Key Performance Indicators (KPIs) defined in the system, including their names, descriptions, formulas, equations, and calculation methods.

---

## Table of Contents

1. [Core Governance KPIs](#1-core-governance-kpis)
2. [Operational KPIs](#2-operational-kpis)
3. [Funnel KPIs](#3-funnel-kpis)
4. [Composite Indices](#4-composite-indices)
5. [Threshold Reference](#5-threshold-reference)

---

## 1. Core Governance KPIs

### 1.1 Overall GCEI (Governance & Child Experience Index)

| Attribute       | Value                                                                  |
| --------------- | ---------------------------------------------------------------------- |
| **Name (AR)**   | مؤشر الحوكمة وتجربة الطفل                                              |
| **Name (EN)**   | Governance & Child Experience Index                                    |
| **Description** | Comprehensive score measuring kindergarten performance quality (0-100) |
| **Formula**     | `60% Governance + 40% Child Experience`                                |
| **Equation**    | `GCEI = (GQI × 0.60) + (CEI × 0.40)`                                   |
| **Target**      | ≥80 GREEN, ≥60 AMBER, <60 RED                                          |

#### Components:

- **GQI (Governance Quality Index)**: 60% weight
- **CEI (Child Experience Index)**: 40% weight

---

### 1.2 Attendance Rate

| Attribute       | Value                                                                 |
| --------------- | --------------------------------------------------------------------- |
| **Name (AR)**   | نسبة الحضور                                                           |
| **Name (EN)**   | Attendance Rate                                                       |
| **Description** | Percentage of children attending daily                                |
| **Formula**     | `(Actual Attendance Days ÷ Expected Attendance Days) × 100`           |
| **Equation**    | `Attendance Rate = (Attended Child-Days / Expected Child-Days) × 100` |
| **Target**      | ≥90% GREEN, ≥70% AMBER, <70% RED                                      |

#### Calculation Method:

```
1. Count expected child-days:
   - Get active enrollments overlapping the period
   - Filter by working days (Sun-Thu, excluding holidays)
   - For each child: expected_days = working_days ∩ enrollment_range

2. Count attended child-days:
   - AttendanceLog with status: PRESENT, LATE, or EXCUSED

3. Calculate: (total_attended / total_expected) × 100
```

---

### 1.3 Ratio Compliance (Staff-Child Ratio)

| Attribute       | Value                                                              |
| --------------- | ------------------------------------------------------------------ |
| **Name (AR)**   | نسبة الالتزام بالنسب                                               |
| **Name (EN)**   | Staff-Child Ratio Compliance                                       |
| **Description** | Percentage of time complying with staff-child ratios               |
| **Formula**     | `(Compliant Minutes ÷ Operating Minutes) × 100`                    |
| **Equation**    | `Ratio Compliance = (Compliant Minutes / Operating Minutes) × 100` |
| **Target**      | ≥95% GREEN, ≥80% AMBER, <80% RED                                   |

#### Calculation Method:

```
1. Get operating minutes per day from operating hours
2. For each day, check if actual staff count meets required ratio
3. Required ratio: typically 1:10 (1 staff per 10 children)
4. Sum compliant minutes / total operating minutes × 100
```

---

### 1.4 Incident Rate

| Attribute       | Value                                                          |
| --------------- | -------------------------------------------------------------- |
| **Name (AR)**   | معدل الحوادث                                                   |
| **Name (EN)**   | Incident Rate                                                  |
| **Description** | Number of incidents per 100 child-days                         |
| **Formula**     | `(Number of Incidents ÷ Children Present) × 100`               |
| **Equation**    | `Incident Rate = (Incident Count / Attended Child-Days) × 100` |
| **Target**      | ≤0 GREEN, ≤0.5 AMBER, >0.5 RED (lower is better)               |

#### Calculation Method:

```
1. Count all incidents in period (any severity)
2. Count attended child-days
3. Calculate: (incidents / attended_child_days) × 100
```

---

### 1.5 Serious Incident Rate

| Attribute       | Value                                                                           |
| --------------- | ------------------------------------------------------------------------------- |
| **Name (AR)**   | الحوادث الخطرة                                                                  |
| **Name (EN)**   | Serious Incident Rate                                                           |
| **Description** | Incidents requiring medical intervention                                        |
| **Formula**     | `(Serious Incidents ÷ Children Present) × 100`                                  |
| **Equation**    | `Serious Incident Rate = (HIGH/CRITICAL Incidents / Attended Child-Days) × 100` |
| **Target**      | 0 GREEN, ≤0.1 AMBER, >0.1 RED (lower is better)                                 |

#### Calculation Method:

```
1. Count incidents with severity: HIGH or CRITICAL
2. Count attended child-days
3. Calculate: (serious_incidents / attended_child_days) × 100
```

---

### 1.6 Incident Follow-up SLA

| Attribute       | Value                                                                    |
| --------------- | ------------------------------------------------------------------------ |
| **Name (AR)**   | متابعة الحوادث                                                           |
| **Name (EN)**   | Incident Follow-up SLA                                                   |
| **Description** | Percentage of incidents closed within 48 hours                           |
| **Formula**     | `(Closed within 48h ÷ Total with Follow-up) × 100`                       |
| **Equation**    | `SLA Compliance = (Closed Within SLA / Total Requiring Follow-up) × 100` |
| **Target**      | 100% GREEN, ≥90% AMBER, <90% RED                                         |

#### Calculation Method:

```
1. Count incidents requiring follow-up (followup_required_flag = true)
2. Count those where closed_at ≤ followup_sla_deadline (48 hours)
3. Calculate: (closed_within_sla / total_followup_required) × 100
```

---

### 1.7 Chronic Absence Rate

| Attribute       | Value                                                                    |
| --------------- | ------------------------------------------------------------------------ |
| **Name (AR)**   | الغياب المزمن                                                            |
| **Name (EN)**   | Chronic Absence Rate                                                     |
| **Description** | Percentage of children absent >10% of school days                        |
| **Formula**     | `(Chronically Absent ÷ Total Children) × 100`                            |
| **Equation**    | `Chronic Absence = (Children with ≥10% Absence / Active Children) × 100` |
| **Target**      | ≤5% GREEN, ≤10% AMBER, >10% RED (lower is better)                        |

#### Calculation Method:

```
1. For each child, calculate absence rate:
   absence_rate = (expected_days - attended_days) / expected_days

2. Count children with absence_rate ≥ 10%
3. Calculate: (chronic_absentees / total_active_children) × 100
```

---

### 1.8 Capacity Utilization Rate

| Attribute       | Value                                                                |
| --------------- | -------------------------------------------------------------------- |
| **Name (AR)**   | نسبة استغلال الطاقة                                                  |
| **Name (EN)**   | Capacity Utilization Rate                                            |
| **Description** | Percentage utilization of capacity                                   |
| **Formula**     | `(Enrolled Children ÷ Capacity) × 100`                               |
| **Equation**    | `Capacity Utilization = (Active Enrollments / Total Capacity) × 100` |
| **Target**      | ≥90% GREEN, ≥80% AMBER, <80% RED                                     |

#### Calculation Method:

```
1. Sum capacity_total of all active classes
2. Count active enrollment applications
3. Calculate: (enrollments / total_capacity) × 100
```

---

### 1.9 Training Completion Rate

| Attribute       | Value                                             |
| --------------- | ------------------------------------------------- |
| **Name (AR)**   | اكتمال التدريب                                    |
| **Name (EN)**   | Training Completion Rate                          |
| **Description** | Percentage of staff completing mandatory training |
| **Formula**     | `(Staff Completed Training ÷ Total Staff) × 100`  |
| **Equation**    | `Training Rate = (Completed / Expected) × 100`    |
| **Target**      | ≥90% GREEN, ≥75% AMBER, <75% RED                  |

#### Calculation Method:

```
1. Count active staff (MANAGER, SUPERVISOR roles)
2. Count mandatory training modules
3. Expected = staff_count × mandatory_modules
4. Actual = completed training records in period
5. Calculate: (actual / expected) × 100
```

---

### 1.10 Report Submission Rate

| Attribute       | Value                                          |
| --------------- | ---------------------------------------------- |
| **Name (AR)**   | إرسال التقارير                                 |
| **Name (EN)**   | Report Submission Rate                         |
| **Description** | Percentage of daily reports submitted          |
| **Formula**     | `(Reports Submitted ÷ Reports Expected) × 100` |
| **Equation**    | `Report Rate = (Submitted / Expected) × 100`   |
| **Target**      | ≥95% GREEN, ≥85% AMBER, <85% RED               |

#### Calculation Method:

```
1. Count expected reports (children × working days)
2. Count submitted reports (status: SUBMITTED, APPROVED, SENT_TO_PARENT, REJECTED, RETURNED)
3. Calculate: (submitted / expected) × 100, capped at 100%
```

---

## 2. Operational KPIs

### 2.1 Active Enrollments

| Attribute       | Value                                                |
| --------------- | ---------------------------------------------------- |
| **Name (EN)**   | Active Enrollments                                   |
| **Description** | Count of currently enrolled children                 |
| **Formula**     | `COUNT(EnrollmentApplication WHERE status = ACTIVE)` |

### 2.2 New Enrollments

| Attribute       | Value                                                     |
| --------------- | --------------------------------------------------------- |
| **Name (EN)**   | New Enrollments                                           |
| **Description** | Count of new enrollments in period                        |
| **Formula**     | `COUNT(EnrollmentApplication WHERE created_at IN period)` |

### 2.3 Checklist Compliance

| Attribute          | Value                                                     |
| ------------------ | --------------------------------------------------------- |
| **Name (EN)**      | Checklist Compliance                                      |
| **Description**    | Completion of daily checklists                            |
| **Formula**        | `(Completed Checklists ÷ Required Checklists) × 100`      |
| **Required Types** | opening, safety, closing                                  |
| **Equation**       | `Checklist Rate = (completed / (working_days × 3)) × 100` |

### 2.4 Regulatory Status

| Attribute       | Value                        |
| --------------- | ---------------------------- |
| **Name (EN)**   | Regulatory Status            |
| **Description** | License validity status      |
| **Formula**     | Based on license_valid_until |
| **Equation**    | ```                          |

if license_expired: 0%
if expires within 30 days: 60%
else: 100%

```|

---

## 3. Funnel KPIs

### 3.1 Submission Funnel
| Stage | Description | Formula |
|-------|------------|---------|
| **Required** | Children with attendance | COUNT(AttendanceLog) |
| **Submitted** | Reports ≥ SUBMITTED status | COUNT(DailyReport WHERE status IN [SUBMITTED, APPROVED, SENT_TO_PARENT]) |
| **Delivered** | Reports SENT_TO_PARENT | COUNT(DailyReport WHERE status = SENT_TO_PARENT) |
| **Viewed** | Reports viewed by parents | COUNT(DailyReportView) |

### 3.2 Funnel Rates
| Rate | Formula |
|------|--------|
| **Submission Rate** | `submitted / required` |
| **Delivery Rate** | `delivered / submitted` |
| **View Rate** | `viewed / delivered` |

---

## 4. Composite Indices

### 4.1 GQI (Governance Quality Index)
| Component | Weight |
|-----------|--------|
| Ratio Compliance | 30% |
| Checklist Compliance | 20% |
| Regulatory Status | 20% |
| Training Completion | 15% |
| Incident Follow-up SLA | 15% |

**Equation:**
```

GQI = Σ(value × weight) / Σ(weights with data)

```

### 4.2 CEI (Child Experience Index)
| Component | Weight |
|-----------|--------|
| Attendance Rate | 35% |
| Chronic Absence (inverted) | 25% |
| Serious Incident Rate (inverted) | 20% |
| Parent Satisfaction | 20% |

**Equation:**
```

CEI = Σ(value × weight) / Σ(weights with data)

```

### 4.3 Governance Score
| Component | Weight |
|-----------|--------|
| GQI | 60% |
| CEI | 40% |

**Equation:**
```

Governance Score = (GQI × 0.60) + (CEI × 0.40)

```

### 4.4 Parent Satisfaction Score
| Attribute | Value |
|-----------|-------|
| **Description** | NPS converted to 0-100 scale |
| **Formula** | `(NPS + 100) / 2` |
| **NPS Formula** | `(Promoters% - Detractors%)` |
| **Promoters** | NPS score ≥ 9 |
| **Detractors** | NPS score ≤ 6 |

---

## 5. Threshold Reference

| KPI | GREEN | AMBER | RED | Lower Better |
|-----|-------|-------|-----|--------------|
| Overall GCEI | ≥80 | ≥60 | <60 | ❌ |
| Attendance Rate | ≥90% | ≥70% | <70% | ❌ |
| Ratio Compliance | ≥95% | ≥80% | <80% | ❌ |
| Incident Rate | 0 | ≤0.5 | >0.5 | ✅ |
| Serious Incident Rate | 0 | ≤0.1 | >0.1 | ✅ |
| Incident Follow-up SLA | 100% | ≥90% | <90% | ❌ |
| Chronic Absence Rate | ≤5% | ≤10% | >10% | ✅ |
| Capacity Utilization | ≥90% | ≥80% | <80% | ❌ |
| Training Completion | ≥90% | ≥75% | <75% | ❌ |
| Report Submission | ≥95% | ≥85% | <85% | ❌ |

---

## 6. Data Quality Metadata

Each KPI includes quality metadata:
- **has_data**: Boolean indicating whether data exists
- **coverage_pct**: Percentage of expected records captured
- **reason**: Explanation if data is missing

---

## 7. API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /kpi/summary` | KPI summary for manager's kindergarten |
| `GET /kpi/attendance-rate` | Attendance rate |
| `GET /kpi/governance-score` | Governance score and band |
| `GET /kpi/dashboard-data` | Full dashboard with trends |
| `GET /kpi/manager/dashboard` | Manager-scoped dashboard |
| `GET /manager/dashboard/enhanced` | Enhanced dashboard with definitions |
| `GET /kpi/network-summary` | Network-wide summary (admin) |

---

## 8. Calculation Notes

### Working Days
- Jordan school week: Sunday to Thursday
- Friday (4) and Saturday (5) are closed
- Respects OperatingCalendar overrides

### Period Calculations
- Default period: current month
- Supports daily, weekly, monthly granularity
- Maximum daily granularity: 93 days

### Enrollment Overlaps
- Uses effective dates (enrollment_start_date, enrollment_end_date)
- Only counts days within both enrollment and period range
- Active status required

---

*Document generated from system codebase - kpi_service.py, governance_kpi_service.py*
```
