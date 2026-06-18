# National Nursery Intelligence & Heat Map Dashboard - Technical Design Document

## 1. Technical Architecture and Data Pipeline

### 1.1 System Architecture Overview
The platform is built as a modern FastAPI-based microservices architecture with PostgreSQL for primary data storage, Redis for caching, and Celery for background processing. The dashboard extends this architecture with real-time analytics and geospatial visualization layers.

### 1.2 Backend Services Layer
- **FastAPI Application**: Core API server handling REST endpoints, authentication, and business logic
- **Analytics Service**: Real-time computation engine for KPIs, rankings, and predictive models (`analytics_service.py`)
- **Geospatial Service**: Map visualization and spatial analysis service using GeoJSON and spatial indexing
- **AI/ML Service**: Predictive analytics engine for forecasting and anomaly detection (`predictive_analytics.py`)
- **Governance KPI Service**: Compliance monitoring and ranking algorithms (`governance_kpi_service.py`)
- **Alert Engine**: Multi-severity alert generation and notification system

### 1.3 Frontend Framework
- **Server-side Templates**: Jinja2 templates for Arabic-first RTL interface (`templates/admin/analytics/index.html`)
- **Client-side Visualization**: Chart.js/D3.js for interactive charts and Leaflet.js for map rendering
- **CSS Framework**: Bootstrap 5 with RTL support and Arabic typography
- **Design System**: Custom Arabic-first UI components adhering to WCAG 2.1 AA standards

### 1.4 Data Processing Pipeline
```
Raw Data → Ingestion → Transformation → Aggregation → Visualization
```

**Data Ingestion Sources**:
1. **Real-time Kindergarten Operations**: Attendance logs, daily reports, incidents, enrollment applications
2. **Geographic Data**: Governorate boundaries, nursery locations, population density maps
3. **External Data Sources**: Jordan Statistical Department, Ministry of Social Development APIs
4. **Administrative Data**: Staffing records, compliance reports, health monitoring

**Processing Stages**:
- **Batch Processing**: Daily aggregations using SQLAlchemy queries and PostgreSQL materialized views
- **Stream Processing**: Real-time WebSocket updates for live dashboards (`analytics_ws.py`)
- **Caching Layer**: Redis-backed cache for high-frequency queries (`cache_service.py`)
- **Data Quality Checks**: Validation pipelines for completeness, accuracy, and timeliness

### 1.5 High-Concurrency Architecture
- **Connection Pooling**: PostgreSQL connection pools with 100+ concurrent connections
- **Redis Cluster**: Distributed cache for session management and analytics results
- **Celery Workers**: Distributed task processing for heavy computations
- **Load Balancing**: Horizontal scaling with multiple API instances
- **WebSocket Support**: Real-time dashboard updates via Socket.IO or FastAPI WebSocket endpoints

### 1.6 Security Architecture
- **Role-Based Access Control (RBAC)**: Granular permissions per user role (ADMIN, MANAGER, SUPERVISOR, PARENT)
- **Data Encryption**: AES-256 encryption for sensitive child and health data
- **Audit Logging**: Comprehensive audit trails for all data access and modifications (`audit_service.py`)
- **API Rate Limiting**: Configurable rate limits per endpoint (`config.py`)
- **Multi-Factor Authentication**: TOTP-based MFA support (`mfa_service.py`)

## 2. UI/UX Design System Specification

### 2.1 Arabic-First Design Principles
- **Primary Language**: Arabic interface with optional English fallback
- **RTL Layout**: Right-to-left text flow, navigation placement, and icon positioning
- **Typography Hierarchy**: IBM Plex Sans Arabic for body, Cairo for headings, Noto Kufi Arabic for data labels
- **Reading Patterns**: Arabic reading patterns optimized for government administrators

### 2.2 Color Palette Implementation
```css
/* Primary Government Colors */
--primary-color: #0E334F; /* Dark Blue - Primary brand */
--secondary-color: #061826; /* Deep Navy - Secondary accents */
--background-color: #F5F7FA; /* Light Gray - Main background */
--card-background: #FFFFFF; /* White - Card surfaces */
--success-color: #28A745; /* Green - Positive indicators */
--warning-color: #FFC107; /* Amber - Warning/attention */
--danger-color: #DC3545; /* Red - Critical alerts */
```

### 2.3 WCAG 2.1 AA Compliance
- **Text Contrast**: Minimum 4.5:1 ratio for all text elements
- **Focus Indicators**: Visible focus rings for keyboard navigation
- **Screen Reader Support**: Semantic HTML with ARIA labels
- **Color Blindness**: Color-blind safe palette with pattern backups
- **Keyboard Navigation**: Full keyboard accessibility for all interactive elements
- **Animation Control**: Option to disable animations for users with vestibular disorders

### 2.4 Responsive Design Grid System
- **Desktop**: 12-column grid (≥1200px)
- **Tablet**: 8-column grid (768px-1199px)
- **Mobile**: 4-column grid (≤767px)
- **Breakpoints**: Tailored for government tablet and mobile use

### 2.5 Component Library
1. **Data Cards**: KPI cards with trend indicators and drill-down capability
2. **Heat Map Components**: Interactive maps with color-coded intensity layers
3. **Alert Cards**: Severity-based alert notifications with action buttons
4. **Chart Components**: Bar, line, pie charts with Arabic labels
5. **Filter Controls**: Governorate, date range, nursery type filters
6. **Export Controls**: PDF, Excel, CSV export with time intelligence filtering

### 2.6 Dashboard Layout Templates
- **Admin Dashboard**: Network-wide analytics with governorate heat maps
- **Manager Dashboard**: Kindergarten-specific operational metrics
- **Supervisor Dashboard**: Daily reporting and child-level insights
- **Parent Dashboard**: Child-centric attendance and health monitoring

## 3. Geospatial and Visualization Engine

### 3.1 Geographic Data Model
**Jordan Governorate Boundaries**:
```python
JORDAN_GOVERNORATES = [
    "عمان", "إربد", "الزرقاء", "العقبة", "المفرق",
    "جرش", "عجلون", "الطفيلة", "الكرك", "معان", "البلقاء", "مادبا"
]
```

**Governorate GeoJSON Schema**:
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "properties": {
        "GOVERNORATE_A": "عمان",
        "GOVERNORATE_E": "Amman",
        "AREA_KM2": 1761.5
      },
      "geometry": {
        "type": "Polygon",
        "coordinates": [[[35.6, 32.0], [36.5, 32.0], ...]]
      }
    }
  ]
}
```

**Nursery Location Schema**:
```python
class NurseryLocation(Base):
    __tablename__ = "nursery_locations"
    id = Column(Integer, primary_key=True, index=True)
    kindergarten_id = Column(Integer, ForeignKey("kindergartens.id"), nullable=False)
    latitude = Column(Float, nullable=False)  # Decimal degrees
    longitude = Column(Float, nullable=False)  # Decimal degrees
    governorate = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    area = Column(String(100), nullable=False)
    address_line = Column(Text, nullable=False)
    geocode_status = Column(String(50), default="VALIDATED")  # VALIDATED, NEEDS_VERIFICATION, UNVERIFIED
    boundary_polygon = Column(JSON, nullable=True)  # GeoJSON polygon for nursery campus
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("idx_nursery_locations_governorate", "governorate"),
        Index("idx_nursery_locations_coordinates", "latitude", "longitude"),
    )
```

### 3.2 Heat Map Engine Architecture
**Heat Map Types**:
1. **Nursery Distribution Heat Map**: Density of nurseries per governorate/area
2. **Child Population Heat Map**: Density of children aged 0-5 years
3. **HR Capacity Heat Map**: Staff-to-child ratios visualization
4. **Attendance Heat Map**: Daily attendance rates across regions
5. **Health/Epidemic Monitoring Heat Map**: Health incident clustering
6. **Geographic Risk Heat Map**: Composite risk score based on multiple factors

**Heat Map Rendering Logic**:
```python
def generate_heat_map_layer(
    data_points: List[NurseryData],
    heat_type: HeatMapType,
    aggregation_level: AggregationLevel
) -> GeoJSON:
    """
    Generate GeoJSON heat map layer with intensity gradients.
    Color coding:
    - Red (High): #DC3545
    - Amber (Medium): #FFC107
    - Green (Low): #28A745
    - Blue (No Data): #0E334F
    """
```

### 3.3 Visualization Components
- **Interactive Map**: Leaflet.js with Arabic map labels and RTL tooltips
- **Layer Control**: Toggle between six heat map layers
- **Drill-Down Capability**: Click governorate → city → nursery → class detail
- **Time-Series Overlay**: Historical heat map comparisons
- **Export as PDF**: Map visualization with legend and data summary

### 3.4 Spatial Analytics Engine
- **Clustering Algorithms**: DBSCAN for nursery density detection
- **Distance Calculations**: Haversine formula for geographic proximity
- **Risk Scoring**: Composite scoring based on attendance, incidents, staffing ratios
- **Predictive Heat Maps**: Forecasted heat maps using time-series predictions

## 4. Data Modeling and KPI Logic

### 4.1 Core Metrics Schema
```python
class DashboardMetric(Base):
    id: int
    metric_type: str  # ATTENDANCE_RATE, ENROLLMENT_COUNT, etc.
    scope_type: str   # NETWORK, GOVERNORATE, KINDERGARTEN, CLASS
    scope_id: Optional[str]
    value: float
    trend: float      # Percentage change
    benchmark: float  # Target value
    computed_at: datetime
    confidence_score: float  # Data quality confidence
```

### 4.2 Key Performance Indicators (KPIs)

**Operational KPIs**:
1. **Attendance Rate**: `(PRESENT logs) / (total attendance logs) * 100`
2. **Enrollment Growth**: `(Current enrollments) / (Previous period enrollments)`
3. **Daily Report Compliance**: `(Submitted reports) / (Required reports) * 100`
4. **Incident Frequency**: `(Total incidents) / (Total children)`
5. **Health Alert Rate**: `(Health alerts) / (Total children)`
6. **Staff-to-Child Ratio**: `(Staff count) / (Child count)`

**Governance KPIs**:
1. **Submission Rate**: Bayesian-smoothed ranking with k-factor smoothing
2. **Delivery Rate**: `(Reports sent to parent) / (Submitted reports) * 100`
3. **View Rate**: `(Viewed reports) / (Delivered reports) * 100`
4. **Timeliness Score**: Median hours from creation to submission
5. **Quality Score**: `1 - (Rejection rate)`
6. **Consistency Index**: `1 - std_dev(daily_submission_rate)`

**Smart Ratios**:
1. **Child-to-Supervisor Ratio**: `∑(Children) / ∑(Supervisors)` per kindergarten
2. **Child-to-Teacher Ratio**: `∑(Children) / ∑(Teachers)` per age group
3. **Supervisor-to-Class Ratio**: `∑(Classes) / ∑(Supervisors)` per governorate
4. **Capacity Utilization**: `∑(Enrolled children) / ∑(Total capacity)` per nursery

**Demographic Indicators**:
1. **Age Distribution**: Children segmented by 0-1, 1-2, 2-4 age groups
2. **Gender Balance**: Male/Female ratio per governorate
3. **Nationality Distribution**: Jordanian vs. non-Jordanian children
4. **Special Needs Percentage**: `∑(Children with special needs) / ∑(Children)` * 100

### 4.3 Data Quality Metrics
```python
class DataQualityResult(BaseModel):
    entity_type: str
    entity_id: Optional[str]
    completeness_percent: float
    accuracy_score: float
    timeliness_score: float
    consistency_score: float
    evaluated_at: datetime
    details: Dict[str, object]
```

## 5. AI/ML Intelligence Layer

### 5.1 Predictive Analytics Engine
```python
class PredictiveAnalyticsService:
    def forecast_attendance(
        scope_type: str,
        scope_id: Optional[str],
        start_date: date,
        end_date: date,
        horizon_days: int = 30
    ) -> PredictResponse:
        """
        Linear regression forecasting with confidence intervals.
        Model: slope * days + intercept ± 1.96 * stddev
        """
    
    def predict_incidents(
        scope_type: str,
        scope_id: Optional[str],
        start_date: date,
        end_date: date,
        horizon_days: int = 30
    ) -> PredictResponse:
        """
        Seasonal ARIMA model for incident prediction.
        Incorporates day-of-week and holiday effects.
        """
    
    def forecast_enrollment_trend(
        scope_type: str,
        scope_id: Optional[str],
        start_date: date,
        end_date: date,
        horizon_days: int = 30
    ) -> PredictResponse:
        """
        Exponential smoothing for enrollment growth forecasting.
        Weighted by historical seasonality patterns.
        """
```

### 5.2 Anomaly Detection Engine
```python
def z_score_anomalies(series: List[SeriesPoint]) -> List[Tuple[SeriesPoint, float, models.SeverityLevel]]:
    """
    Z-score anomaly detection with severity classification:
    - |score| ≥ 3.0 → HIGH severity
    - |score| ≥ 2.5 → MEDIUM severity
    - |score| ≥ 2.0 → LOW severity
    """
```

### 5.3 Cross-Metric Correlation Engine
```python
class CorrelationEngine:
    def correlate_metrics(
        metric1_type: str,
        metric2_type: str,
        scope_type: str,
        scope_id: Optional[str],
        time_window_days: int = 90
    ) -> CorrelationResult:
        """
        Pearson correlation coefficient between two metrics.
        Identifies relationships like:
        - Low attendance ↔ High incident rate
        - High submission rate ↔ Low rejection rate
        - Staffing ratio ↔ Enrollment growth
        """
    
    def detect_causal_patterns(
        metrics: List[str],
        scope_type: str,
        scope_id: Optional[str]
    ) -> List[CausalPattern]:
        """
        Granger causality test for time-series metrics.
        Identifies predictive relationships across governorates.
        """
```

### 5.4 Risk Scoring Algorithm
```python
def compute_geographic_risk_score(
    governorate: str,
    city: str,
    date_range: Tuple[date, date]
) -> RiskScore:
    """
    Composite risk score based on:
    - Attendance rate (30% weight)
    - Incident frequency (25% weight)
    - Staff-to-child ratio (20% weight)
    - Health alert rate (15% weight)
    - Data completeness (10% weight)
    """
```

### 5.5 Model Training Pipeline
- **Data Preparation**: Daily aggregation of operational metrics
- **Feature Engineering**: Lagged variables, seasonal indicators, governorate clustering
- **Model Selection**: Linear regression for attendance, ARIMA for incidents, exponential smoothing for enrollment
- **Validation**: Cross-validation with governorate stratification
- **Monitoring**: Model drift detection and recalibration triggers

## 6. Operational Workflows

### 6.1 Multi-Severity Smart Alert System
**Alert Severity Levels**:
1. **CRITICAL**: Immediate action required (red)
   - Attendance rate < 50% for 3 consecutive days
   - Critical incident (health emergency)
   - Data breach or security incident
   
2. **HIGH**: Management attention needed (amber)
   - Submission rate < threshold for 5 days
   - Staff-to-child ratio violation
   - High incident frequency trend
   
3. **MEDIUM**: Supervisor review required (yellow)
   - Daily report missing for >2 days
   - Moderate health alert clustering
   - Data quality score < 80%
   
4. **LOW**: Routine monitoring (blue)
   - Minor data inconsistencies
   - Routine compliance reminders
   - Performance trend deviations

**Alert Generation Logic**:
```python
class AlertEngine:
    def generate_alerts(
        threshold_config: ThresholdRequest,
        window_days: int = 30
    ) -> List[Alert]:
        """
        Generate alerts based on threshold violations.
        Severity determined by violation magnitude and persistence.
        """
```

### 6.2 Automated Reporting Center
**Export Formats**:
1. **PDF Reports**: Professional government-grade reports with Arabic typography
2. **Excel Spreadsheets**: Multi-sheet exports with pivot tables
3. **CSV Data**: Raw data exports for external analysis
4. **GeoJSON Maps**: Exportable heat map layers for GIS software

**Time Intelligence Filters**:
- **Daily**: Last 24 hours
- **Weekly**: Last 7 days with weekday patterns
- **Monthly**: Calendar month aggregation
- **Quarterly**: Fiscal quarter summaries
- **Yearly**: Annual trends and benchmarks
- **Custom Range**: User-defined start/end dates

**Report Generation Pipeline**:
```python
class ExportService:
    def generate_pdf_report(
        scope_type: str,
        scope_id: Optional[str],
        start_date: date,
        end_date: date,
        report_type: str
    ) -> str:
        """
        Generate PDF with:
        - Executive summary
        - KPI dashboards
        - Heat map visualization
        - Action recommendations
        """
    
    def generate_excel_report(
        scope_type: str,
        scope_id: Optional[str],
        start_date: date,
        end_date: date,
        report_type: str
    ) -> str:
        """
        Multi-sheet Excel export:
        - Raw data sheet
        - Aggregated KPIs sheet
        - Trend analysis sheet
        - Benchmark comparison sheet
        """
```

### 6.3 Action Plan Management
```python
class ActionPlanService:
    def create_action_plan(
        recommendation_id: Optional[int],
        kindergarten_id: Optional[int],
        title: str,
        description: Optional[str],
        assigned_to: Optional[int],
        due_date: Optional[date]
    ) -> ActionPlan:
        """
        Create automated action plans from alert recommendations.
        Status tracking: OPEN → IN_PROGRESS → COMPLETED → CANCELLED
        """
```

## 7. Phased Implementation Roadmap

### Phase 1: Foundation (Q1)
**Duration**: 3 months
**Objectives**: Establish core data infrastructure and basic dashboard
**Deliverables**:
1. **Enhanced Data Pipeline**: Real-time ingestion from existing KinJo platform
2. **Core Dashboard**: Basic KPI cards and trend charts
3. **Arabic UI Framework**: RTL-compatible design system implementation
4. **Governorate Heat Map**: Nursery distribution visualization
5. **Basic Export**: CSV and PDF report generation

### Phase 2: Intelligence Layer (Q2)
**Duration**: 3 months
**Objectives**: Add predictive analytics and correlation engine
**Deliverables**:
1. **Predictive Models**: Attendance, incident, enrollment forecasting
2. **Anomaly Detection**: Z-score based alert generation
3. **Cross-Metric Correlation**: Relationship discovery engine
4. **Advanced Heat Maps**: Child population and HR capacity visualization
5. **Multi-Severity Alert System**: CRITICAL/HIGH/MEDIUM/LOW alerts

### Phase 3: Advanced Analytics (Q3)
**Duration**: 3 months
**Objectives**: Implement advanced risk scoring and national-scale analytics
**Deliverables**:
1. **Geographic Risk Scoring**: Composite risk heat maps
2. **Health/Epidemic Monitoring**: Health alert clustering visualization
3. **Smart Ratio Calculations**: Child-to-supervisor, child-to-teacher ratios
4. **National-Scale Rollout**: All 12 governorates with district-level drill-down
5. **Automated Reporting Center**: Excel pivot tables and time intelligence filtering

### Phase 4: Optimization & Scale (Q4)
**Duration**: 3 months
**Objectives**: Performance optimization and AI model refinement
**Deliverables**:
1. **Model Refinement**: Improved accuracy through historical data training
2. **Performance Optimization**: Query optimization and caching enhancements
3. **Mobile Optimization**: Tablet and mobile government user interfaces
4. **API Integration**: External ministry data source integrations
5. **Training & Deployment**: Ministry staff training and national rollout