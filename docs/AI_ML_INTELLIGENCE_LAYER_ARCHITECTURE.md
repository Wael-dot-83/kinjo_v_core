# AI/ML Intelligence Layer Architecture

## 1. Predictive Analytics Engine

### 1.1 Attendance Forecasting Model
- **Model Type**: Linear regression with seasonal decomposition
- **Input Features**: 
  - Historical attendance rates (90 days)
  - Day of week patterns
  - Holiday effects
  - Seasonal variations (month/quarter)
- **Output**: 30-day forecast with 95% confidence interval
- **Formula**: `predicted_attendance = slope * days + intercept ± 1.96 * stddev`

### 1.2 Incident Prediction Model
- **Model Type**: Seasonal ARIMA with holiday adjustment
- **Input Features**:
  - Daily incident counts (120 days)
  - Incident type categorization (INJURY, ILLNESS, BEHAVIOR, OTHER)
  - Severity level distribution
  - Day of week patterns
- **Output**: 14-day incident forecast
- **Formula**: ARIMA(p,d,q)(P,D,Q)[s] with exogenous holiday variables

### 1.3 Enrollment Trend Forecasting
- **Model Type**: Exponential smoothing (Holt-Winters)
- **Input Features**:
  - Daily enrollment applications (180 days)
  - Lead source analysis
  - Seasonal patterns
  - Previous year trends
- **Output**: 90-day enrollment forecast
- **Formula**: `level_t + trend_t + seasonal_t`

### 1.4 Staffing Demand Prediction
- **Model Type**: Multi-variate linear regression
- **Input Features**:
  - Child enrollment projections
  - Age group distribution
  - Staff turnover rate
  - Seasonal enrollment variations
- **Output**: Recommended staff count per role per time period
- **Formula**: `staff_needed = α * children + β * turnover + γ * seasonal_factor`

## 2. Anomaly Detection Engine

### 2.1 Z-Score Anomaly Detection
```python
def z_score_anomalies(
    series: List[SeriesPoint],
    threshold: float = 2.0
) -> List[Anomaly]:
    """
    Detect anomalies using z-score method.
    Severity thresholds:
    - z ≥ 3.0: CRITICAL severity
    - z ≥ 2.5: HIGH severity
    - z ≥ 2.0: MEDIUM severity
    - z ≥ 1.5: LOW severity
    """
    values = [p.value for p in series]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    stddev = variance ** 0.5 or 1.0
    
    anomalies = []
    for point in series:
        z_score = (point.value - mean) / stddev
        if abs(z_score) >= threshold:
            severity = classify_severity(abs(z_score))
            anomalies.append((point, round(z_score, 2), severity))
    return anomalies
```

### 2.2 Isolation Forest for Multivariate Anomalies
```python
class IsolationForestDetector:
    """
    Detect anomalies in multi-dimensional data.
    Features:
    - Aggregate multiple metrics into feature vectors
    - Detect unusual combinations of values
    - Identify atypical nursery performance patterns
    """
    
    def fit_predict(
        self,
        X: np.ndarray,
        contamination: float = 0.1
    ) -> np.ndarray:
        """Return -1 for anomalies, 1 for normal points."""
        model = IsolationForest(
            contamination=contamination,
            random_state=42,
            n_estimators=100
        )
        return model.fit_predict(X)
```

## 3. Cross-Metric Correlation Engine

### 3.1 Pearson Correlation Analysis
```python
class CorrelationEngine:
    def correlate(
        self,
        metric1: List[float],
        metric2: List[float]
    ) -> CorrelationResult:
        """
        Calculate Pearson correlation coefficient.
        r = Σ((x - x̄)(y - ȳ)) / √(Σ(x - x̄)² × Σ(y - ȳ)²)
        Returns:
        - correlation_coefficient: -1 to 1
        - p_value: statistical significance
        - sample_size: number of data points
        """
        n = min(len(metric1), len(metric2))
        if n < 2:
            return CorrelationResult(0.0, 1.0, 0)
        
        r = np.corrcoef(metric1[:n], metric2[:n])[0, 1]
        p_value = self.calculate_p_value(r, n)
        
        return CorrelationResult(
            correlation_coefficient=round(r, 4),
            p_value=round(p_value, 4),
            sample_size=n
        )
    
    def find_significant_correlations(
        self,
        metrics_dict: Dict[str, List[float]],
        p_threshold: float = 0.05
    ) -> List[CorrelationPair]:
        """Find all significant correlations across metrics."""
        pairs = []
        keys = list(metrics_dict.keys())
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                result = self.correlate(
                    metrics_dict[keys[i]],
                    metrics_dict[keys[j]]
                )
                if result.p_value < p_threshold:
                    pairs.append(CorrelationPair(
                        metric1=keys[i],
                        metric2=keys[j],
                        correlation=result.correlation_coefficient,
                        significance=result.p_value
                    ))
        return pairs
```

### 3.2 Granger Causality Testing
```python
def granger_causality_test(
    metric1: List[float],
    metric2: List[float],
    max_lag: int = 7
) -> GrangerResult:
    """
    Test if metric1 Granger-causes metric2.
    Null hypothesis: metric1 does not Granger-cause metric2
    """
    from statsmodels.tsa.stattools import grangercausalitytests
    
    df = pd.DataFrame({
        'metric1': metric1,
        'metric2': metric2
    })
    
    result = grangercausalitytests(
        df[['metric2', 'metric1']],
        maxlag=max_lag,
        verbose=False
    )
    
    best_p_value = min(
        result[lag][0]['ssr_ftest'][1] 
        for lag in result.keys()
    )
    
    return GrangerResult(
        is_causal=best_p_value < 0.05,
        p_value=best_p_value,
        optimal_lag=min(result.keys(), key=lambda l: result[l][0]['ssr_ftest'][1])
    )
```

## 4. Risk Scoring Algorithm

### 4.1 Composite Risk Score Calculation
```python
def compute_composite_risk_score(
    attendance_rate: float,
    incident_rate: float,
    staff_ratio_compliance: float,
    health_alert_rate: float,
    data_completeness: float,
    weights: dict = None
) -> RiskScore:
    """
    Calculate composite risk score with weighted factors.
    
    Default weights:
    - attendance: 30% (inverse - lower is higher risk)
    - incidents: 25% (direct - higher is higher risk)
    - staff_ratio: 20% (inverse - lower is higher risk)
    - health_alerts: 15% (direct - higher is higher risk)
    - completeness: 10% (inverse - lower is higher risk)
    """
    if weights is None:
        weights = {
            'attendance': 0.30,
            'incidents': 0.25,
            'staff_ratio': 0.20,
            'health_alerts': 0.15,
            'completeness': 0.10
        }
    
    # Normalize each metric to 0-1 scale
    normalized = {
        'attendance': (100 - attendance_rate) / 100,
        'incidents': min(1.0, incident_rate / 5.0),  # Cap at 5 incidents per 100 child-days
        'staff_ratio': (100 - staff_ratio_compliance) / 100,
        'health_alerts': min(1.0, health_alert_rate / 10.0),
        'completeness': (100 - data_completeness) / 100
    }
    
    score = sum(
        normalized[key] * weights[key] 
        for key in weights.keys()
    )
    
    risk_level = classify_risk_level(score)
    
    return RiskScore(
        score=round(score, 4),
        risk_level=risk_level,
        components=normalized
    )
```

### 4.2 Risk Level Classification
```python
def classify_risk_level(score: float) -> str:
    """
    Classify risk score into levels.
    - High Risk: score > 0.6
    - Medium Risk: 0.3 < score ≤ 0.6
    - Low Risk: score ≤ 0.3
    """
    if score > 0.6:
        return "HIGH"
    elif score > 0.3:
        return "MEDIUM"
    else:
        return "LOW"
```

## 5. Model Training Pipeline

### 5.1 Data Preparation
```python
class ModelTrainingPipeline:
    def prepare_features(
        self,
        db: Session,
        start_date: date,
        end_date: date
    ) -> pd.DataFrame:
        """
        Prepare training features from operational data.
        Features include lagged variables and seasonal indicators.
        """
        features = []
        dates = self.date_range(start_date, end_date)
        
        for d in dates:
            day_features = {
                'date': d,
                'day_of_week': d.weekday(),
                'is_weekend': d.weekday() >= 5,
                'is_holiday': self.is_holiday(d),
                'month': d.month,
                'season': self.get_season(d),
                'attendance_lag_1': self.get_attendance(d - timedelta(days=1)),
                'attendance_lag_7': self.get_attendance(d - timedelta(days=7)),
                'incident_lag_1': self.get_incidents(d - timedelta(days=1)),
                'incident_lag_7': self.get_incidents(d - timedelta(days=7)),
            }
            features.append(day_features)
        
        return pd.DataFrame(features)
```

### 5.2 Model Selection and Training
```python
def train_models(
    training_data: pd.DataFrame,
    target_col: str,
    model_type: str = 'auto'
) -> TrainedModel:
    """
    Train predictive model with cross-validation.
    Model selection based on MAPE (Mean Absolute Percentage Error)
    """
    if model_type == 'auto':
        # Try multiple models and select best
        models = {
            'linear': LinearRegression(),
            'rf': RandomForestRegressor(n_estimators=100),
            'xgb': XGBRegressor(n_estimators=100),
            'svm': SVR()
        }
        
        best_model = None
        best_score = float('inf')
        
        for name, model in models.items():
            scores = cross_val_score(
                model,
                training_data.drop(columns=[target_col]),
                training_data[target_col],
                cv=5,
                scoring='neg_mean_absolute_percentage_error'
            )
            avg_score = -scores.mean()
            if avg_score < best_score:
                best_score = avg_score
                best_model = (name, model)
    
    # Fit the selected model
    best_model[1].fit(
        training_data.drop(columns=[target_col]),
        training_data[target_col]
    )
    
    return TrainedModel(
        name=best_model[0],
        model=best_model[1],
        mape=best_score,
        training_date=datetime.now()
    )
```

## 6. Model Monitoring and Drift Detection

### 6.1 Drift Detection
```python
class ModelMonitor:
    def detect_drift(
        self,
        current_predictions: List[float],
        actual_values: List[float],
        baseline_predictions: List[float]
    ) -> DriftDetectionResult:
        """
        Detect model drift using statistical tests.
        Methods: PSI (Population Stability Index), KS test
        """
        psi = self.calculate_psi(
            np.array(baseline_predictions),
            np.array(current_predictions)
        )
        
        mape_current = mean_absolute_percentage_error(actual_values, current_predictions)
        mape_baseline = mean_absolute_percentage_error(actual_values, baseline_predictions)
        
        is_drift = psi > 0.25 or mape_current > mape_baseline * 1.5
        
        return DriftDetectionResult(
            is_drift=is_drift,
            psi=round(psi, 4),
            mape_increase=round(mape_current - mape_baseline, 4),
            recommendation="retrain" if is_drift else "monitor"
        )
```

### 6.2 Performance Metrics
- **MAE (Mean Absolute Error)**: Track forecast accuracy
- **MAPE (Mean Absolute Percentage Error)**: Percentage accuracy
- **R² (R-squared)**: Model fit quality
- **PSI (Population Stability Index)**: Data drift detection
- **Coverage Rate**: Confidence interval coverage percentage

## 7. AI/ML API Endpoints

### 7.1 Prediction Endpoints
```python
@router.post("/predict/attendance")
async def predict_attendance(
    request: PredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Forecast attendance rates for given scope and time period.
    Returns predictions with confidence intervals.
    """
    predictions = await predictive_analytics.predict_attendance_rate(
        db,
        request.scope_id,
        request.horizon_days
    )
    return PredictResponse(
        metric="attendance_forecast",
        scope=request.scope_type,
        predictions=predictions
    )
```

### 7.2 Correlation Endpoints
```python
@router.get("/correlate")
async def get_correlations(
    metric_types: str,
    scope_type: str,
    scope_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get correlation analysis between specified metrics.
    """
    metrics = metric_types.split(',')
    results = []
    
    for m1 in metrics:
        for m2 in metrics:
            if m1 != m2:
                corr = await correlation_engine.correlate_metrics(
                    m1, m2, scope_type, scope_id
                )
                results.append(corr)
    
    return {"correlations": results}
```

### 7.3 Risk Assessment Endpoint
```python
@router.get("/risk-score")
async def get_risk_score(
    scope_type: str,
    scope_id: str,
    date_range: Tuple[date, date],
    db: Session = Depends(get_db)
):
    """
    Calculate geographic risk score for specified scope.
    Returns risk level and component breakdown.
    """
    score = await risk_engine.compute_geographic_risk_score(
        scope_id, date_range
    )
    return RiskScoreResponse(
        scope_type=scope_type,
        scope_id=scope_id,
        risk_score=score
    )
```

## 8. AI Model Performance Benchmarks

### 8.1 Accuracy Targets
| Model | Target MAPE | Target R² | Update Frequency |
|-------|-------------|-----------|------------------|
| Attendance Forecast | < 10% | > 0.85 | Weekly |
| Incident Prediction | < 15% | > 0.75 | Bi-weekly |
| Enrollment Forecast | < 12% | > 0.80 | Monthly |
| Staffing Demand | < 8% | > 0.90 | Monthly |

### 8.2 Model Retraining Triggers
- **Performance Degradation**: MAPE increases by >50% from baseline
- **Data Drift**: PSI > 0.25
- **Concept Drift**: Seasonal pattern changes detected
- **New Data Volume**: 2x more data available since last training
- **Manual Trigger**: Quarterly scheduled retraining