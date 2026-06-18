# Operational Workflows Specification

## 1. Multi-Severity Smart Alert System

### 1.1 Alert Severity Definitions

#### CRITICAL Alerts (Red #DC3545)
- **Attendance Emergencies**: Attendance rate < 50% for 3+ consecutive days
- **Critical Incidents**: Health emergencies requiring immediate intervention
- **Security Breaches**: Unauthorized access to sensitive child data
- **System Failures**: Core service unavailable for > 30 minutes
- **Staff Ratio Violations**: Severe understaffing posing safety risks

#### HIGH Alerts (Amber #FFC107)
- **Submission Rate Violations**: Daily report submission < threshold for 5 days
- **Staff-to-Child Ratio Issues**: Ratio exceeding recommended limits by 20%+
- **High Incident Trends**: Significant increase in incident frequency
- **Moderate Health Clusters**: Multiple health alerts in same area
- **Capacity Violations**: Over 95% capacity utilization

#### MEDIUM Alerts (Yellow - warning color)
- **Missing Reports**: Daily report missing for 3+ days
- **Data Quality Issues**: Completeness score < 80%
- **Declining Trends**: Negative trends across multiple KPIs
- **Pending Reviews**: Long-pending manager approvals
- **Maintenance Reminders**: Upcoming license renewals

#### LOW Alerts (Blue - primary color)
- **Routine Notifications**: Regular compliance reminders
- **Trend Deviations**: Minor performance variations
- **Data Inconsistencies**: Minor data entry corrections needed
- **Suggestion Alerts**: Performance improvement recommendations
- **Informational Updates**: Policy or procedure changes

### 1.2 Alert Generation Logic

```python
class AlertEngine:
    def generate_alerts(
        self,
        db: Session,
        scope_type: str,
        scope_id: Optional[str],
        evaluation_time: datetime = None
    ) -> List[ActiveAlert]:
        """
        Generate alerts based on configured thresholds and current metrics.
        """
        if evaluation_time is None:
            evaluation_time = datetime.now(timezone.utc)
        
        active_alerts = []
        
        # Fetch configured thresholds
        thresholds = db.query(models.AlertThreshold).filter(
            models.AlertThreshold.is_active == True,
            models.AlertThreshold.scope_type == scope_type
        ).all()
        
        for threshold in thresholds:
            current_value = self._fetch_current_metric(
                db, threshold.metric_type, scope_type, scope_id
            )
            
            # Check threshold violation
            if self._is_violation(current_value, threshold):
                # Calculate severity based on violation magnitude
                severity = self._calculate_severity(
                    current_value, threshold
                )
                
                # Create or update alert
                alert = self._create_or_update_alert(
                    db, threshold, current_value, severity, evaluation_time
                )
                active_alerts.append(alert)
        
        return active_alerts
    
    def _calculate_severity(
        self,
        value: float,
        threshold: models.AlertThreshold
    ) -> SeverityLevel:
        """
        Calculate alert severity based on violation magnitude.
        """
        violation_ratio = abs(value - threshold.threshold_value) / threshold.threshold_value
        
        if threshold.operator == AlertOperator.LT:
            if value < threshold.threshold_value * 0.5:  # 50% below threshold
                return SeverityLevel.CRITICAL
            elif value < threshold.threshold_value * 0.7:  # 30% below
                return SeverityLevel.HIGH
            elif value < threshold.threshold_value * 0.9:  # 10% below
                return SeverityLevel.MEDIUM
            else:
                return SeverityLevel.LOW
        else:  # GT operator
            if value > threshold.threshold_value * 2.0:
                return SeverityLevel.CRITICAL
            elif value > threshold.threshold_value * 1.5:
                return SeverityLevel.HIGH
            elif value > threshold.threshold_value * 1.1:
                return SeverityLevel.MEDIUM
            else:
                return SeverityLevel.LOW
```

## 2. Alert Threshold Configuration

### 2.1 Default Thresholds by Metric Type

| Metric | Operator | Threshold | Window | Severity | Description |
|--------|----------|-----------|--------|----------|-------------|
| attendance_rate | LT | 70 | 7 days | HIGH | Low attendance detection |
| attendance_rate | LT | 50 | 3 days | CRITICAL | Emergency low attendance |
| incident_rate | GT | 2.0 | 30 days | HIGH | High incident rate |
| staff_ratio | LT | 1.0 | 30 days | HIGH | Ratio compliance check |
| report_submission_rate | LT | 85 | 7 days | MEDIUM | Daily report compliance |
| capacity_utilization | GT | 95 | - | HIGH | Overcapacity warning |
| data_completeness | LT | 80 | - | MEDIUM | Data quality alert |

### 2.2 Threshold Configuration API
```python
class ThresholdConfigAPI:
    @router.post("/alert-thresholds")
    async def create_threshold(
        config: ThresholdRequest,
        db: Session = Depends(get_db),
        current_user: User = Depends(require_admin)
    ):
        """
        Create new alert threshold configuration.
        """
        threshold = models.AlertThreshold(
            metric_type=config.metric_type,
            scope_type=config.scope_type,
            scope_id=config.scope_id,
            operator=AlertOperator(config.operator),
            threshold_value=config.threshold_value,
            window_days=config.window_days,
            severity=config.severity,
            created_by=current_user.id
        )
        db.add(threshold)
        db.commit()
        return {"id": threshold.id, "message": "Threshold created"}
    
    @router.get("/alert-thresholds")
    async def list_thresholds(
        scope_type: Optional[str] = None,
        db: Session = Depends(get_db)
    ):
        """
        List all configured alert thresholds.
        """
        query = db.query(models.AlertThreshold)
        if scope_type:
            query = query.filter(models.AlertThreshold.scope_type == scope_type)
        return {"thresholds": query.all()}
```

## 3. Automated Reporting Center

### 3.1 Export Format Specifications

#### PDF Report Structure
```python
class PDFReportGenerator:
    def generate_governorate_report(
        self,
        governorate: str,
        start_date: date,
        end_date: date,
        metrics: Dict[str, Any]
    ) -> bytes:
        """
        Generate professional PDF report for governorate.
        Structure:
        1. Cover Page - Ministry Header
        2. Executive Summary
        3. KPI Dashboard
        4. Heat Map Visualization
        5. Trend Analysis Charts
        6. Top/Bottom Performers
        7. Action Recommendations
        8. Appendix - Data Tables
        """
        report = ArabicPDFReport()
        report.add_cover_page(
            title="تقرير تحليلي - " + governorate,
            period=f"{start_date} إلى {end_date}"
        )
        report.add_kpi_cards(metrics['kpis'])
        report.add_heat_map(metrics['heat_map_geojson'])
        report.add_charts(metrics['trends'])
        report.add_recommendations(metrics['recommendations'])
        return report.build()
```

#### Excel Export Structure
- **Sheet 1**: Executive Summary - Key metrics and targets
- **Sheet 2**: Raw Data - Complete dataset export
- **Sheet 3**: Aggregated KPIs - Calculated metrics by scope
- **Sheet 4**: Trend Analysis - Time-series data
- **Sheet 5**: Benchmark Comparison - Performance vs. benchmarks
- **Sheet 6**: Alerts - Active and historical alerts

#### CSV Data Export
```python
def generate_csv_export(
    data: List[Dict],
    columns: List[str],
    include_headers: bool = True
) -> str:
    """
    Generate CSV export with Arabic column headers.
    """
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=columns,
        extrasaction='ignore'
    )
    
    if include_headers:
        arabic_headers = {
            col: COLUMN_TRANSLATIONS.get(col, col)
            for col in columns
        }
        writer.writerow(arabic_headers)
    
    for row in data:
        writer.writerow(row)
    
    return output.getvalue()
```

### 3.2 Time Intelligence Filtering

```python
class TimeIntelligenceFilter:
    def apply_filter(
        self,
        query,
        filter_type: str,
        custom_start: Optional[date] = None,
        custom_end: Optional[date] = None
    ):
        """
        Apply time-based filters to queries.
        """
        today = date.today()
        
        if filter_type == "daily":
            start = today - timedelta(days=1)
            end = today
        elif filter_type == "weekly":
            start = today - timedelta(weeks=1)
            end = today
        elif filter_type == "monthly":
            start = date(today.year, today.month, 1)
            end = today
        elif filter_type == "quarterly":
            quarter = (today.month - 1) // 3 + 1
            start = date(today.year, (quarter - 1) * 3 + 1, 1)
            end = today
        elif filter_type == "annual":
            start = date(today.year, 1, 1)
            end = today
        elif filter_type == "custom":
            start = custom_start
            end = custom_end
        
        return query.filter(
            func.date(models.DailyReport.date) >= start,
            func.date(models.DailyReport.date) <= end
        )
```

## 4. Action Plan Management

### 4.1 Action Plan Creation Workflow
```python
class ActionPlanWorkflow:
    def create_from_alert(
        self,
        db: Session,
        alert: ActiveAlert
    ) -> models.Recommendation:
        """
        Auto-create action plan from alert.
        """
        # Get nursery manager for assignment
        manager = self._find_manager_for_scope(db, alert.scope_type, alert.scope_id)
        
        action = models.Recommendation(
            kindergarten_id=self._extract_kg_id(alert.scope_id),
            scope_type=alert.scope_type,
            scope_id=alert.scope_id,
            title=self._generate_title(alert),
            description=self._generate_description(alert),
            priority=self._map_severity_to_priority(alert.severity),
            assigned_to=manager.id if manager else None,
            due_date=self._calculate_due_date(alert.severity),
            status=ActionPlanStatus.OPEN
        )
        db.add(action)
        db.commit()
        
        # Send notification to assigned user
        self._send_assignment_notification(action)
        
        return action
    
    def _calculate_due_date(self, severity: SeverityLevel) -> date:
        """
        Calculate due date based on severity.
        CRITICAL: 24 hours
        HIGH: 3 days
        MEDIUM: 7 days
        LOW: 14 days
        """
        days_map = {
            SeverityLevel.CRITICAL: 1,
            SeverityLevel.HIGH: 3,
            SeverityLevel.MEDIUM: 7,
            SeverityLevel.LOW: 14
        }
        return date.today() + timedelta(days=days_map.get(severity, 7))
```

### 4.2 Action Plan Status Flow
```
OPEN → IN_PROGRESS → COMPLETED → CLOSED
                    ↓
                 CANCELLED
```

## 5. Alert Notification System

### 5.1 Notification Channels
- **In-App Notifications**: Real-time dashboard alerts
- **Email Notifications**: For non-immediate attention items
- **SMS Notifications**: For CRITICAL alerts only
- **Push Notifications**: Mobile app notifications

### 5.2 Notification Escalation
```python
class NotificationEscalator:
    def escalate_alert(
        self,
        alert: ActiveAlert,
        acknowledgment_time: datetime
    ):
        """
        Escalate alert based on acknowledgment time.
        """
        escalation_time = {
            SeverityLevel.CRITICAL: timedelta(hours=2),
            SeverityLevel.HIGH: timedelta(hours=24),
            SeverityLevel.MEDIUM: timedelta(days=3),
            SeverityLevel.LOW: timedelta(days=7)
        }
        
        max_ack_time = escalation_time.get(alert.severity, timedelta(days=3))
        
        if datetime.now(timezone.utc) - acknowledgment_time > max_ack_time:
            # Escalate to higher authority
            self._notify_supervisor(alert)
            if datetime.now(timezone.utc) - acknowledgment_time > max_ack_time * 2:
                self._notify_admin(alert)
```

## 6. Alert Resolution Workflow

### 6.1 Alert Acknowledgment
```python
@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Acknowledge an active alert.
    """
    alert = db.query(models.ActiveAlert).get(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    
    return {"status": "acknowledged"}
```

### 6.2 Alert Resolution
```python
@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: int,
    resolution_notes: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mark alert as resolved with resolution notes.
    """
    alert = db.query(models.ActiveAlert).get(alert_id)
    alert.status = AlertStatus.RESOLVED
    alert.resolution_notes = resolution_notes
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolved_by = current_user.id
    db.commit()
    
    return {"status": "resolved"}
```

## 7. Monitoring Dashboard

### 7.1 Alert Metrics Display
```python
class AlertDashboardMetrics:
    def get_alert_statistics(
        self,
        db: Session,
        scope_type: str,
        scope_id: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Get alert statistics for dashboard display.
        """
        query = db.query(
            models.ActiveAlert.severity,
            func.count(models.ActiveAlert.id).label('count')
        ).filter(
            models.ActiveAlert.status == AlertStatus.ACTIVE
        )
        
        if scope_id:
            query = query.filter(
                models.ActiveAlert.scope_type == scope_type,
                models.ActiveAlert.scope_id == scope_id
            )
        else:
            query = query.filter(
                models.ActiveAlert.scope_type == scope_type
            )
        
        results = query.group_by(models.ActiveAlert.severity).all()
        
        return {
            'critical': sum(r.count for r in results if r.severity == SeverityLevel.CRITICAL),
            'high': sum(r.count for r in results if r.severity == SeverityLevel.HIGH),
            'medium': sum(r.count for r in results if r.severity == SeverityLevel.MEDIUM),
            'low': sum(r.count for r in results if r.severity == SeverityLevel.LOW)
        }
```

### 7.2 Alert Resolution SLA Tracking
- **CRITICAL**: Must be acknowledged within 2 hours, resolved within 24 hours
- **HIGH**: Must be acknowledged within 24 hours, resolved within 72 hours
- **MEDIUM**: Must be acknowledged within 72 hours, resolved within 7 days
- **LOW**: Must be acknowledged within 7 days, resolved within 30 days

## 8. Report Scheduling and Automation

### 8.1 Scheduled Report Generation
```python
class ReportScheduler:
    def schedule_daily_report(
        self,
        scope_type: str,
        scope_id: str,
        format: str = "PDF"
    ):
        """
        Schedule daily report generation.
        """
        schedule = ReportSchedule(
            scope_type=scope_type,
            scope_id=scope_id,
            frequency="daily",
            format=format,
            next_run=datetime.now(timezone.utc).replace(
                hour=settings.GOVERNANCE_REPORT_DEADLINE_HOUR,
                minute=0,
                second=0
            ) + timedelta(days=1),
            created_by=0  # System
        )
        db.add(schedule)
        db.commit()
```

### 8.2 Automated Report Distribution
```python
@router.get("/reports/scheduled")
async def get_scheduled_reports(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user's scheduled reports.
    """
    schedules = db.query(models.ReportSchedule).filter(
        models.ReportSchedule.created_by == current_user.id
    ).all()
    
    return {
        "scheduled_reports": [
            {
                "id": s.id,
                "scope": f"{s.scope_type}: {s.scope_id}",
                "frequency": s.frequency,
                "format": s.format,
                "next_run": s.next_run.isoformat()
            }
            for s in schedules
        ]
    }
```